"""
Basic functional test for Vector Database Manager core functionality

This test validates the basic functionality without requiring full embedding models
which may have dependency conflicts during initial setup.
"""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ..schema import CanonicalIssue, ExtractedContent, Source, SourceType
from ..step05_corpus.vector_database_manager import VectorDatabaseManager


@pytest.fixture
def temp_db_dir():
    """Create a temporary directory for ChromaDB testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_content():
    """Create sample extracted content for testing."""
    source = Source(
        url="https://example.com/candidate-info",
        type=SourceType.WEBSITE,
        title="Candidate Information Page",
        last_accessed=datetime.utcnow(),
        is_fresh=True,
    )

    return ExtractedContent(
        source=source,
        text="This is a sample political statement about healthcare reform. The candidate supports universal healthcare coverage and believes in reducing prescription drug costs. They also advocate for mental health services expansion.",
        extraction_timestamp=datetime.utcnow(),
        language="en",
        word_count=35,
        quality_score=0.8,
        metadata={"issue": "Healthcare", "candidate": "John Doe"},
    )


@pytest.fixture
def db_manager(temp_db_dir):
    """Create a vector database manager with temporary storage."""
    manager = VectorDatabaseManager()
    manager.config["persist_directory"] = temp_db_dir
    return manager


class TestVectorDatabaseManagerBasic:
    """Basic tests for VectorDatabaseManager that don't require full initialization."""

    def test_configuration_initialization(self, db_manager):
        """Test that the manager initializes with proper configuration."""
        assert db_manager.collection_name == "smartervote_content"
        assert db_manager.client is None
        assert db_manager.collection is None
        assert db_manager.embedding_model is None

        # Check default configuration
        assert db_manager.config["chunk_size"] == 500
        assert db_manager.config["chunk_overlap"] == 50
        assert db_manager.config["embedding_model"] == "all-MiniLM-L6-v2"
        assert db_manager.config["similarity_threshold"] == 0.7

    def test_configuration_from_environment(self, temp_db_dir):
        """Test configuration loading from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "CHROMA_CHUNK_SIZE": "300",
                "CHROMA_CHUNK_OVERLAP": "30",
                "CHROMA_SIMILARITY_THRESHOLD": "0.8",
                "CHROMA_PERSIST_DIR": temp_db_dir,
            },
        ):
            manager = VectorDatabaseManager()

            assert manager.config["chunk_size"] == 300
            assert manager.config["chunk_overlap"] == 30
            assert manager.config["similarity_threshold"] == 0.8
            assert manager.config["persist_directory"] == temp_db_dir

    def test_content_chunking_basic(self, db_manager, sample_content):
        """Test basic content chunking functionality."""
        chunks = db_manager._chunk_content(sample_content)

        assert len(chunks) > 0
        assert all(chunk["text"] for chunk in chunks)
        assert all(chunk["id"] for chunk in chunks)
        assert all("metadata" in chunk for chunk in chunks)

        # Check metadata preservation
        for chunk in chunks:
            metadata = chunk["metadata"]
            assert metadata["source_url"] == str(sample_content.source.url)
            assert metadata["source_type"] == sample_content.source.type.value
            assert metadata["language"] == sample_content.language

    def test_sentence_splitting(self, db_manager):
        """Test sentence splitting functionality."""
        text = "First sentence. Second sentence! Third sentence? Fourth sentence."
        sentences = db_manager._split_into_sentences(text)

        assert len(sentences) == 4
        assert sentences[0] == "First sentence."
        assert sentences[1] == "Second sentence!"
        assert sentences[2] == "Third sentence?"
        assert sentences[3] == "Fourth sentence."

    def test_overlap_sentences(self, db_manager):
        """Test sentence overlap functionality."""
        sentences = ["Short.", "Another short.", "This is a longer sentence.", "Final."]
        overlap = db_manager._get_overlap_sentences(sentences, 10)

        # Should include sentences that fit within word limit
        assert len(overlap) > 0
        total_words = sum(len(s.split()) for s in overlap)
        assert total_words <= 10

    def test_chunk_data_creation(self, db_manager, sample_content):
        """Test chunk data structure creation."""
        chunk_text = "This is a test chunk of content."
        chunk_index = 0

        chunk_data = db_manager._create_chunk_data(sample_content, chunk_text, chunk_index)

        assert chunk_data["id"] is not None
        assert chunk_data["text"] == chunk_text
        assert chunk_data["metadata"]["chunk_index"] == chunk_index
        assert chunk_data["metadata"]["word_count"] == len(chunk_text.split())
        assert chunk_data["metadata"]["source_url"] == str(sample_content.source.url)

    def test_large_content_chunking(self, db_manager):
        """Test chunking of large content."""
        # Create large content
        large_text = " ".join(["This is sentence number {}.".format(i) for i in range(200)])

        large_source = Source(
            url="https://example.com/large-content",
            type=SourceType.WEBSITE,
            title="Large Content",
            last_accessed=datetime.utcnow(),
        )

        large_content = ExtractedContent(
            source=large_source,
            text=large_text,
            extraction_timestamp=datetime.utcnow(),
            language="en",
            word_count=len(large_text.split()),
            quality_score=0.7,
            metadata={},
        )

        chunks = db_manager._chunk_content(large_content)

        # Should create multiple chunks
        assert len(chunks) > 1

        # Each chunk should be reasonable size
        for chunk in chunks:
            words = chunk["text"].split()
            assert len(words) <= db_manager.config["chunk_size"] + 100  # Allow some overlap

    def test_empty_content_handling(self, db_manager):
        """Test handling of empty content."""
        empty_source = Source(
            url="https://example.com/empty",
            type=SourceType.WEBSITE,
            title="Empty Content",
            last_accessed=datetime.utcnow(),
        )

        empty_content = ExtractedContent(
            source=empty_source,
            text="",  # Empty text
            extraction_timestamp=datetime.utcnow(),
            language="en",
            word_count=0,
            quality_score=0.0,
            metadata={},
        )

        chunks = db_manager._chunk_content(empty_content)
        assert len(chunks) == 0  # Should return empty list for empty content

    def test_very_short_content_handling(self, db_manager):
        """Test handling of very short content."""
        short_source = Source(
            url="https://example.com/short",
            type=SourceType.WEBSITE,
            title="Short Content",
            last_accessed=datetime.utcnow(),
        )

        short_content = ExtractedContent(
            source=short_source,
            text="Short text",  # Very short text
            extraction_timestamp=datetime.utcnow(),
            language="en",
            word_count=2,
            quality_score=0.5,
            metadata={},
        )

        chunks = db_manager._chunk_content(short_content)
        # Should either return no chunks (if below minimum) or one small chunk
        assert len(chunks) <= 1

    @pytest.mark.asyncio
    async def test_initialization_creates_directory(self, temp_db_dir):
        """Test that initialization creates the persist directory."""
        db_path = Path(temp_db_dir) / "test_subdir"
        manager = VectorDatabaseManager()
        manager.config["persist_directory"] = str(db_path)

        assert not db_path.exists()

        # Mock the ChromaDB and embedding model initialization to avoid dependency issues
        with (
            patch("chromadb.PersistentClient") as mock_client,
            patch("pipeline.app.step05_corpus.vector_database_manager.SentenceTransformer") as mock_embedding,
        ):
            mock_collection = MagicMock()
            mock_collection.count.return_value = 0
            mock_client.return_value.get_or_create_collection.return_value = mock_collection

            # Mock the availability flag
            with patch("pipeline.app.step05_corpus.vector_database_manager.SENTENCE_TRANSFORMERS_AVAILABLE", True):
                await manager.initialize()

            assert db_path.exists()
            assert manager.client is not None
            assert manager.collection is not None
            assert manager.embedding_model is not None

    def test_config_validation(self, db_manager):
        """Test configuration validation."""
        # Test that configuration values are reasonable
        assert db_manager.config["chunk_size"] > 0
        assert db_manager.config["chunk_overlap"] >= 0
        assert db_manager.config["chunk_overlap"] < db_manager.config["chunk_size"]
        assert 0 <= db_manager.config["similarity_threshold"] <= 1
        assert db_manager.config["max_results"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
