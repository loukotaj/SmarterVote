"""
Persistent Content Cache for SmarterVote Pipeline

SQLite-based caching layer for fetched web content. Provides:
- Persistent storage across runs
- Configurable TTL (time-to-live) for cache entries
- Content deduplication via URL checksums
- Automatic cache cleanup of expired entries
- Statistics and cache management utilities

Usage:
    cache = ContentCache()

    # Check cache
    cached = cache.get(url)
    if cached:
        return cached['content']

    # Store in cache
    cache.set(url, content, metadata)
"""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ContentCache:
    """Persistent SQLite-based cache for fetched web content."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        default_ttl_hours: int = 24,
        max_content_size_mb: int = 10,
    ):
        """
        Initialize the content cache.

        Args:
            cache_dir: Directory for cache database. Defaults to ./data/cache
            default_ttl_hours: Default time-to-live for cache entries in hours
            max_content_size_mb: Maximum content size to cache in MB
        """
        self.default_ttl_hours = default_ttl_hours
        self.max_content_size = max_content_size_mb * 1024 * 1024  # Convert to bytes

        # Set up cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(os.getenv("CONTENT_CACHE_DIR", "./data/cache"))

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "content_cache.db"

        # Initialize database
        self._init_db()

        logger.info(f"Content cache initialized at {self.db_path} (TTL: {default_ttl_hours}h)")

    def _init_db(self):
        """Initialize SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS content_cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    content TEXT,
                    content_type TEXT,
                    status_code INTEGER,
                    headers TEXT,
                    metadata TEXT,
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    content_size INTEGER,
                    hit_count INTEGER DEFAULT 0
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_expires_at ON content_cache(expires_at)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_url ON content_cache(url)
            """
            )
            conn.commit()

    def _url_hash(self, url: str) -> str:
        """Generate consistent hash for URL."""
        return hashlib.sha256(url.encode()).hexdigest()

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached content for a URL.

        Args:
            url: The URL to look up

        Returns:
            Cached content dict or None if not found/expired
        """
        url_hash = self._url_hash(url)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM content_cache
                WHERE url_hash = ? AND expires_at > ?
                """,
                (url_hash, datetime.utcnow().isoformat()),
            )
            row = cursor.fetchone()

            if row:
                # Update hit count
                conn.execute(
                    "UPDATE content_cache SET hit_count = hit_count + 1 WHERE url_hash = ?",
                    (url_hash,),
                )
                conn.commit()

                logger.debug(f"Cache HIT for {url[:80]}...")
                return {
                    "url": row["url"],
                    "content": row["content"],
                    "content_type": row["content_type"],
                    "status_code": row["status_code"],
                    "headers": json.loads(row["headers"]) if row["headers"] else {},
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "fetched_at": row["fetched_at"],
                    "from_cache": True,
                }

        logger.debug(f"Cache MISS for {url[:80]}...")
        return None

    def set(
        self,
        url: str,
        content: str,
        content_type: str = "text/html",
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[int] = None,
    ) -> bool:
        """
        Store content in cache.

        Args:
            url: Source URL
            content: Content to cache
            content_type: MIME type of content
            status_code: HTTP status code
            headers: HTTP response headers
            metadata: Additional metadata
            ttl_hours: Custom TTL (uses default if not specified)

        Returns:
            True if cached successfully, False otherwise
        """
        # Check content size
        content_size = len(content.encode("utf-8")) if content else 0
        if content_size > self.max_content_size:
            logger.warning(f"Content too large to cache ({content_size} bytes): {url[:80]}...")
            return False

        url_hash = self._url_hash(url)
        ttl = ttl_hours or self.default_ttl_hours
        fetched_at = datetime.utcnow()
        expires_at = fetched_at + timedelta(hours=ttl)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO content_cache
                    (url_hash, url, content, content_type, status_code, headers, metadata,
                     fetched_at, expires_at, content_size, hit_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        url_hash,
                        url,
                        content,
                        content_type,
                        status_code,
                        json.dumps(headers) if headers else None,
                        json.dumps(metadata) if metadata else None,
                        fetched_at.isoformat(),
                        expires_at.isoformat(),
                        content_size,
                    ),
                )
                conn.commit()

            logger.debug(f"Cached content for {url[:80]}... (expires: {expires_at})")
            return True

        except Exception as e:
            logger.error(f"Failed to cache content for {url}: {e}")
            return False

    def invalidate(self, url: str) -> bool:
        """
        Invalidate (remove) a cached entry.

        Args:
            url: URL to invalidate

        Returns:
            True if entry was removed, False if not found
        """
        url_hash = self._url_hash(url)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM content_cache WHERE url_hash = ?", (url_hash,))
            conn.commit()
            return cursor.rowcount > 0

    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM content_cache WHERE expires_at < ?",
                (datetime.utcnow().isoformat(),),
            )
            conn.commit()
            count = cursor.rowcount

        if count > 0:
            logger.info(f"Cleaned up {count} expired cache entries")
        return count

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM content_cache")
            conn.commit()
            count = cursor.rowcount

        logger.info(f"Cleared {count} cache entries")
        return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            # Total entries
            total = conn.execute("SELECT COUNT(*) FROM content_cache").fetchone()[0]

            # Valid (non-expired) entries
            valid = conn.execute(
                "SELECT COUNT(*) FROM content_cache WHERE expires_at > ?",
                (datetime.utcnow().isoformat(),),
            ).fetchone()[0]

            # Total size
            size_result = conn.execute("SELECT SUM(content_size) FROM content_cache").fetchone()[0]
            total_size = size_result or 0

            # Total hits
            hits_result = conn.execute("SELECT SUM(hit_count) FROM content_cache").fetchone()[0]
            total_hits = hits_result or 0

            # Oldest and newest entries
            oldest = conn.execute("SELECT MIN(fetched_at) FROM content_cache").fetchone()[0]
            newest = conn.execute("SELECT MAX(fetched_at) FROM content_cache").fetchone()[0]

        return {
            "total_entries": total,
            "valid_entries": valid,
            "expired_entries": total - valid,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_hits": total_hits,
            "oldest_entry": oldest,
            "newest_entry": newest,
            "cache_path": str(self.db_path),
        }

    def has(self, url: str) -> bool:
        """
        Check if URL is in cache (and not expired).

        Args:
            url: URL to check

        Returns:
            True if cached and valid
        """
        url_hash = self._url_hash(url)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM content_cache WHERE url_hash = ? AND expires_at > ?",
                (url_hash, datetime.utcnow().isoformat()),
            )
            return cursor.fetchone() is not None


# Global cache instance (lazy initialization)
_cache_instance: Optional[ContentCache] = None


def get_content_cache() -> ContentCache:
    """Get or create the global content cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ContentCache()
    return _cache_instance
