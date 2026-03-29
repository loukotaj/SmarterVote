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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SearchCache:
    """Persistent SQLite-based cache for search API results."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        default_ttl_hours: int = 168,  # 7 days default - searches are stable
    ):
        """
        Initialize the search cache.

        Args:
            cache_dir: Directory for cache database. Defaults to ./data/cache
            default_ttl_hours: Default time-to-live for cache entries in hours (default 7 days)
        """
        self.default_ttl_hours = default_ttl_hours

        # Set up cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(os.getenv("SEARCH_CACHE_DIR", "./data/cache"))

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "search_cache.db"

        # Initialize database
        self._init_db()

        logger.info(f"Search cache initialized at {self.db_path} (TTL: {default_ttl_hours}h)")

    def _init_db(self):
        """Initialize SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
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

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM search_cache
                WHERE query_hash = ? AND expires_at > ?
                """,
                (query_hash, datetime.utcnow().isoformat()),
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
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=ttl)

        try:
            results_json = json.dumps(results, default=str)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize search results: {e}")
            return False

        try:
            with sqlite3.connect(self.db_path) as conn:
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

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            # Total entries
            total = conn.execute("SELECT COUNT(*) FROM search_cache").fetchone()[0]

            # Active (non-expired) entries
            active = conn.execute(
                "SELECT COUNT(*) FROM search_cache WHERE expires_at > ?",
                (datetime.utcnow().isoformat(),),
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
        """Remove expired cache entries. Returns count of removed entries."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM search_cache WHERE expires_at <= ?",
                (datetime.utcnow().isoformat(),),
            )
            conn.commit()
            removed = cursor.rowcount

        if removed > 0:
            logger.info(f"Cleaned up {removed} expired search cache entries")

        return removed

    def clear_for_race(self, race_id: str) -> int:
        """Clear all cached searches for a specific race."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM search_cache WHERE race_id = ?", (race_id,))
            conn.commit()
            removed = cursor.rowcount

        logger.info(f"Cleared {removed} search cache entries for race {race_id}")
        return removed

    def clear_all(self) -> int:
        """Clear all cache entries."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM search_cache")
            conn.commit()
            removed = cursor.rowcount

        logger.info(f"Cleared all {removed} search cache entries")
        return removed


# Singleton instance for easy access
_search_cache_instance: Optional[SearchCache] = None


def get_search_cache() -> SearchCache:
    """Get or create the global search cache instance."""
    global _search_cache_instance
    if _search_cache_instance is None:
        _search_cache_instance = SearchCache()
    return _search_cache_instance
