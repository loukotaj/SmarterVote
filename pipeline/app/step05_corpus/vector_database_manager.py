"""Vector Database Manager for SmarterVote Pipeline

This module encapsulates ChromaDB operations for content indexing and similarity
search. It provides core functionality such as client initialization, document
chunking, duplicate detection, statistics, and maintenance utilities. Election
specific logic lives in :mod:`election_vector_database_manager`.

IMPLEMENTATION STATUS:
✅ ChromaDB client initialization and configuration
✅ Document chunking strategies with sentence boundary preservation
✅ Vector embedding and search functionality (all-MiniLM-L6-v2)
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
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

from ..schema import ExtractedContent, Source, SourceType, VectorDocument


class InMemoryCollection:
    """Simple in-memory stand-in for Chroma collections used in tests."""

    def __init__(self):
        self.store: Dict[str, tuple[str, Dict[str, Any]]] = {}

    def add(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        for doc, meta, id_ in zip(documents, metadatas, ids):
            self.store[id_] = (doc, meta)

    def get(self, where: Optional[Dict[str, Any]] = None, include: Optional[List[str]] = None):
        ids, docs, metas = [], [], []
        for id_, (doc, meta) in self.store.items():
            match = True
            if where:
                conditions = where.get("$and")
                if conditions:
                    for cond in conditions:
                        ((k, v),) = cond.items()
                        if meta.get(k) != v:
                            match = False
                            break
                else:
                    for k, v in where.items():
                        if meta.get(k) != v:
                            match = False
                            break
            if match:
                ids.append(id_)
                docs.append(doc)
                metas.append(meta)

        result: Dict[str, Any] = {"ids": ids}
        if include:
            if "documents" in include:
                result["documents"] = docs
            if "metadatas" in include:
                result["metadatas"] = metas
            if "distances" in include:
                result["distances"] = [0.0 for _ in docs]
        return result

    def query(
        self,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[List[float]]] = None,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ):
        result = self.get(where=where, include=include)
        # Chroma query returns lists of lists
        if "documents" in result:
            result["documents"] = [result["documents"][:n_results]]
        if "metadatas" in result:
            result["metadatas"] = [result["metadatas"][:n_results]]
        if "ids" in result:
            result["ids"] = [result["ids"][:n_results]]
        if "distances" in result:
            result["distances"] = [result["distances"][:n_results]]
        return result

    def count(self) -> int:
        return len(self.store)

    def delete(self, ids: List[str]):
        for id_ in ids:
            self.store.pop(id_, None)

    def to_dict(self) -> Dict[str, Any]:
        return {id_: {"doc": doc, "meta": meta} for id_, (doc, meta) in self.store.items()}

    def load_dict(self, data: Dict[str, Any]):
        self.store = {id_: (entry["doc"], entry["meta"]) for id_, entry in data.items()}


class InMemoryClient:
    """Minimal client returning an in-memory collection with optional persistence."""

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = persist_path
        self._collection = InMemoryCollection()
        if self.persist_path and self.persist_path.exists():
            with self.persist_path.open("r") as f:
                self._collection.load_dict(json.load(f))

    def get_or_create_collection(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        return self._collection

    def save(self):
        if self.persist_path:
            with self.persist_path.open("w") as f:
                json.dump(self._collection.to_dict(), f)

    def reset(self):
        self._collection = InMemoryCollection()
        if self.persist_path and self.persist_path.exists():
            self.persist_path.unlink()


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

            try:
                self.client = chromadb.Client(
                    settings=Settings(
                        chroma_db_impl="duckdb+parquet",
                        persist_directory=str(persist_dir),
                        allow_reset=True,
                        anonymized_telemetry=False,
                    )
                )
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"description": "SmarterVote electoral content corpus"},
                )
                logger.info(f"Vector database initialized with {self.collection.count()} existing documents")
            except Exception as chroma_error:  # pragma: no cover - fallback
                logger.error(f"Falling back to in-memory vector store: {chroma_error}")
                self.client = InMemoryClient(persist_path=persist_dir / "in_memory_store.json")
                self.collection = self.client.get_or_create_collection(name=self.collection_name)

            if SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.info(f"Loading embedding model: {self.config['embedding_model']}")
                self.embedding_model = SentenceTransformer(self.config["embedding_model"])
            else:
                self.embedding_model = None
                logger.info("Using ChromaDB default embedding function")

        except Exception as e:
            logger.error(f"Failed to initialize vector database: {e}")
            raise

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

    async def _index_chunk(self, chunk: Dict[str, Any], extra_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Index a single chunk in the vector database with optional metadata and enhanced duplicate detection."""
        try:
            if not self.collection:
                await self.initialize()

            if extra_metadata:
                chunk["metadata"].update(extra_metadata)

            # Compute content hash for duplicate detection
            content_hash = hashlib.md5(chunk["text"].encode()).hexdigest()
            chunk["metadata"]["content_hash"] = content_hash

            # Enhanced duplicate detection with claim hash
            claim_hash = chunk["metadata"].get("claim_hash", "")
            
            # Check for duplicate by content hash and extra metadata
            if extra_metadata:
                conditions = [{"content_hash": content_hash}] + [{k: v} for k, v in extra_metadata.items()]
                where = {"$and": conditions}
            else:
                where = {"content_hash": content_hash}
            existing = self.collection.get(where=where)
            if existing.get("ids"):
                logger.debug(f"Skipping duplicate chunk {chunk['id']} (content hash match)")
                return True

            # Additional claim-based duplicate detection if claim_hash is available
            if claim_hash:
                claim_where = {"claim_hash": claim_hash}
                if extra_metadata:
                    # Check for claim duplicates within the same context (e.g., same race)
                    claim_conditions = [{"claim_hash": claim_hash}] + [{k: v} for k, v in extra_metadata.items()]
                    claim_where = {"$and": claim_conditions}
                
                existing_claims = self.collection.get(where=claim_where)
                if existing_claims.get("ids"):
                    logger.debug(f"Skipping duplicate chunk {chunk['id']} (claim hash match)")
                    return True

            # Add to collection
            self.collection.add(documents=[chunk["text"]], metadatas=[chunk["metadata"]], ids=[chunk["id"]])
            if isinstance(self.client, InMemoryClient):
                self.client.save()

            logger.debug(f"Indexed chunk {chunk['id']}")
            return True

        except Exception as e:
            logger.error(f"Failed to index chunk {chunk['id']}: {e}")
            return False

    async def search_similar(
        self,
        query: str,
        where: Optional[Dict[str, Any]] = None,
        limit: int = 10,
    ) -> List[VectorDocument]:
        """Search for similar content in the vector database."""
        logger.info(f"Searching for similar content: '{query[:50]}...'")

        if not self.client or not self.collection:
            await self.initialize()

        try:
            if self.embedding_model:
                # Generate query embedding and use vector search
                query_embedding = self.embedding_model.encode(query).tolist()

                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    where=where,
                    include=["documents", "metadatas", "distances"],
                )
            else:
                # Use text-based search if no embedding model
                results = self.collection.query(
                    query_texts=[query],
                    n_results=limit,
                    where=where,
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

    async def search_content(self, where: Dict[str, Any]) -> List[ExtractedContent]:
        """Search and retrieve content for summarization using a metadata filter."""
        logger.info(f"Searching content with filters: {where}")

        if not self.client or not self.collection:
            await self.initialize()

        try:
            # Get all content matching the filter
            results = self.collection.get(where=where, include=["documents", "metadatas"])

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

    async def get_documents(self, where: Dict[str, Any]) -> List[VectorDocument]:
        """Retrieve documents from the database using a metadata filter."""
        logger.info(f"Retrieving documents with filters: {where}")

        if not self.client or not self.collection:
            await self.initialize()

        try:
            results = self.collection.get(where=where, include=["documents", "metadatas"])

            documents = []
            if results["documents"]:
                for i, doc_text in enumerate(results["documents"]):
                    metadata = results["metadatas"][i] if results["metadatas"] else {}
                    doc_id = results["ids"][i] if results["ids"] else f"doc_{i}"

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
                        similarity_score=None,
                        source=source,
                    )
                    documents.append(doc)

            logger.info(f"Retrieved {len(documents)} documents")
            return documents

        except Exception as e:
            logger.error(f"Failed to retrieve documents: {e}")
            return []

    async def get_content_stats(self, where: Dict[str, Any]) -> Dict[str, Any]:
        """Get statistics about indexed content matching a metadata filter, including AI enrichment metrics."""
        if not self.client or not self.collection:
            await self.initialize()

        try:
            results = self.collection.get(where=where, include=["metadatas"])

            if not results["metadatas"]:
                return {
                    "total_chunks": 0,
                    "total_sources": 0,
                    "issues_covered": [],
                    "freshness_score": 0.0,
                    "quality_score": 0.0,
                    "average_usefulness": 0.0,
                    "ai_issues_distinct": [],
                    "last_updated": datetime.utcnow().isoformat(),
                }

            metadatas = results["metadatas"]
            total_chunks = len(metadatas)

            # Count unique sources
            sources = set()
            issues = set()
            ai_issues = set()
            fresh_count = 0
            quality_scores = []
            usefulness_scores = []
            timestamps = []

            for metadata in metadatas:
                sources.add(metadata.get("source_url", ""))
                
                # Legacy issue tracking
                if "issue" in metadata:
                    issues.add(metadata["issue"])
                
                # AI-enriched issue tracking
                if "ai_issues" in metadata:
                    ai_issue_list = metadata["ai_issues"]
                    if isinstance(ai_issue_list, list):
                        ai_issues.update(ai_issue_list)
                
                if metadata.get("is_fresh", False):
                    fresh_count += 1
                
                if "quality_score" in metadata:
                    quality_scores.append(float(metadata["quality_score"]))
                
                # AI usefulness scores
                if "ai_usefulness" in metadata:
                    usefulness_scores.append(float(metadata["ai_usefulness"]))
                
                if "extraction_timestamp" in metadata:
                    timestamps.append(metadata["extraction_timestamp"])

            freshness_score = fresh_count / total_chunks if total_chunks > 0 else 0.0
            avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
            avg_usefulness = sum(usefulness_scores) / len(usefulness_scores) if usefulness_scores else 0.0
            last_updated = max(timestamps) if timestamps else datetime.utcnow().isoformat()

            return {
                "total_chunks": total_chunks,
                "total_sources": len(sources),
                "issues_covered": list(issues),  # Legacy issue list
                "ai_issues_distinct": list(ai_issues),  # AI-detected issues
                "freshness_score": freshness_score,
                "quality_score": avg_quality,
                "average_usefulness": avg_usefulness,  # AI usefulness metric
                "last_updated": last_updated,
            }

        except Exception as e:
            logger.error(f"Failed to get content stats: {e}")
            return {
                "total_chunks": 0,
                "total_sources": 0,
                "issues_covered": [],
                "ai_issues_distinct": [],
                "freshness_score": 0.0,
                "quality_score": 0.0,
                "average_usefulness": 0.0,
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
