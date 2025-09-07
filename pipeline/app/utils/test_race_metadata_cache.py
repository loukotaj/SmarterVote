"""Test module for Race Metadata caching functionality."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Skip entire module if google cloud dependencies are unavailable
pytest.importorskip("google.cloud.firestore")

from .race_metadata_cache import RaceMetadataCache

try:
    from ..schema import RaceJSON, RaceMetadata, Candidate, ConfidenceLevel
except ImportError:
    from shared.models import RaceJSON, RaceMetadata, Candidate, ConfidenceLevel  # type: ignore


class TestRaceMetadataCache:
    """Test cases for Race Metadata caching."""

    def create_test_race_json(self, race_id: str = "test-senate-2024") -> RaceJSON:
        """Create test RaceJSON object."""
        metadata = RaceMetadata(
            race_id=race_id,
            state="TEST",
            office_type="senate",
            year=2024,
            full_office_name="U.S. Senate",
            jurisdiction="TEST",
            district=None,
            election_date=datetime(2024, 11, 5),
            race_type="federal",
            is_primary=False,
            primary_date=None,
            is_special_election=False,
            is_runoff=False,
            incumbent_party="Democratic",
            major_issues=[],
            geographic_keywords=["TEST"],
            confidence=ConfidenceLevel.MEDIUM,
            extracted_at=datetime.utcnow(),
        )

        candidates = [
            Candidate(name="John Doe", party="Democratic", incumbent=True),
            Candidate(name="Jane Smith", party="Republican", incumbent=False),
        ]

        return RaceJSON(
            id=race_id,
            election_date=datetime(2024, 11, 5),
            candidates=candidates,
            updated_utc=datetime.utcnow(),
            generator=[],
            race_metadata=metadata,
        )

    @pytest.mark.cloud
    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = RaceMetadataCache(project_id="test-project", collection_name="test_race_cache", default_ttl_hours=6)
        assert cache.firestore_cache.project_id == "test-project"
        assert cache.firestore_cache.collection_name == "test_race_cache"
        assert cache.default_ttl_hours == 6

        # Test default initialization
        default_cache = RaceMetadataCache()
        assert default_cache.firestore_cache.project_id is None
        assert default_cache.firestore_cache.collection_name == "race_metadata_cache"
        assert default_cache.default_ttl_hours == 12

    @pytest.mark.cloud
    @patch("pipeline.app.utils.race_metadata_cache.FirestoreCache")
    def test_cache_metadata_success(self, mock_firestore_cache_class):
        """Test successful metadata caching."""
        # Mock the FirestoreCache instance and Firestore client
        mock_firestore_cache = AsyncMock()
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_doc_ref = AsyncMock()

        mock_firestore_cache_class.return_value = mock_firestore_cache
        mock_firestore_cache._get_client.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_collection_ref.document.return_value = mock_doc_ref

        cache = RaceMetadataCache()
        test_race_json = self.create_test_race_json("test-race-2024")

        # Test caching
        result = asyncio.run(cache.cache_metadata("test-race-2024", test_race_json))

        # Assertions
        assert result is True
        mock_client.collection.assert_called_once()
        mock_collection_ref.document.assert_called_once_with("test-race-2024")
        mock_doc_ref.set.assert_called_once()

        # Verify the document data structure
        call_args = mock_doc_ref.set.call_args[0][0]
        assert call_args["race_id"] == "test-race-2024"
        assert call_args["candidates_count"] == 2
        assert call_args["confidence"] == "medium"
        assert call_args["year"] == 2024
        assert call_args["state"] == "TEST"
        assert call_args["office_type"] == "senate"
        assert "race_json" in call_args
        assert "cached_at" in call_args

    @pytest.mark.cloud
    @patch("pipeline.app.utils.race_metadata_cache.FirestoreCache")
    def test_get_cached_metadata_fresh(self, mock_firestore_cache_class):
        """Test retrieving fresh cached metadata."""
        # Mock the FirestoreCache instance and Firestore client
        mock_firestore_cache = AsyncMock()
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_doc_ref = AsyncMock()
        mock_doc = MagicMock()

        mock_firestore_cache_class.return_value = mock_firestore_cache
        mock_firestore_cache._get_client.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_collection_ref.document.return_value = mock_doc_ref
        mock_doc_ref.get.return_value = mock_doc

        # Mock document that exists and is fresh
        mock_doc.exists = True
        cached_time = datetime.utcnow() - timedelta(hours=1)  # 1 hour old
        test_race_json = self.create_test_race_json("test-race-2024")

        mock_doc.to_dict.return_value = {
            "race_id": "test-race-2024",
            "cached_at": cached_time,
            "race_json": test_race_json.model_dump(mode="json", by_alias=True, exclude_none=True),
            "candidates_count": 2,
            "confidence": "medium",
        }

        cache = RaceMetadataCache(default_ttl_hours=12)

        # Test retrieval
        result = asyncio.run(cache.get_cached_metadata("test-race-2024"))

        # Assertions
        assert result is not None
        assert isinstance(result, RaceJSON)
        assert result.id == "test-race-2024"
        assert len(result.candidates) == 2
        mock_collection_ref.document.assert_called_once_with("test-race-2024")

    @pytest.mark.cloud
    @patch("pipeline.app.utils.race_metadata_cache.FirestoreCache")
    def test_get_cached_metadata_expired(self, mock_firestore_cache_class):
        """Test retrieving expired cached metadata."""
        # Mock the FirestoreCache instance and Firestore client
        mock_firestore_cache = AsyncMock()
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_doc_ref = AsyncMock()
        mock_doc = MagicMock()

        mock_firestore_cache_class.return_value = mock_firestore_cache
        mock_firestore_cache._get_client.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_collection_ref.document.return_value = mock_doc_ref
        mock_doc_ref.get.return_value = mock_doc

        # Mock document that exists but is expired
        mock_doc.exists = True
        cached_time = datetime.utcnow() - timedelta(hours=25)  # 25 hours old (>12 hour TTL)
        test_race_json = self.create_test_race_json("test-race-2024")

        mock_doc.to_dict.return_value = {
            "race_id": "test-race-2024",
            "cached_at": cached_time,
            "race_json": test_race_json.model_dump(mode="json", by_alias=True, exclude_none=True),
        }

        cache = RaceMetadataCache(default_ttl_hours=12)

        # Test retrieval
        result = asyncio.run(cache.get_cached_metadata("test-race-2024"))

        # Should return None for expired cache
        assert result is None

    @pytest.mark.cloud
    @patch("pipeline.app.utils.race_metadata_cache.FirestoreCache")
    def test_get_cached_metadata_not_found(self, mock_firestore_cache_class):
        """Test retrieving non-existent cached metadata."""
        # Mock the FirestoreCache instance and Firestore client
        mock_firestore_cache = AsyncMock()
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_doc_ref = AsyncMock()
        mock_doc = MagicMock()

        mock_firestore_cache_class.return_value = mock_firestore_cache
        mock_firestore_cache._get_client.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_collection_ref.document.return_value = mock_doc_ref
        mock_doc_ref.get.return_value = mock_doc

        # Mock document that doesn't exist
        mock_doc.exists = False

        cache = RaceMetadataCache()

        # Test retrieval
        result = asyncio.run(cache.get_cached_metadata("nonexistent-race"))

        # Should return None for non-existent cache
        assert result is None

    @pytest.mark.cloud
    @patch("pipeline.app.utils.race_metadata_cache.FirestoreCache")
    def test_invalidate_cache(self, mock_firestore_cache_class):
        """Test cache invalidation."""
        # Mock the FirestoreCache instance and Firestore client
        mock_firestore_cache = AsyncMock()
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_doc_ref = AsyncMock()

        mock_firestore_cache_class.return_value = mock_firestore_cache
        mock_firestore_cache._get_client.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_collection_ref.document.return_value = mock_doc_ref

        cache = RaceMetadataCache()

        # Test invalidation
        result = asyncio.run(cache.invalidate_cache("test-race-2024"))

        # Assertions
        assert result is True
        mock_collection_ref.document.assert_called_once_with("test-race-2024")
        mock_doc_ref.delete.assert_called_once()

    @pytest.mark.cloud
    @patch("pipeline.app.utils.race_metadata_cache.FirestoreCache")
    def test_bulk_invalidate_cache(self, mock_firestore_cache_class):
        """Test bulk cache invalidation."""
        # Mock the FirestoreCache instance and Firestore client
        mock_firestore_cache = AsyncMock()
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_batch = AsyncMock()

        mock_firestore_cache_class.return_value = mock_firestore_cache
        mock_firestore_cache._get_client.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_client.batch.return_value = mock_batch

        cache = RaceMetadataCache()
        race_ids = ["race1-2024", "race2-2024", "race3-2024"]

        # Test bulk invalidation
        result = asyncio.run(cache.bulk_invalidate_cache(race_ids))

        # Assertions
        assert len(result) == 3
        assert all(success for success in result.values())
        mock_batch.commit.assert_called_once()
        assert mock_batch.delete.call_count == 3

    @pytest.mark.cloud
    @patch("pipeline.app.utils.race_metadata_cache.FirestoreCache")
    def test_get_cache_stats(self, mock_firestore_cache_class):
        """Test cache statistics."""
        # Mock the FirestoreCache instance and Firestore client
        mock_firestore_cache = AsyncMock()
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()

        mock_firestore_cache_class.return_value = mock_firestore_cache
        mock_firestore_cache._get_client.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref

        # Mock documents with various ages
        now = datetime.utcnow()
        mock_docs = []

        # Fresh document
        fresh_doc = MagicMock()
        fresh_doc.to_dict.return_value = {
            "race_id": "fresh-race-2024",
            "cached_at": now - timedelta(hours=2),
            "year": 2024,
            "state": "CA",
        }
        mock_docs.append(fresh_doc)

        # Expired document
        expired_doc = MagicMock()
        expired_doc.to_dict.return_value = {
            "race_id": "expired-race-2024",
            "cached_at": now - timedelta(hours=25),
            "year": 2024,
            "state": "TX",
        }
        mock_docs.append(expired_doc)

        mock_collection_ref.get.return_value = mock_docs

        cache = RaceMetadataCache(default_ttl_hours=12)

        # Test stats
        result = asyncio.run(cache.get_cache_stats())

        # Assertions
        assert result["total_items"] == 2
        assert result["fresh_items"] == 1
        assert result["expired_items"] == 1
        assert result["ttl_hours"] == 12
        assert result["stats_by_year"][2024] == 2
        assert result["stats_by_state"]["CA"] == 1
        assert result["stats_by_state"]["TX"] == 1

    @pytest.mark.cloud
    @patch("pipeline.app.utils.race_metadata_cache.FirestoreCache")
    def test_cleanup_expired_entries(self, mock_firestore_cache_class):
        """Test cleanup of expired entries."""
        # Mock the FirestoreCache instance and Firestore client
        mock_firestore_cache = AsyncMock()
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_batch = AsyncMock()

        mock_firestore_cache_class.return_value = mock_firestore_cache
        mock_firestore_cache._get_client.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_client.batch.return_value = mock_batch

        # Mock documents with various ages
        now = datetime.utcnow()
        mock_docs = []

        # Fresh document (should not be deleted)
        fresh_doc = MagicMock()
        fresh_doc.to_dict.return_value = {
            "cached_at": now - timedelta(hours=2),
        }
        mock_docs.append(fresh_doc)

        # Expired document (should be deleted)
        expired_doc = MagicMock()
        expired_doc.to_dict.return_value = {
            "cached_at": now - timedelta(hours=25),
        }
        expired_doc.reference = MagicMock()
        mock_docs.append(expired_doc)

        mock_collection_ref.get.return_value = mock_docs

        cache = RaceMetadataCache(default_ttl_hours=12)

        # Test cleanup
        result = asyncio.run(cache.cleanup_expired_entries())

        # Assertions
        assert result == 1  # One expired entry removed
        mock_batch.delete.assert_called_once_with(expired_doc.reference)
        mock_batch.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in cache operations."""
        cache = RaceMetadataCache()

        # Mock the firestore cache to raise exceptions
        with patch.object(cache.firestore_cache, "_get_client", side_effect=Exception("Connection error")):
            # Test that operations return appropriate failure values
            result = await cache.get_cached_metadata("test-race")
            assert result is None

            success = await cache.cache_metadata("test-race", self.create_test_race_json())
            assert success is False

            success = await cache.invalidate_cache("test-race")
            assert success is False

            stats = await cache.get_cache_stats()
            assert stats == {}

            cleanup_count = await cache.cleanup_expired_entries()
            assert cleanup_count == 0


# Manual test function for local testing (requires actual Firestore setup)
async def manual_test_with_emulator():
    """Manual test function for use with Firestore emulator."""
    print("Starting manual Race Metadata cache test...")

    # Set up for Firestore emulator (if running)
    import os

    os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"

    cache = RaceMetadataCache(project_id="test-project", collection_name="test_race_metadata_cache")

    try:
        # Create test race metadata
        test_helper = TestRaceMetadataCache()
        test_race_json = test_helper.create_test_race_json("manual-test-senate-2024")

        print("Caching test race metadata...")
        success = await cache.cache_metadata("manual-test-senate-2024", test_race_json)
        print(f"Cache result: {success}")

        print("Retrieving cached metadata...")
        cached = await cache.get_cached_metadata("manual-test-senate-2024")
        print(f"Retrieved: {cached is not None}")

        if cached:
            print(f"Cached race: {cached.id}")
            print(f"Candidates: {len(cached.candidates)}")
            print(f"Confidence: {cached.race_metadata.confidence}")

        print("Getting cache stats...")
        stats = await cache.get_cache_stats()
        print(f"Cache stats: {stats}")

        print("Testing TTL expiry with short TTL...")
        expired = await cache.get_cached_metadata("manual-test-senate-2024", ttl_hours=0)
        print(f"Expired result: {expired is None}")

        print("Invalidating test cache...")
        await cache.invalidate_cache("manual-test-senate-2024")
        print("Cache invalidated")

    except Exception as e:
        print(f"Error during manual test: {e}")
    finally:
        await cache.close()
        print("Manual test completed")


if __name__ == "__main__":
    # Run manual test (requires Firestore emulator)
    asyncio.run(manual_test_with_emulator())