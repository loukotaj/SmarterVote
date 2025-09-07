"""
Race Metadata Caching Service

Specialized caching for RaceMetadataService results with TTL support.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .firestore_cache import FirestoreCache

try:
    from ..schema import RaceJSON
except ImportError:
    try:
        from shared.models import RaceJSON  # type: ignore
    except ImportError:
        # Create a minimal stub for testing
        class RaceJSON:  # type: ignore
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
            
            def model_dump(self, **kwargs):
                return self.__dict__

logger = logging.getLogger(__name__)


class RaceMetadataCache:
    """Specialized cache for race metadata with TTL support."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        collection_name: str = "race_metadata_cache",
        default_ttl_hours: int = 12,
    ):
        """
        Initialize race metadata cache.

        Args:
            project_id: GCP project ID. If None, uses default credentials.
            collection_name: Name of the Firestore collection to use.
            default_ttl_hours: Default TTL in hours for cached entries.
        """
        self.firestore_cache = FirestoreCache(project_id=project_id, collection_name=collection_name)
        self.default_ttl_hours = default_ttl_hours

    async def get_cached_metadata(self, race_id: str, ttl_hours: Optional[int] = None) -> Optional[RaceJSON]:
        """
        Retrieve cached race metadata if it exists and is not expired.

        Args:
            race_id: The race identifier (e.g., 'mo-senate-2024')
            ttl_hours: TTL in hours. If None, uses default_ttl_hours.

        Returns:
            RaceJSON if cached and fresh, None otherwise
        """
        ttl_hours = ttl_hours or self.default_ttl_hours

        try:
            # Use race_id as document ID directly for metadata cache
            client = await self.firestore_cache._get_client()
            collection_ref = client.collection(self.firestore_cache.collection_name)
            doc_ref = collection_ref.document(race_id)
            doc = await doc_ref.get()

            if not doc.exists:
                logger.info(f"No cached metadata found for race {race_id}")
                return None

            doc_data = doc.to_dict()
            cached_at = doc_data.get("cached_at")

            if not cached_at:
                logger.warning(f"Cached metadata for race {race_id} missing cached_at timestamp")
                return None

            # Check if cache is still fresh
            if isinstance(cached_at, str):
                cached_at = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))

            cache_age = datetime.utcnow() - cached_at.replace(tzinfo=None)
            if cache_age > timedelta(hours=ttl_hours):
                logger.info(
                    f"Cached metadata for race {race_id} expired "
                    f"(age: {cache_age.total_seconds()/3600:.1f}h, TTL: {ttl_hours}h)"
                )
                return None

            # Reconstruct RaceJSON from cached data
            race_json_data = doc_data.get("race_json")
            if not race_json_data:
                logger.warning(f"Cached data for race {race_id} missing race_json field")
                return None

            # Parse the cached RaceJSON
            race_json = RaceJSON.model_validate(race_json_data)
            logger.info(
                f"Cache hit for race {race_id} "
                f"(age: {cache_age.total_seconds()/3600:.1f}h, candidates: {len(race_json.candidates)})"
            )
            return race_json

        except Exception as e:
            logger.error(f"Failed to retrieve cached metadata for race {race_id}: {e}")
            return None

    async def cache_metadata(self, race_id: str, race_json: RaceJSON) -> bool:
        """
        Cache race metadata.

        Args:
            race_id: The race identifier
            race_json: The RaceJSON object to cache

        Returns:
            bool: True if caching succeeded, False otherwise
        """
        try:
            # Prepare document data
            doc_data = {
                "race_id": race_id,
                "cached_at": datetime.utcnow(),
                "race_json": race_json.model_dump(mode="json", by_alias=True, exclude_none=True),
                "candidates_count": len(race_json.candidates),
                "confidence": str(race_json.race_metadata.confidence.value) if race_json.race_metadata else "unknown",
                "year": race_json.race_metadata.year if race_json.race_metadata else None,
                "state": race_json.race_metadata.state if race_json.race_metadata else None,
                "office_type": race_json.race_metadata.office_type if race_json.race_metadata else None,
            }

            # Store in Firestore using race_id as document ID
            client = await self.firestore_cache._get_client()
            collection_ref = client.collection(self.firestore_cache.collection_name)
            doc_ref = collection_ref.document(race_id)

            await doc_ref.set(doc_data)

            logger.info(
                f"Successfully cached metadata for race {race_id} "
                f"(candidates: {len(race_json.candidates)}, "
                f"confidence: {doc_data['confidence']})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to cache metadata for race {race_id}: {e}")
            return False

    async def invalidate_cache(self, race_id: str) -> bool:
        """
        Invalidate (delete) cached metadata for a specific race.

        Args:
            race_id: The race identifier to invalidate

        Returns:
            bool: True if invalidation succeeded
        """
        try:
            client = await self.firestore_cache._get_client()
            collection_ref = client.collection(self.firestore_cache.collection_name)
            doc_ref = collection_ref.document(race_id)

            await doc_ref.delete()
            logger.info(f"Successfully invalidated cache for race {race_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to invalidate cache for race {race_id}: {e}")
            return False

    async def bulk_invalidate_cache(self, race_ids: list[str]) -> Dict[str, bool]:
        """
        Invalidate cached metadata for multiple races.

        Args:
            race_ids: List of race identifiers to invalidate

        Returns:
            Dict mapping race_id to success status
        """
        results = {}

        try:
            client = await self.firestore_cache._get_client()
            collection_ref = client.collection(self.firestore_cache.collection_name)

            # Use batch for efficient bulk operations
            batch = client.batch()
            for race_id in race_ids:
                doc_ref = collection_ref.document(race_id)
                batch.delete(doc_ref)
                results[race_id] = True

            await batch.commit()
            logger.info(f"Successfully invalidated cache for {len(race_ids)} races")

        except Exception as e:
            logger.error(f"Failed to bulk invalidate cache: {e}")
            # Mark all as failed
            for race_id in race_ids:
                results[race_id] = False

        return results

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache statistics including TTL info
        """
        try:
            client = await self.firestore_cache._get_client()
            collection_ref = client.collection(self.firestore_cache.collection_name)
            docs = await collection_ref.get()

            now = datetime.utcnow()
            total_items = len(docs)
            fresh_items = 0
            expired_items = 0
            stats_by_year = {}
            stats_by_state = {}
            oldest_cache = None
            newest_cache = None

            for doc in docs:
                data = doc.to_dict()
                cached_at = data.get("cached_at")

                if cached_at:
                    if isinstance(cached_at, str):
                        cached_at = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
                    cached_at = cached_at.replace(tzinfo=None)

                    age_hours = (now - cached_at).total_seconds() / 3600

                    if age_hours <= self.default_ttl_hours:
                        fresh_items += 1
                    else:
                        expired_items += 1

                    if oldest_cache is None or cached_at < oldest_cache:
                        oldest_cache = cached_at
                    if newest_cache is None or cached_at > newest_cache:
                        newest_cache = cached_at

                # Count by year and state
                year = data.get("year")
                if year:
                    stats_by_year[year] = stats_by_year.get(year, 0) + 1

                state = data.get("state")
                if state:
                    stats_by_state[state] = stats_by_state.get(state, 0) + 1

            return {
                "total_items": total_items,
                "fresh_items": fresh_items,
                "expired_items": expired_items,
                "ttl_hours": self.default_ttl_hours,
                "stats_by_year": stats_by_year,
                "stats_by_state": stats_by_state,
                "oldest_cache": oldest_cache.isoformat() if oldest_cache else None,
                "newest_cache": newest_cache.isoformat() if newest_cache else None,
            }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}

    async def cleanup_expired_entries(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        try:
            client = await self.firestore_cache._get_client()
            collection_ref = client.collection(self.firestore_cache.collection_name)
            docs = await collection_ref.get()

            now = datetime.utcnow()
            expired_docs = []

            for doc in docs:
                data = doc.to_dict()
                cached_at = data.get("cached_at")

                if cached_at:
                    if isinstance(cached_at, str):
                        cached_at = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
                    cached_at = cached_at.replace(tzinfo=None)

                    age_hours = (now - cached_at).total_seconds() / 3600
                    if age_hours > self.default_ttl_hours:
                        expired_docs.append(doc.reference)

            if expired_docs:
                # Use batch for efficient deletion
                batch = client.batch()
                for doc_ref in expired_docs:
                    batch.delete(doc_ref)
                await batch.commit()

                logger.info(f"Cleaned up {len(expired_docs)} expired cache entries")
                return len(expired_docs)
            else:
                logger.info("No expired cache entries found")
                return 0

        except Exception as e:
            logger.error(f"Failed to cleanup expired entries: {e}")
            return 0

    async def close(self):
        """Close the underlying Firestore client connection."""
        await self.firestore_cache.close()