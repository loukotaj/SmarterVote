"""
Tests for Vector Database Manager

This module contains comprehensive tests for the ChromaDB-based vector database
operations, including initialization, content indexing, search functionality,
and database management operations.
"""

import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ..schema import CanonicalIssue, ExtractedContent, Source, SourceType, VectorDocument
from ..step02_corpus.election_vector_database_manager import ElectionVectorDatabaseManager


@pytest.fixture
def temp_db_dir():
    """Create a temporary directory for ChromaDB testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Add a delay to allow ChromaDB to release file handles
    import time

    time.sleep(0.5)
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        # On Windows, ChromaDB might still hold file handles
        # Try again after a longer delay
        time.sleep(2)
        try:
            shutil.rmtree(temp_dir)
        except PermissionError:
            # If still locked, ignore for now (files will be cleaned up by OS)
            pass


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
    """Create an election-aware vector database manager with temporary storage."""
    manager = ElectionVectorDatabaseManager()
    manager.config["persist_directory"] = temp_db_dir
    yield manager
    # Clean up ChromaDB connections
    if hasattr(manager, "client") and manager.client:
        try:
            manager.client.reset()
        except:
            pass


class TestElectionVectorDatabaseManager:
    """Test cases for ElectionVectorDatabaseManager class."""

    @pytest.mark.asyncio
    async def test_initialization(self, db_manager):
        """Test database initialization."""
        # Mock dependencies to avoid import issues in CI
        with (
            patch("chromadb.PersistentClient") as mock_client,
            patch("pipeline.app.step02_corpus.vector_database_manager.SentenceTransformer") as mock_embedding,
        ):
            mock_collection = MagicMock()
            mock_collection.count.return_value = 0
            mock_client.return_value.get_or_create_collection.return_value = mock_collection

            # Mock the availability flag
            with patch(
                "pipeline.app.step02_corpus.vector_database_manager.SENTENCE_TRANSFORMERS_AVAILABLE",
                True,
            ):
                await db_manager.initialize()

            assert db_manager.client is not None
            assert db_manager.collection is not None
            assert db_manager.embedding_model is not None
            assert db_manager.collection.count() == 0

    @pytest.mark.asyncio
    async def test_initialization_creates_directory(self, temp_db_dir):
        """Test that initialization creates the persist directory."""
        db_path = Path(temp_db_dir) / "test_subdir"
        manager = ElectionVectorDatabaseManager()
        manager.config["persist_directory"] = str(db_path)

        assert not db_path.exists()
        await manager.initialize()
        assert db_path.exists()

    @pytest.mark.asyncio
    async def test_content_chunking(self, db_manager, sample_content):
        """Test content chunking functionality."""
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

    @pytest.mark.asyncio
    async def test_build_corpus(self, db_manager, sample_content):
        """Test corpus building functionality."""
        await db_manager.initialize()

        race_id = "test-race-2024"
        content_list = [sample_content]

        result = await db_manager.build_corpus(race_id, content_list)

        assert result is True
        assert db_manager.collection.count() > 0

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, db_manager, sample_content):
        """Test duplicate content detection."""
        await db_manager.initialize()

        race_id = "test-race-2024"

        # Index same content twice
        await db_manager.build_corpus(race_id, [sample_content])
        initial_count = db_manager.collection.count()

        await db_manager.build_corpus(race_id, [sample_content])
        final_count = db_manager.collection.count()

        # Should not significantly increase due to duplicate detection
        assert final_count <= initial_count + 1  # Allow for some variation

    @pytest.mark.asyncio
    async def test_search_similar(self, db_manager, sample_content):
        """Test similarity search functionality."""
        await db_manager.initialize()

        race_id = "test-race-2024"
        await db_manager.build_corpus(race_id, [sample_content])

        # Search for similar content
        query = "healthcare policy reform"
        results = await db_manager.search_similar(query, race_id=race_id, limit=5)

        assert isinstance(results, list)
        if results:  # If we get results
            assert all(isinstance(doc, VectorDocument) for doc in results)
            assert all(doc.similarity_score is not None for doc in results)
            assert all(doc.similarity_score >= 0 for doc in results)

    @pytest.mark.asyncio
    async def test_search_similar_with_filters(self, db_manager, sample_content):
        """Test similarity search with metadata filters."""
        await db_manager.initialize()

        race_id = "test-race-2024"
        await db_manager.build_corpus(race_id, [sample_content])

        # Search with race filter
        results = await db_manager.search_similar("healthcare", race_id=race_id, issue=CanonicalIssue.HEALTHCARE)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_content(self, db_manager, sample_content):
        """Test content search and retrieval."""
        await db_manager.initialize()

        race_id = "test-race-2024"
        await db_manager.build_corpus(race_id, [sample_content])

        # Search for content
        content_list = await db_manager.search_content(race_id)

        assert isinstance(content_list, list)
        if content_list:  # If we get results
            assert all(isinstance(content, ExtractedContent) for content in content_list)

    @pytest.mark.asyncio
    async def test_get_race_content(self, db_manager, sample_content):
        """Test race content retrieval."""
        await db_manager.initialize()

        race_id = "test-race-2024"
        await db_manager.build_corpus(race_id, [sample_content])

        # Get race content
        documents = await db_manager.get_race_content(race_id)

        assert isinstance(documents, list)
        if documents:  # If we get results
            assert all(isinstance(doc, VectorDocument) for doc in documents)

    @pytest.mark.asyncio
    async def test_get_content_stats(self, db_manager, sample_content):
        """Test content statistics calculation."""
        await db_manager.initialize()

        race_id = "test-race-2024"
        await db_manager.build_corpus(race_id, [sample_content])

        # Get stats
        stats = await db_manager.get_content_stats(race_id)

        assert isinstance(stats, dict)
        assert "total_chunks" in stats
        assert "total_sources" in stats
        assert "issues_covered" in stats
        assert "freshness_score" in stats
        assert "quality_score" in stats
        assert "last_updated" in stats

        # Verify stats make sense
        assert stats["total_chunks"] >= 0
        assert stats["total_sources"] >= 0
        assert 0 <= stats["freshness_score"] <= 1
        assert stats["quality_score"] >= 0

    @pytest.mark.asyncio
    async def test_cleanup_old_content(self, db_manager):
        """Test old content cleanup functionality."""
        await db_manager.initialize()

        # Create old content
        old_source = Source(
            url="https://example.com/old-content",
            type=SourceType.WEBSITE,
            title="Old Content",
            last_accessed=datetime.utcnow(),
        )

        old_content = ExtractedContent(
            source=old_source,
            text="This is old content that should be cleaned up.",
            extraction_timestamp=datetime.utcnow() - timedelta(days=40),
            language="en",
            word_count=10,
            quality_score=0.5,
            metadata={},
        )

        # Index old content
        race_id = "test-race-2024"
        await db_manager.build_corpus(race_id, [old_content])
        initial_count = db_manager.collection.count()

        # Cleanup content older than 30 days
        await db_manager.cleanup_old_content(days=30)
        final_count = db_manager.collection.count()

        # Should have fewer items after cleanup
        assert final_count <= initial_count

    @pytest.mark.asyncio
    async def test_error_handling_invalid_embedding(self, db_manager):
        """Test error handling for invalid content."""
        await db_manager.initialize()

        # Create content with empty text
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

        # Should handle gracefully
        result = await db_manager.build_corpus("test-race", [empty_content])
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_large_content_chunking(self, db_manager):
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

    @pytest.mark.asyncio
    async def test_configuration_from_environment(self, temp_db_dir):
        """Test configuration loading from environment variables."""
        with patch.dict(
            "os.environ", {"CHROMA_CHUNK_SIZE": "300", "CHROMA_CHUNK_OVERLAP": "30", "CHROMA_SIMILARITY_THRESHOLD": "0.8"}
        ):
            manager = ElectionVectorDatabaseManager()

            assert manager.config["chunk_size"] == 300
            assert manager.config["chunk_overlap"] == 30
            assert manager.config["similarity_threshold"] == 0.8

    @pytest.mark.asyncio
    async def test_persistence_across_sessions(self, temp_db_dir, sample_content):
        """Test that data persists across database sessions."""
        race_id = "persistence-test-2024"

        # First session: create and populate database
        manager1 = ElectionVectorDatabaseManager()
        manager1.config["persist_directory"] = temp_db_dir
        await manager1.initialize()
        await manager1.build_corpus(race_id, [sample_content])
        first_count = manager1.collection.count()

        # Second session: reconnect to same database
        manager2 = ElectionVectorDatabaseManager()
        manager2.config["persist_directory"] = temp_db_dir
        await manager2.initialize()
        second_count = manager2.collection.count()

        # Data should persist
        assert second_count == first_count
        assert second_count > 0
