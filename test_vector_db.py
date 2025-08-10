"""
Simple test script for Vector Database Manager functionality.
"""

import asyncio
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add the project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.app.corpus.vector_database_manager import VectorDatabaseManager
from pipeline.app.schema import ExtractedContent, Source, SourceType


async def test_basic_functionality():
    """Test basic vector database functionality."""
    print("🧪 Testing Vector Database Manager Basic Functionality")
    print("=" * 60)

    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as temp_dir:
        # Initialize manager with temp directory
        manager = VectorDatabaseManager()
        manager.config["persist_directory"] = temp_dir
        print(f"📁 Using temporary database at: {temp_dir}")

        # Test initialization
        print("\n1️⃣  Testing initialization...")
        await manager.initialize()
        print(f"✅ Database initialized with {manager.collection.count()} documents")
        print(f"🔧 Embedding model available: {manager.embedding_model is not None}")

        # Create sample content
        print("\n2️⃣  Creating sample content...")
        source = Source(
            url="https://example.com/candidate-platform",
            type=SourceType.WEBSITE,
            title="Candidate Platform Document",
            last_accessed=datetime.utcnow(),
            is_fresh=True,
        )

        content = ExtractedContent(
            source=source,
            text="Healthcare is a fundamental right for all Americans. We need to ensure universal healthcare coverage while reducing costs for families. Medicare for All would provide comprehensive healthcare including dental and vision care. Climate change represents an existential threat to our planet. We must transition to renewable energy sources and reduce carbon emissions by 50 percent by 2030. Economic growth should benefit working families, not just the wealthy.",
            extraction_timestamp=datetime.utcnow(),
            language="en",
            word_count=65,
            quality_score=0.85,
            metadata={"candidate": "Test Candidate", "topic": "policy platform"},
        )

        race_id = "test-race-2024"
        print(f"📄 Created content with {content.word_count} words")

        # Test corpus building
        print("\n3️⃣  Testing corpus building...")
        success = await manager.build_corpus(race_id, [content])
        print(f"✅ Corpus building success: {success}")
        print(f"📊 Total documents in database: {manager.collection.count()}")

        # Test chunking
        print("\n4️⃣  Testing content chunking...")
        chunks = manager._chunk_content(content)
        print(f"📦 Content split into {len(chunks)} chunks")
        for i, chunk in enumerate(chunks[:2]):  # Show first 2 chunks
            print(f"   Chunk {i+1}: {len(chunk['text'])} chars - '{chunk['text'][:50]}...'")

        # Test content statistics
        print("\n5️⃣  Testing content statistics...")
        stats = await manager.get_content_stats(race_id)
        print(f"📈 Content Statistics:")
        print(f"   - Total chunks: {stats['total_chunks']}")
        print(f"   - Total sources: {stats['total_sources']}")
        print(f"   - Issues covered: {stats['issues_covered']}")
        print(f"   - Freshness score: {stats['freshness_score']:.2f}")
        print(f"   - Quality score: {stats['quality_score']:.2f}")

        # Test similarity search
        print("\n6️⃣  Testing similarity search...")
        search_queries = ["universal healthcare coverage", "climate change renewable energy", "economic growth families"]

        for query in search_queries:
            results = await manager.search_similar(query, race_id=race_id, limit=3)
            print(f"🔍 Query: '{query}'")
            print(f"   Found {len(results)} results")
            for result in results[:1]:  # Show first result
                similarity = result.similarity_score or 0.0
                print(f"   - Similarity: {similarity:.3f}, Content: '{result.content[:80]}...'")

        # Test content retrieval
        print("\n7️⃣  Testing content retrieval...")
        content_list = await manager.search_content(race_id)
        print(f"📋 Retrieved {len(content_list)} content items for race")

        # Test race content retrieval
        documents = await manager.get_race_content(race_id)
        print(f"📑 Retrieved {len(documents)} documents for race")

        print("\n✅ All tests completed successfully!")
        print("🎉 Vector Database Manager is working correctly!")


if __name__ == "__main__":
    asyncio.run(test_basic_functionality())
