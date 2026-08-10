"""
Persistent Search Cache for SmarterVote Pipeline

SQLite-based caching layer for search API results (Serper, Google CSE).
Significantly reduces API costs by caching search results for extended periods.

Search queries are relatively stable for election research - the same query
will return similar results for days or weeks, making caching highly effective.

Usage:
    cache = SearchCache()

    # Check cache
    cached = cache.get(query_text, race_id)
    if cached:
        return cached['results']

    # Store in cache after API call
    cache.set(query_text, race_id, results, provider="serper")
"""

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.config import FIRESTORE_PAGE_CACHE_COLLECTION, FIRESTORE_SEARCH_CACHE_COLLECTION, local_paths
from shared.pipeline_config import RetentionConfig

logger = logging.getLogger("pipeline")


class SearchCache:
    """Persistent SQLite-based cache for search API results."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        default_ttl_hours: Optional[int] = None,
    ):
        """
        Initialize the search cache.

        Args:
            cache_dir: Directory for cache database. Defaults to ./data/cache
            default_ttl_hours: Default time-to-live for cache entries in hours (default 7 days)
        """
        retention = RetentionConfig.from_env()
        self.default_ttl_hours = default_ttl_hours or retention.search_cache_ttl_hours
        self.page_ttl_hours = retention.page_cache_ttl_hours

        # Set up cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(os.getenv("SEARCH_CACHE_DIR", str(local_paths.cache_dir)))

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "search_cache.db"

        # Initialize database
        self._init_db()

        logger.info(f"Search cache initialized at {self.db_path} (TTL: {self.default_ttl_hours}h)")

    def _init_db(self):
        """Initialize SQLite database schema."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS search_cache (
                    query_hash TEXT PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    race_id TEXT,
                    provider TEXT,
                    results TEXT NOT NULL,
                    result_count INTEGER,
                    searched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_search_expires ON search_cache(expires_at)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_search_race ON search_cache(race_id)
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS page_cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_length INTEGER,
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_page_expires ON page_cache(expires_at)
            """
            )
            conn.commit()

    def _query_hash(self, query_text: str, race_id: Optional[str] = None) -> str:
        """Generate consistent hash for a search query."""
        key = f"{query_text}:{race_id or ''}"
        return hashlib.sha256(key.encode()).hexdigest()

    def get(self, query_text: str, race_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached search results.

        Args:
            query_text: The search query text
            race_id: Optional race identifier for context

        Returns:
            Cached results dict or None if not found/expired
        """
        query_hash = self._query_hash(query_text, race_id)

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM search_cache
                WHERE query_hash = ? AND expires_at > ?
                """,
                (query_hash, datetime.now(timezone.utc).isoformat()),
            )
            row = cursor.fetchone()

            if row:
                # Update hit count
                conn.execute(
                    "UPDATE search_cache SET hit_count = hit_count + 1 WHERE query_hash = ?",
                    (query_hash,),
                )
                conn.commit()

                logger.debug(f"Search cache HIT for '{query_text[:50]}...' (hits: {row['hit_count'] + 1})")
                return {
                    "query_text": row["query_text"],
                    "race_id": row["race_id"],
                    "provider": row["provider"],
                    "results": json.loads(row["results"]),
                    "result_count": row["result_count"],
                    "searched_at": row["searched_at"],
                    "from_cache": True,
                }

        logger.debug(f"Search cache MISS for '{query_text[:50]}...'")
        return None

    def set(
        self,
        query_text: str,
        results: List[Dict[str, Any]],
        race_id: Optional[str] = None,
        provider: str = "unknown",
        ttl_hours: Optional[int] = None,
    ) -> bool:
        """
        Store search results in cache.

        Args:
            query_text: The search query text
            results: List of search result dicts (serializable)
            race_id: Optional race identifier
            provider: Search provider name (serper, google_cse, etc.)
            ttl_hours: Custom TTL, defaults to instance default

        Returns:
            True if cached successfully
        """
        query_hash = self._query_hash(query_text, race_id)
        ttl = ttl_hours or self.default_ttl_hours
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl)

        try:
            results_json = json.dumps(results, default=str)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize search results: {e}")
            return False

        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO search_cache
                    (query_hash, query_text, race_id, provider, results, result_count, searched_at, expires_at, hit_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        query_hash,
                        query_text,
                        race_id,
                        provider,
                        results_json,
                        len(results),
                        now.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
                conn.commit()

            logger.debug(f"Search cached: '{query_text[:50]}...' ({len(results)} results, TTL: {ttl}h)")
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to cache search results: {e}")
            return False

    def get_page(self, url: str) -> Optional[str]:
        """Return cached page text content, or None if not found/expired."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT content FROM page_cache WHERE url_hash = ? AND expires_at > ?",
                (url_hash, datetime.now(timezone.utc).isoformat()),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE page_cache SET hit_count = hit_count + 1 WHERE url_hash = ?",
                    (url_hash,),
                )
                conn.commit()
                logger.debug(f"Page cache HIT: {url[:60]}")
                return row["content"]
        logger.debug(f"Page cache MISS: {url[:60]}")
        return None

    def set_page(self, url: str, content: str, ttl_hours: Optional[int] = None) -> bool:
        """Cache stripped page text content. TTL defaults to 24h (pages change faster than searches)."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        ttl = ttl_hours or self.page_ttl_hours
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl)
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO page_cache
                    (url_hash, url, content, content_length, fetched_at, expires_at, hit_count)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (url_hash, url, content, len(content), now.isoformat(), expires_at.isoformat()),
                )
                conn.commit()
            logger.debug(f"Page cached: {url[:60]} ({len(content)} chars, TTL: {ttl}h)")
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to cache page {url[:60]}: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            # Total entries
            total = conn.execute("SELECT COUNT(*) FROM search_cache").fetchone()[0]

            # Active (non-expired) entries
            active = conn.execute(
                "SELECT COUNT(*) FROM search_cache WHERE expires_at > ?",
                (datetime.now(timezone.utc).isoformat(),),
            ).fetchone()[0]

            # Total hits
            total_hits = conn.execute("SELECT SUM(hit_count) FROM search_cache").fetchone()[0] or 0

            # By provider
            provider_stats = {}
            for row in conn.execute("SELECT provider, COUNT(*), SUM(hit_count) FROM search_cache GROUP BY provider"):
                provider_stats[row[0] or "unknown"] = {"count": row[1], "hits": row[2] or 0}

            # Cache size
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": total - active,
            "total_hits": total_hits,
            "by_provider": provider_stats,
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / (1024 * 1024), 2),
        }

    def cleanup_expired(self) -> int:
        """Remove expired cache entries from both search and page caches."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            search_cursor = conn.execute(
                "DELETE FROM search_cache WHERE expires_at <= ?",
                (now,),
            )
            page_cursor = conn.execute(
                "DELETE FROM page_cache WHERE expires_at <= ?",
                (now,),
            )
            conn.commit()
            removed_search = search_cursor.rowcount
            removed_pages = page_cursor.rowcount

        removed = removed_search + removed_pages
        if removed > 0:
            logger.info(
                "Cleaned up %s expired cache entries (%s search, %s page)",
                removed,
                removed_search,
                removed_pages,
            )

        return removed

    def clear_for_race(self, race_id: str) -> int:
        """Clear all cached searches for a specific race."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute("DELETE FROM search_cache WHERE race_id = ?", (race_id,))
            conn.commit()
            removed = cursor.rowcount

        logger.info(f"Cleared {removed} search cache entries for race {race_id}")
        return removed

    def list_cached_for_race(self, race_id: str) -> Dict[str, Any]:
        """Return cached search queries and their result URLs for a race.

        Returns ``{"searches": [{"query": ..., "urls": [...]}], "page_urls": [...]}``
        containing only non-expired entries.
        """
        now = datetime.now(timezone.utc).isoformat()
        searches: List[Dict[str, Any]] = []
        # sqlite3.Connection's context manager commits or rolls back but does
        # not close the connection. Explicit closure matters on Windows, where
        # an open SQLite handle prevents temporary cache directories from being
        # removed after this read.
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT query_text, results FROM search_cache " "WHERE race_id = ? AND expires_at > ?",
                (race_id, now),
            )
            all_urls: set = set()
            for query_text, results_json in rows:
                try:
                    results = json.loads(results_json)
                except (json.JSONDecodeError, TypeError):
                    results = []
                urls = [r.get("url", "") for r in results if r.get("url")]
                searches.append({"query": query_text, "urls": urls})
                all_urls.update(urls)

            # Also list page-cache URLs that are still valid
            page_rows = conn.execute("SELECT url FROM page_cache WHERE expires_at > ?", (now,))
            page_urls = [r[0] for r in page_rows if r[0] in all_urls]

        return {"searches": searches, "page_urls": page_urls}

    def clear_all(self) -> int:
        """Clear all cache entries across search and page caches."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            search_cursor = conn.execute("DELETE FROM search_cache")
            page_cursor = conn.execute("DELETE FROM page_cache")
            conn.commit()
            removed = search_cursor.rowcount + page_cursor.rowcount

        logger.info(f"Cleared all {removed} cache entries")
        return removed


class FirestoreSearchCache:
    """Firestore-backed cache for deployed pipeline workers.

    Cloud Run and Cloud Functions have ephemeral local disks, so SQLite only
    helps within one warm instance. This backend keeps Serper and page fetch
    results shared across all deployed workers.
    """

    def __init__(self, project: Optional[str] = None, default_ttl_hours: Optional[int] = None):
        retention = RetentionConfig.from_env()
        self.default_ttl_hours = default_ttl_hours or retention.search_cache_ttl_hours
        self.page_ttl_hours = retention.page_cache_ttl_hours
        self.project = project or os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID")
        from google.cloud import firestore  # type: ignore

        self._db = firestore.Client(project=self.project) if self.project else firestore.Client()
        self._search_collection = os.getenv("SEARCH_CACHE_FIRESTORE_COLLECTION", FIRESTORE_SEARCH_CACHE_COLLECTION)
        self._page_collection = os.getenv("PAGE_CACHE_FIRESTORE_COLLECTION", FIRESTORE_PAGE_CACHE_COLLECTION)
        logger.info(
            "Search cache initialized in Firestore collection %s (TTL: %sh)",
            self._search_collection,
            self.default_ttl_hours,
        )

    def _query_hash(self, query_text: str, race_id: Optional[str] = None) -> str:
        key = f"{query_text}:{race_id or ''}"
        return hashlib.sha256(key.encode()).hexdigest()

    def _page_hash(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    @staticmethod
    def _active(data: Dict[str, Any], now: str) -> bool:
        expires_at = data.get("expires_at")
        if hasattr(expires_at, "isoformat"):
            expires_at = expires_at.isoformat()
        return isinstance(expires_at, str) and expires_at > now

    @staticmethod
    def _decode_results(raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
        if isinstance(raw, str):
            try:
                decoded = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
            return [r for r in decoded if isinstance(r, dict)] if isinstance(decoded, list) else []
        return []

    def get(self, query_text: str, race_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        query_hash = self._query_hash(query_text, race_id)
        now = datetime.now(timezone.utc).isoformat()
        try:
            doc_ref = self._db.collection(self._search_collection).document(query_hash)
            doc = doc_ref.get()
            if not getattr(doc, "exists", False):
                return None
            data = doc.to_dict() or {}
            if not self._active(data, now):
                return None
            doc_ref.update({"hit_count": int(data.get("hit_count") or 0) + 1})
            return {
                "query_text": data.get("query_text") or query_text,
                "race_id": data.get("race_id"),
                "provider": data.get("provider"),
                "results": self._decode_results(data.get("results")),
                "result_count": data.get("result_count"),
                "searched_at": data.get("searched_at"),
                "from_cache": True,
            }
        except Exception as exc:
            logger.warning("Firestore search cache read failed: %s", exc)
            return None

    def set(
        self,
        query_text: str,
        results: List[Dict[str, Any]],
        race_id: Optional[str] = None,
        provider: str = "unknown",
        ttl_hours: Optional[int] = None,
    ) -> bool:
        query_hash = self._query_hash(query_text, race_id)
        ttl = ttl_hours or self.default_ttl_hours
        now = datetime.now(timezone.utc)
        try:
            expires_at = now + timedelta(hours=ttl)
            self._db.collection(self._search_collection).document(query_hash).set(
                {
                    "query_hash": query_hash,
                    "query_text": query_text,
                    "race_id": race_id,
                    "provider": provider,
                    "results": results,
                    "result_count": len(results),
                    "searched_at": now.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "ttl_at": expires_at,
                    "hit_count": 0,
                }
            )
            return True
        except Exception as exc:
            logger.warning("Firestore search cache write failed: %s", exc)
            return False

    def get_page(self, url: str) -> Optional[str]:
        now = datetime.now(timezone.utc).isoformat()
        try:
            doc_ref = self._db.collection(self._page_collection).document(self._page_hash(url))
            doc = doc_ref.get()
            if not getattr(doc, "exists", False):
                return None
            data = doc.to_dict() or {}
            if not self._active(data, now):
                return None
            doc_ref.update({"hit_count": int(data.get("hit_count") or 0) + 1})
            content = data.get("content")
            return content if isinstance(content, str) else None
        except Exception as exc:
            logger.warning("Firestore page cache read failed: %s", exc)
            return None

    def set_page(self, url: str, content: str, ttl_hours: Optional[int] = None) -> bool:
        now = datetime.now(timezone.utc)
        ttl = ttl_hours or self.page_ttl_hours
        try:
            expires_at = now + timedelta(hours=ttl)
            self._db.collection(self._page_collection).document(self._page_hash(url)).set(
                {
                    "url_hash": self._page_hash(url),
                    "url": url,
                    "content": content,
                    "content_length": len(content),
                    "fetched_at": now.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "ttl_at": expires_at,
                    "hit_count": 0,
                }
            )
            return True
        except Exception as exc:
            logger.warning("Firestore page cache write failed: %s", exc)
            return False

    def list_cached_for_race(self, race_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        searches: List[Dict[str, Any]] = []
        all_urls: set[str] = set()
        try:
            rows = self._db.collection(self._search_collection).where("race_id", "==", race_id).stream()
            for doc in rows:
                data = doc.to_dict() or {}
                if not self._active(data, now):
                    continue
                results = self._decode_results(data.get("results"))
                urls = [str(r.get("url")) for r in results if r.get("url")]
                searches.append({"query": data.get("query_text") or "", "urls": urls})
                all_urls.update(urls)

            page_urls: List[str] = []
            if all_urls:
                for doc in self._db.collection(self._page_collection).stream():
                    data = doc.to_dict() or {}
                    url = data.get("url")
                    if isinstance(url, str) and url in all_urls and self._active(data, now):
                        page_urls.append(url)
            return {"searches": searches, "page_urls": page_urls}
        except Exception as exc:
            logger.warning("Firestore search cache list failed: %s", exc)
            return {"searches": searches, "page_urls": []}

    def get_stats(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        total = 0
        active = 0
        total_hits = 0
        provider_stats: Dict[str, Dict[str, int]] = {}
        try:
            for doc in self._db.collection(self._search_collection).stream():
                total += 1
                data = doc.to_dict() or {}
                hits = int(data.get("hit_count") or 0)
                total_hits += hits
                provider = str(data.get("provider") or "unknown")
                provider_stats.setdefault(provider, {"count": 0, "hits": 0})
                provider_stats[provider]["count"] += 1
                provider_stats[provider]["hits"] += hits
                if self._active(data, now):
                    active += 1
        except Exception as exc:
            logger.warning("Firestore search cache stats failed: %s", exc)
        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": total - active,
            "total_hits": total_hits,
            "by_provider": provider_stats,
            "backend": "firestore",
        }

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        removed = 0
        try:
            for collection in (self._search_collection, self._page_collection):
                for doc in self._db.collection(collection).stream():
                    data = doc.to_dict() or {}
                    if not self._active(data, now):
                        doc.reference.delete()
                        removed += 1
        except Exception as exc:
            logger.warning("Firestore search cache cleanup failed: %s", exc)
        return removed

    def clear_for_race(self, race_id: str) -> int:
        removed = 0
        try:
            for doc in self._db.collection(self._search_collection).where("race_id", "==", race_id).stream():
                doc.reference.delete()
                removed += 1
        except Exception as exc:
            logger.warning("Firestore search cache clear_for_race failed: %s", exc)
        return removed

    def clear_all(self) -> int:
        removed = 0
        try:
            for collection in (self._search_collection, self._page_collection):
                for doc in self._db.collection(collection).stream():
                    doc.reference.delete()
                    removed += 1
        except Exception as exc:
            logger.warning("Firestore search cache clear_all failed: %s", exc)
        return removed


# Singleton instance for easy access
_search_cache_instance: Optional[SearchCache | FirestoreSearchCache] = None


def _should_use_firestore_cache() -> bool:
    backend = os.getenv("SEARCH_CACHE_BACKEND", "").strip().lower()
    if backend:
        return backend == "firestore"
    return (
        os.getenv("STORAGE_MODE", "").strip().lower() == "gcp"
        or bool(os.getenv("FIRESTORE_PROJECT"))
        or bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_SERVICE"))
    )


def get_search_cache() -> SearchCache | FirestoreSearchCache:
    """Get or create the global search cache instance."""
    global _search_cache_instance
    if _search_cache_instance is None:
        if _should_use_firestore_cache():
            try:
                _search_cache_instance = FirestoreSearchCache()
            except Exception as exc:
                if os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_SERVICE"):
                    raise RuntimeError("Firestore search cache is required for deployed pipeline workers") from exc
                logger.warning("Could not initialize Firestore search cache; falling back to SQLite: %s", exc)
                _search_cache_instance = SearchCache()
        else:
            _search_cache_instance = SearchCache()
    return _search_cache_instance
