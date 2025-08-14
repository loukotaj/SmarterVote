"""Test module for Firestore caching functionality."""

import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Skip entire module if google cloud dependencies are unavailable
pytest.importorskip("google.cloud.firestore")

from .firestore_cache import FirestoreCache

try:
    from ..schema import ExtractedContent, Source, SourceType
except ImportError:
    from shared.models import ExtractedContent, Source, SourceType  # type: ignore


class TestFirestoreCache:
    """Test cases for Firestore caching."""

    def create_test_content(self, url: str = "https://example.com", text: str = "Test content") -> ExtractedContent:
        """Create test ExtractedContent object."""
        source = Source(
            url=url,
            type=SourceType.WEBSITE,
            title="Test Source",
            last_accessed=datetime.utcnow(),
            description="Test description",
        )

        return ExtractedContent(
            source=source,
            text=text,
            metadata={
                "content_checksum": "abc123def456",
                "word_count": len(text.split()),
                "extraction_method": "html_readability",
                "usefulness_score": 0.8,
                "is_useful": True,
            },
            extraction_timestamp=datetime.utcnow(),
            word_count=len(text.split()),
            language="en",
        )

    @pytest.mark.cloud
    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = FirestoreCache(project_id="test-project", collection_name="test_collection")
        assert cache.project_id == "test-project"
        assert cache.collection_name == "test_collection"

        # Test default initialization
        default_cache = FirestoreCache()
        assert default_cache.project_id is None
        assert default_cache.collection_name == "extracted_content_cache"

    @pytest.mark.cloud
    @patch("pipeline.app.utils.firestore_cache.firestore.AsyncClient")
    def test_cache_content_success(self, mock_client_class):
        """Test successful content caching."""
        # Mock Firestore client and operations
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_batch = AsyncMock()
        mock_doc_ref = AsyncMock()

        mock_client_class.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_client.batch.return_value = mock_batch
        mock_collection_ref.document.return_value = mock_doc_ref

        cache = FirestoreCache()

        # Create test content
        test_content = [
            self.create_test_content("https://test1.com", "Test content 1"),
            self.create_test_content("https://test2.com", "Test content 2"),
        ]

        # Test caching
        result = asyncio.run(cache.cache_content("test-race-2024", test_content))

        # Assertions
        assert result is True
        mock_client.collection.assert_called_once_with("extracted_content_cache")
        mock_batch.commit.assert_called_once()

        # Verify batch.set was called for each content item
        assert mock_batch.set.call_count == 2

    @pytest.mark.cloud
    @patch("pipeline.app.utils.firestore_cache.firestore.AsyncClient")
    def test_get_cached_content(self, mock_client_class):
        """Test retrieving cached content."""
        # Mock Firestore client
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_query = AsyncMock()

        # Mock document data
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "race_id": "test-race-2024",
            "source_url": "https://test.com",
            "text": "Cached test content",
            "cached_at": datetime.utcnow(),
        }

        mock_client_class.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_collection_ref.where.return_value = mock_query
        mock_query.get.return_value = [mock_doc]

        cache = FirestoreCache()

        # Test retrieval
        result = asyncio.run(cache.get_cached_content("test-race-2024"))

        # Assertions
        assert len(result) == 1
        assert result[0]["race_id"] == "test-race-2024"
        assert result[0]["text"] == "Cached test content"

        mock_collection_ref.where.assert_called_once_with("race_id", "==", "test-race-2024")

    @pytest.mark.asyncio
    @patch("firestore_cache.firestore.AsyncClient")
    async def test_clear_cache(self, mock_client_class):
        """Test cache clearing."""
        # Mock Firestore client
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_query = AsyncMock()
        mock_batch = AsyncMock()
        mock_doc = MagicMock()

        mock_client_class.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_collection_ref.where.return_value = mock_query
        mock_query.get.return_value = [mock_doc]
        mock_client.batch.return_value = mock_batch

        cache = FirestoreCache()

        # Test clearing specific race
        result = await cache.clear_cache("test-race-2024")

        # Assertions
        assert result is True
        mock_collection_ref.where.assert_called_once_with("race_id", "==", "test-race-2024")
        mock_batch.delete.assert_called_once()
        mock_batch.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("firestore_cache.firestore.AsyncClient")
    async def test_get_cache_stats(self, mock_client_class):
        """Test cache statistics."""
        # Mock Firestore client
        mock_client = AsyncMock()
        mock_collection_ref = AsyncMock()
        mock_query = AsyncMock()

        # Mock document data
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "race_id": "test-race-2024",
            "text": "Test content with multiple words here",
        }

        mock_client_class.return_value = mock_client
        mock_client.collection.return_value = mock_collection_ref
        mock_collection_ref.where.return_value = mock_query
        mock_query.get.return_value = [mock_doc]

        cache = FirestoreCache()

        # Test stats for specific race
        result = await cache.get_cache_stats("test-race-2024")

        # Assertions
        assert result["race_id"] == "test-race-2024"
        assert result["total_items"] == 1
        assert result["total_text_chars"] > 0
        assert result["avg_text_length"] > 0

    def test_serialize_metadata(self):
        """Test metadata serialization."""
        cache = FirestoreCache()

        # Test complex metadata
        metadata = {
            "simple_string": "test",
            "simple_int": 123,
            "simple_float": 45.6,
            "simple_bool": True,
            "simple_none": None,
            "datetime_obj": datetime.utcnow(),
            "simple_list": ["a", "b", "c"],
            "mixed_list": ["a", 1, True],
            "nested_dict": {"key": "value", "number": 42},
            "complex_object": {"nested": {"deep": "value"}},
        }

        result = cache._serialize_metadata(metadata)

        # Assertions
        assert result["simple_string"] == "test"
        assert result["simple_int"] == 123
        assert result["simple_float"] == 45.6
        assert result["simple_bool"] is True
        assert result["simple_none"] is None
        assert isinstance(result["datetime_obj"], str)  # Should be ISO format
        assert result["simple_list"] == ["a", "b", "c"]
        assert isinstance(result["mixed_list"], str)  # Should be converted to string
        assert isinstance(result["nested_dict"], dict)
        assert result["nested_dict"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_cache_content_missing_checksum(self):
        """Test handling content with missing checksum."""
        cache = FirestoreCache()

        # Create content without checksum
        content = self.create_test_content()
        content.metadata.pop("content_checksum", None)  # Remove checksum

        # Mock client to avoid actual Firestore calls
        with patch("firestore_cache.firestore.AsyncClient"):
            result = await cache.cache_content("test-race", [content])

            # Should return False since no content was cached
            assert result is False

    @pytest.mark.asyncio
    @patch("firestore_cache.firestore.AsyncClient")
    async def test_cache_error_handling(self, mock_client_class):
        """Test error handling during caching."""
        # Make the client raise an exception
        mock_client_class.side_effect = Exception("Firestore connection error")

        cache = FirestoreCache()
        test_content = [self.create_test_content()]

        result = await cache.cache_content("test-race", test_content)

        # Should return False on error
        assert result is False


# Manual test function for local testing (requires actual Firestore setup)
async def manual_test_with_emulator():
    """Manual test function for use with Firestore emulator."""
    print("Starting manual Firestore cache test...")

    # Set up for Firestore emulator (if running)
    os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"

    cache = FirestoreCache(project_id="test-project", collection_name="test_cache")

    try:
        # Create test content
        source = Source(
            url="https://example.com/test",
            source_type=SourceType.WEBSITE,
            title="Test Article",
            description="Test description",
        )

        content = ExtractedContent(
            source=source,
            text="This is test content for manual verification of Firestore caching.",
            metadata={
                "content_checksum": "test123hash456",
                "word_count": 10,
                "extraction_method": "manual_test",
                "usefulness_score": 0.9,
                "is_useful": True,
                "test_timestamp": datetime.utcnow(),
            },
            extraction_timestamp=datetime.utcnow(),
            word_count=10,
            language="en",
        )

        print("Caching test content...")
        success = await cache.cache_content("manual-test-race-2024", [content])
        print(f"Cache result: {success}")

        print("Retrieving cached content...")
        cached = await cache.get_cached_content("manual-test-race-2024")
        print(f"Retrieved {len(cached)} items")

        if cached:
            print(f"Sample cached item: {cached[0]['source_url']}")

        print("Getting cache stats...")
        stats = await cache.get_cache_stats("manual-test-race-2024")
        print(f"Cache stats: {stats}")

        print("Clearing test cache...")
        await cache.clear_cache("manual-test-race-2024")
        print("Cache cleared")

    except Exception as e:
        print(f"Error during manual test: {e}")
    finally:
        await cache.close()
        print("Manual test completed")


if __name__ == "__main__":
    # Run manual test (requires Firestore emulator)
    asyncio.run(manual_test_with_emulator())
