"""
Firestore caching service for extracted content after relevance filtering.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import AsyncClient

try:
    from ..schema import ExtractedContent
except ImportError:
    from shared.models import ExtractedContent  # type: ignore

logger = logging.getLogger(__name__)


class FirestoreCache:
    """Firestore caching service for extracted content."""

    def __init__(self, project_id: Optional[str] = None, collection_name: str = "extracted_content_cache"):
        """
        Initialize Firestore cache.

        Args:
            project_id: GCP project ID. If None, uses default credentials.
            collection_name: Name of the Firestore collection to use.
        """
        self.project_id = project_id
        self.collection_name = collection_name
        self._client: Optional[AsyncClient] = None

    async def _get_client(self) -> AsyncClient:
        """Get or create async Firestore client."""
        if self._client is None:
            if self.project_id:
                self._client = firestore.AsyncClient(project=self.project_id)
            else:
                self._client = firestore.AsyncClient()
        return self._client

    async def cache_content(self, race_id: str, content_list: List[ExtractedContent]) -> bool:
        """
        Cache extracted content after relevance filtering.

        Args:
            race_id: The race identifier (e.g., 'mo-senate-2024')
            content_list: List of ExtractedContent objects that passed relevance check

        Returns:
            bool: True if caching succeeded, False otherwise
        """
        try:
            client = await self._get_client()
            collection_ref = client.collection(self.collection_name)

            # Create batch for efficient writes
            batch = client.batch()

            cached_count = 0
            for content in content_list:
                try:
                    # Create unique document ID based on race and content hash
                    content_hash = content.metadata.get("content_checksum", "")
                    if not content_hash:
                        logger.warning(
                            "Content missing checksum, skipping cache for %s", getattr(content.source, "url", "unknown")
                        )
                        continue

                    doc_id = f"{race_id}_{content_hash[:16]}"  # Use first 16 chars of hash
                    doc_ref = collection_ref.document(doc_id)

                    # Prepare document data
                    doc_data = {
                        "race_id": race_id,
                        "source_url": str(getattr(content.source, "url", "")),
                        "source_type": getattr(content.source, "source_type", "").value
                        if hasattr(getattr(content.source, "source_type", ""), "value")
                        else str(getattr(content.source, "source_type", "")),
                        "text": content.text,
                        "metadata": self._serialize_metadata(content.metadata),
                        "extraction_timestamp": content.extraction_timestamp,
                        "word_count": content.word_count,
                        "language": content.language,
                        "cached_at": datetime.utcnow(),
                        "content_checksum": content_hash,
                    }

                    # Add to batch
                    batch.set(doc_ref, doc_data)
                    cached_count += 1

                except Exception as e:
                    logger.error("Failed to prepare content for caching: %s", e)
                    continue

            if cached_count > 0:
                # Execute batch write
                await batch.commit()
                logger.info("Successfully cached %d extracted content items for race %s", cached_count, race_id)
                return True
            else:
                logger.warning("No content items were cached for race %s", race_id)
                return False

        except Exception as e:
            logger.error("Failed to cache content to Firestore: %s", e)
            return False

    async def get_cached_content(self, race_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve cached content for a race.

        Args:
            race_id: The race identifier

        Returns:
            List of cached content dictionaries
        """
        try:
            client = await self._get_client()
            collection_ref = client.collection(self.collection_name)

            # Query by race_id
            query = collection_ref.where("race_id", "==", race_id)
            docs = await query.get()

            cached_content = []
            for doc in docs:
                doc_data = doc.to_dict()
                cached_content.append(doc_data)

            logger.info("Retrieved %d cached content items for race %s", len(cached_content), race_id)
            return cached_content

        except Exception as e:
            logger.error("Failed to retrieve cached content from Firestore: %s", e)
            return []

    async def clear_cache(self, race_id: Optional[str] = None) -> bool:
        """
        Clear cached content.

        Args:
            race_id: If provided, only clear cache for this race. Otherwise clear all.

        Returns:
            bool: True if clearing succeeded
        """
        try:
            client = await self._get_client()
            collection_ref = client.collection(self.collection_name)

            if race_id:
                # Clear specific race
                query = collection_ref.where("race_id", "==", race_id)
                docs = await query.get()

                batch = client.batch()
                for doc in docs:
                    batch.delete(doc.reference)

                if docs:
                    await batch.commit()
                    logger.info("Cleared %d cached items for race %s", len(docs), race_id)
            else:
                # Clear all - be careful with this in production!
                docs = await collection_ref.get()
                batch = client.batch()
                for doc in docs:
                    batch.delete(doc.reference)

                if docs:
                    await batch.commit()
                    logger.info("Cleared all %d cached items", len(docs))

            return True

        except Exception as e:
            logger.error("Failed to clear cache: %s", e)
            return False

    async def get_cache_stats(self, race_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cache statistics.

        Args:
            race_id: If provided, get stats for specific race only

        Returns:
            Dict with cache statistics
        """
        try:
            client = await self._get_client()
            collection_ref = client.collection(self.collection_name)

            if race_id:
                query = collection_ref.where("race_id", "==", race_id)
                docs = await query.get()

                total_items = len(docs)
                total_size = sum(len(doc.to_dict().get("text", "")) for doc in docs)

                return {
                    "race_id": race_id,
                    "total_items": total_items,
                    "total_text_chars": total_size,
                    "avg_text_length": total_size / max(total_items, 1),
                }
            else:
                docs = await collection_ref.get()

                race_counts = {}
                total_items = len(docs)
                total_size = 0

                for doc in docs:
                    data = doc.to_dict()
                    race = data.get("race_id", "unknown")
                    race_counts[race] = race_counts.get(race, 0) + 1
                    total_size += len(data.get("text", ""))

                return {
                    "total_items": total_items,
                    "total_text_chars": total_size,
                    "avg_text_length": total_size / max(total_items, 1),
                    "race_breakdown": race_counts,
                }

        except Exception as e:
            logger.error("Failed to get cache stats: %s", e)
            return {}

    def _serialize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serialize metadata for Firestore storage.

        Firestore has limitations on nested data and data types.
        """
        serialized = {}

        for key, value in metadata.items():
            try:
                # Handle common problematic types
                if isinstance(value, (str, int, float, bool, type(None))):
                    serialized[key] = value
                elif isinstance(value, datetime):
                    serialized[key] = value.isoformat()
                elif isinstance(value, (list, tuple)):
                    # Only keep simple lists
                    if all(isinstance(item, (str, int, float, bool, type(None))) for item in value):
                        serialized[key] = list(value)
                    else:
                        serialized[key] = str(value)  # Fallback to string
                elif isinstance(value, dict):
                    # Recursively serialize nested dicts (limited depth)
                    try:
                        serialized[key] = self._serialize_metadata(value)
                    except Exception:
                        serialized[key] = str(value)  # Fallback to string
                else:
                    # Convert other types to string
                    serialized[key] = str(value)

            except Exception as e:
                logger.debug("Failed to serialize metadata key %s: %s", key, e)
                serialized[key] = f"<serialization_error: {type(value).__name__}>"

        return serialized

    async def close(self):
        """Close the Firestore client connection."""
        if self._client:
            await self._client.close()
            self._client = None
