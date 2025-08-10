"""
Vector Database Manager for SmarterVote Pipeline

This module handles ChromaDB operations for content indexing and similarity search.
Implements the corpus-first approach by building a comprehensive vector database
of electoral content before generating summaries.

IMPLEMENTATION STATUS:
✅ ChromaDB client initialization and configuration
✅ Document chunking strategies with sentence boundary preservation
✅ Vector embedding and search functionality (all-MiniLM-L6-v2)
✅ Metadata filtering for race-specific and issue-specific searches
✅ Duplicate detection based on content similarity
✅ Persistence layer configured with SQLite storage
✅ Content statistics and analytics
✅ Database cleanup and maintenance operations

FUTURE ENHANCEMENTS:
- [ ] Support for incremental index updates
- [ ] Advanced semantic search with query expansion
- [ ] Document clustering for topic discovery
- [ ] Support for multilingual content indexing
- [ ] Backup/restore functionality for production
- [ ] Index optimization and performance tuning
- [ ] Advanced analytics and search quality metrics
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

from ..schema import CanonicalIssue, ExtractedContent, Source, SourceType, VectorDocument

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    # Will log warning after logger is defined


class VectorDatabaseManager:
    """Manager for vector database operations using ChromaDB."""

    def __init__(self):
        # ChromaDB client and collection
        self.collection_name = "smartervote_content"
        self.client = None
        self.collection = None
        self.embedding_model = None

        # Configuration from environment or defaults
        self.config = {
            "chunk_size": int(os.getenv("CHROMA_CHUNK_SIZE", "500")),  # words per chunk
            "chunk_overlap": int(os.getenv("CHROMA_CHUNK_OVERLAP", "50")),  # word overlap between chunks
            "embedding_model": os.getenv("CHROMA_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),  # Sentence transformer model
            "similarity_threshold": float(os.getenv("CHROMA_SIMILARITY_THRESHOLD", "0.7")),
            "max_results": int(os.getenv("CHROMA_MAX_RESULTS", "100")),
            "persist_directory": os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db"),
        }

    async def initialize(self):
        """
        Initialize ChromaDB client and collection.
        """
        logger.info("Initializing vector database...")

        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers not available, using default ChromaDB embedding")

        try:
            # Ensure persist directory exists
            persist_dir = Path(self.config["persist_directory"])
            persist_dir.mkdir(parents=True, exist_ok=True)

            # Initialize ChromaDB client with persistence
            self.client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=Settings(
                    allow_reset=True,
                    anonymized_telemetry=False,
                ),
            )

            # Initialize embedding model if available
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.info(f"Loading embedding model: {self.config['embedding_model']}")
                self.embedding_model = SentenceTransformer(self.config["embedding_model"])
            else:
                self.embedding_model = None
                logger.info("Using ChromaDB default embedding function")

            # Create or get collection with embedding function
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name, metadata={"description": "SmarterVote electoral content corpus"}
            )

            logger.info(f"Vector database initialized with {self.collection.count()} existing documents")

        except Exception as e:
            logger.error(f"Failed to initialize vector database: {e}")
            raise

    async def build_corpus(self, race_id: str, content: List[ExtractedContent]) -> bool:
        """
        Index extracted content in the vector database.

        Args:
            race_id: The race ID for grouping content
            content: List of extracted content to index

        Returns:
            True if indexing successful

        TODO:
        - [ ] Implement document chunking for large texts
        - [ ] Add duplicate detection based on content similarity
        - [ ] Support for batch indexing operations
        - [ ] Add indexing progress tracking
        """
        logger.info(f"Indexing {len(content)} content items for race {race_id}")

        if not self.client:
            await self.initialize()

        # Process each content item
        indexed_count = 0
        for item in content:
            try:
                chunks = self._chunk_content(item)
                for chunk in chunks:
                    success = await self._index_chunk(race_id, chunk)
                    if success:
                        indexed_count += 1
            except Exception as e:
                logger.error(f"Failed to index content from {item.source.url}: {e}")

        logger.info(f"Successfully indexed {indexed_count} chunks for race {race_id}")
        return indexed_count > 0

    def _chunk_content(self, content: ExtractedContent) -> List[Dict[str, Any]]:
        """
        Split content into chunks for indexing with smart sentence boundary preservation.
        """
        text = content.text.strip()
        if not text:
            return []

        # Split into sentences for better boundary preservation
        sentences = self._split_into_sentences(text)
        chunks = []
        current_chunk = []
        current_word_count = 0

        chunk_size = self.config["chunk_size"]
        overlap = self.config["chunk_overlap"]

        for sentence in sentences:
            sentence_words = sentence.split()
            sentence_word_count = len(sentence_words)

            # If adding this sentence would exceed chunk size, create a chunk
            if current_word_count > 0 and current_word_count + sentence_word_count > chunk_size:
                chunk_text = " ".join(current_chunk)
                if len(chunk_text.strip()) >= 50:  # Only create chunks with meaningful content
                    chunks.append(self._create_chunk_data(content, chunk_text, len(chunks)))

                # Start new chunk with overlap
                overlap_sentences = self._get_overlap_sentences(current_chunk, overlap)
                current_chunk = overlap_sentences + [sentence]
                current_word_count = len(" ".join(current_chunk).split())
            else:
                current_chunk.append(sentence)
                current_word_count += sentence_word_count

        # Add final chunk if it has content
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text.strip()) >= 50:
                chunks.append(self._create_chunk_data(content, chunk_text, len(chunks)))

        logger.debug(f"Split content into {len(chunks)} chunks")
        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using simple heuristics."""
        import re

        # Simple sentence splitting on periods, exclamation marks, and question marks
        # followed by whitespace and capital letters
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [s.strip() for s in sentences if s.strip()]

    def _get_overlap_sentences(self, sentences: List[str], overlap_words: int) -> List[str]:
        """Get the last few sentences that fit within the overlap word limit."""
        overlap_sentences = []
        word_count = 0

        for sentence in reversed(sentences):
            sentence_words = len(sentence.split())
            if word_count + sentence_words > overlap_words:
                break
            overlap_sentences.insert(0, sentence)
            word_count += sentence_words

        return overlap_sentences

    def _create_chunk_data(self, content: ExtractedContent, chunk_text: str, chunk_index: int) -> Dict[str, Any]:
        """Create chunk data structure with metadata."""
        # Generate unique chunk ID
        chunk_id = hashlib.md5(f"{content.source.url}_{chunk_index}_{chunk_text[:100]}".encode()).hexdigest()

        return {
            "id": chunk_id,
            "text": chunk_text,
            "metadata": {
                "source_url": str(content.source.url),
                "source_type": content.source.type.value,
                "source_title": content.source.title,
                "chunk_index": chunk_index,
                "word_count": len(chunk_text.split()),
                "extraction_timestamp": content.extraction_timestamp.isoformat(),
                "language": content.language or "unknown",
                "is_fresh": getattr(content.source, "is_fresh", False),
                "quality_score": getattr(content, "quality_score", 0.0),
                **content.metadata,
            },
        }

    async def _index_chunk(self, race_id: str, chunk: Dict[str, Any]) -> bool:
        """
        Index a single chunk in the vector database using content hash for duplicate detection.
        """
        try:
            if not self.collection:
                await self.initialize()

            # Add race_id to metadata
            chunk["metadata"]["race_id"] = race_id

            # Compute content hash for duplicate detection
            content_hash = hashlib.md5(chunk["text"].encode()).hexdigest()
            chunk["metadata"]["content_hash"] = content_hash

            # Check for duplicate by content hash
            existing = self.collection.get(where={"$and": [{"race_id": race_id}, {"content_hash": content_hash}]})
            if existing.get("ids"):
                logger.debug(f"Skipping duplicate chunk {chunk['id']} (hash match)")
                return True

            # Add to ChromaDB collection (using default embedding)
            self.collection.add(documents=[chunk["text"]], metadatas=[chunk["metadata"]], ids=[chunk["id"]])

            logger.debug(f"Indexed chunk {chunk['id']} for race {race_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to index chunk {chunk['id']}: {e}")
            return False

    async def search_similar(
        self,
        query: str,
        race_id: Optional[str] = None,
        issue: Optional[CanonicalIssue] = None,
        limit: int = 10,
    ) -> List[VectorDocument]:
        """
        Search for similar content in the vector database.
        """
        logger.info(f"Searching for similar content: '{query[:50]}...'")

        if not self.client or not self.collection:
            await self.initialize()

        # Build metadata filters
        where_clause = {}
        if race_id:
            where_clause["race_id"] = race_id
        if issue:
            where_clause["issue"] = issue.value

        try:
            if self.embedding_model:
                # Generate query embedding and use vector search
                query_embedding = self.embedding_model.encode(query).tolist()

                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    where=where_clause if where_clause else None,
                    include=["documents", "metadatas", "distances"],
                )
            else:
                # Use text-based search if no embedding model
                results = self.collection.query(
                    query_texts=[query],
                    n_results=limit,
                    where=where_clause if where_clause else None,
                    include=["documents", "metadatas", "distances"],
                )

            # Convert to VectorDocument objects
            documents = []
            if results["documents"] and len(results["documents"]) > 0:
                for i, doc_text in enumerate(results["documents"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 1.0
                    similarity = max(0.0, 1.0 - distance)  # Convert distance to similarity
                    doc_id = results["ids"][0][i] if results["ids"] else f"doc_{i}"

                    # Create Source object from metadata
                    source = Source(
                        url=metadata.get("source_url", "https://unknown.com"),
                        type=SourceType(metadata.get("source_type", "website")),
                        title=metadata.get("source_title", "Unknown"),
                        last_accessed=datetime.utcnow(),
                    )

                    doc = VectorDocument(
                        id=doc_id,
                        content=doc_text,
                        metadata=metadata,
                        similarity_score=similarity,
                        source=source,
                    )
                    documents.append(doc)

            # Filter by similarity threshold only if using embeddings
            if self.embedding_model:
                documents = [doc for doc in documents if doc.similarity_score >= self.config["similarity_threshold"]]

            logger.info(f"Found {len(documents)} similar documents" + (f" above threshold" if self.embedding_model else ""))
            return documents

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def search_content(self, race_id: str, issue: Optional[CanonicalIssue] = None) -> List[ExtractedContent]:
        """
        Search and retrieve content for summarization.
        """
        logger.info(f"Searching content for race {race_id}" + (f" and issue {issue.value}" if issue else ""))

        if not self.client or not self.collection:
            await self.initialize()

        try:
            # Build metadata filters
            where_clause = {"race_id": race_id}
            if issue:
                where_clause["issue"] = issue.value

            # Get all content for the race/issue
            results = self.collection.get(where=where_clause, include=["documents", "metadatas"])

            # Convert to ExtractedContent objects
            content_list = []
            if results["documents"]:
                for i, doc_text in enumerate(results["documents"]):
                    metadata = results["metadatas"][i] if results["metadatas"] else {}

                    # Reconstruct Source object
                    source = Source(
                        url=metadata.get("source_url", "https://unknown.com"),
                        type=SourceType(metadata.get("source_type", "website")),
                        title=metadata.get("source_title", "Unknown"),
                        last_accessed=datetime.utcnow(),
                        is_fresh=metadata.get("is_fresh", False),
                    )

                    # Create ExtractedContent object
                    content = ExtractedContent(
                        source=source,
                        text=doc_text,
                        extraction_timestamp=datetime.fromisoformat(
                            metadata.get("extraction_timestamp", datetime.utcnow().isoformat())
                        ),
                        language=metadata.get("language", "en"),
                        word_count=metadata.get("word_count", len(doc_text.split())),
                        quality_score=metadata.get("quality_score", 0.0),
                        metadata={
                            k: v
                            for k, v in metadata.items()
                            if k
                            not in [
                                "source_url",
                                "source_type",
                                "source_title",
                                "extraction_timestamp",
                                "language",
                                "word_count",
                                "quality_score",
                                "is_fresh",
                            ]
                        },
                    )
                    content_list.append(content)

            logger.info(f"Retrieved {len(content_list)} content items")
            return content_list

        except Exception as e:
            logger.error(f"Content search failed: {e}")
            return []

    async def get_race_content(self, race_id: str, issue: Optional[CanonicalIssue] = None) -> List[VectorDocument]:
        """
        Get all content for a specific race, optionally filtered by issue.
        """
        logger.info(f"Retrieving content for race {race_id}")

        if not self.client or not self.collection:
            await self.initialize()

        where_clause = {"race_id": race_id}
        if issue:
            where_clause["issue"] = issue.value

        try:
            # Get content from ChromaDB
            results = self.collection.get(where=where_clause, include=["documents", "metadatas"])

            # Convert to VectorDocument objects
            documents = []
            if results["documents"]:
                for i, doc_text in enumerate(results["documents"]):
                    metadata = results["metadatas"][i] if results["metadatas"] else {}
                    doc_id = results["ids"][i] if results["ids"] else f"doc_{i}"

                    # Create Source object from metadata
                    source = Source(
                        url=metadata.get("source_url", "https://unknown.com"),
                        type=SourceType(metadata.get("source_type", "website")),
                        title=metadata.get("source_title", "Unknown"),
                        last_accessed=datetime.utcnow(),
                    )

                    doc = VectorDocument(
                        id=doc_id,
                        content=doc_text,
                        metadata=metadata,
                        similarity_score=None,  # No similarity for direct retrieval
                        source=source,
                    )
                    documents.append(doc)

            logger.info(f"Retrieved {len(documents)} documents for race {race_id}")
            return documents

        except Exception as e:
            logger.error(f"Failed to retrieve race content: {e}")
            return []

    async def get_content_stats(self, race_id: str) -> Dict[str, Any]:
        """
        Get statistics about indexed content for a race.
        """
        if not self.client or not self.collection:
            await self.initialize()

        try:
            # Get all content for the race
            results = self.collection.get(where={"race_id": race_id}, include=["metadatas"])

            if not results["metadatas"]:
                return {
                    "total_chunks": 0,
                    "total_sources": 0,
                    "issues_covered": [],
                    "freshness_score": 0.0,
                    "quality_score": 0.0,
                    "last_updated": datetime.utcnow().isoformat(),
                }

            # Calculate statistics
            metadatas = results["metadatas"]
            total_chunks = len(metadatas)

            # Count unique sources
            sources = set()
            issues = set()
            fresh_count = 0
            quality_scores = []
            timestamps = []

            for metadata in metadatas:
                sources.add(metadata.get("source_url", ""))
                if "issue" in metadata:
                    issues.add(metadata["issue"])
                if metadata.get("is_fresh", False):
                    fresh_count += 1
                if "quality_score" in metadata:
                    quality_scores.append(float(metadata["quality_score"]))
                if "extraction_timestamp" in metadata:
                    timestamps.append(metadata["extraction_timestamp"])

            # Calculate scores
            freshness_score = fresh_count / total_chunks if total_chunks > 0 else 0.0
            avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
            last_updated = max(timestamps) if timestamps else datetime.utcnow().isoformat()

            return {
                "total_chunks": total_chunks,
                "total_sources": len(sources),
                "issues_covered": list(issues),
                "freshness_score": freshness_score,
                "quality_score": avg_quality,
                "last_updated": last_updated,
            }

        except Exception as e:
            logger.error(f"Failed to get content stats: {e}")
            return {
                "total_chunks": 0,
                "total_sources": 0,
                "issues_covered": [],
                "freshness_score": 0.0,
                "quality_score": 0.0,
                "last_updated": datetime.utcnow().isoformat(),
            }

    async def cleanup_old_content(self, days: int = 30):
        """
        Clean up old content from the database.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        logger.info(f"Cleaning up content older than {cutoff_date}")

        if not self.client or not self.collection:
            await self.initialize()

        try:
            # Get all content with timestamps
            results = self.collection.get(include=["metadatas"])

            if not results["metadatas"]:
                logger.info("No content found for cleanup")
                return

            # Find old content IDs
            old_ids = []
            for i, metadata in enumerate(results["metadatas"]):
                if "extraction_timestamp" in metadata:
                    try:
                        extraction_time = datetime.fromisoformat(metadata["extraction_timestamp"])
                        if extraction_time < cutoff_date:
                            old_ids.append(results["ids"][i])
                    except ValueError:
                        # Invalid timestamp format, consider for cleanup
                        old_ids.append(results["ids"][i])

            # Delete old content
            if old_ids:
                self.collection.delete(ids=old_ids)
                logger.info(f"Cleaned up {len(old_ids)} old content items")
            else:
                logger.info("No old content found for cleanup")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            raise
