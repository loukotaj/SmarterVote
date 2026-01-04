"""Step 02: Build Vector Corpus from Extracted Content

This handler takes the relevant content from Step 01 and builds
a ChromaDB vector corpus for semantic search during summarization.
"""

import hashlib
import logging
import time
from typing import Any, Dict, List

from pipeline.app.schema import ExtractedContent, Source, SourceType
from datetime import datetime


class Step02CorpusHandler:
    """Handler for building the ChromaDB corpus from relevant content."""

    def __init__(self):
        self.vector_db = None

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """
        Build vector corpus from relevant content.

        Payload expected:
            - race_id: str
            - relevant_content: list of ExtractedContent or content references
            - race_json: dict (race metadata)

        Returns:
            - corpus_stats: dict with indexing statistics
        """
        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        relevant_content = payload.get("relevant_content") or payload.get("processed_content")
        race_json = payload.get("race_json")

        if not race_id:
            raise ValueError("Step02CorpusHandler: Missing 'race_id' in payload")

        if not relevant_content:
            raise ValueError("Step02CorpusHandler: Missing 'relevant_content' in payload")

        logger.info(f"Step02 Corpus: Building vector corpus for race {race_id}")

        # Import storage functions for content references
        from pipeline_client.backend.storage import load_content_from_references

        # Resolve content references if needed
        if isinstance(relevant_content, dict) and relevant_content.get("type") == "content_collection_refs":
            logger.info(f"Loading content from {len(relevant_content.get('references', []))} references")
            actual_content = load_content_from_references(relevant_content["references"])
        elif isinstance(relevant_content, list):
            actual_content = relevant_content
        else:
            raise ValueError("Step02CorpusHandler: Invalid 'relevant_content' format")

        if not actual_content:
            logger.warning("No content available for corpus building")
            return {
                "race_id": race_id,
                "corpus_stats": {
                    "documents_indexed": 0,
                    "chunks_created": 0,
                    "total_characters": 0,
                },
                "status": "empty",
            }

        # Convert to ExtractedContent if needed
        docs: List[ExtractedContent] = []
        for item in actual_content:
            try:
                if isinstance(item, ExtractedContent):
                    docs.append(item)
                elif isinstance(item, dict):
                    # Build a proper ExtractedContent object
                    source_data = item.get("source", {})
                    source = Source(
                        url=source_data.get("url", "https://unknown.com"),
                        type=SourceType(source_data.get("type", "website")),
                        title=source_data.get("title", "Unknown"),
                        last_accessed=datetime.utcnow(),
                    )
                    doc = ExtractedContent(
                        source=source,
                        text=item.get("extracted_text", item.get("text", "")),
                        extraction_timestamp=datetime.utcnow(),
                        language=item.get("language", "en"),
                        word_count=len(item.get("extracted_text", item.get("text", "")).split()),
                        metadata={
                            **item.get("metadata", {}),
                            "quality_score": item.get("quality_score", 0.5),
                        },
                    )
                    docs.append(doc)
            except Exception as e:
                logger.warning(f"Skipping invalid content item: {e}")

        logger.info(f"Processing {len(docs)} documents for corpus")

        # Initialize vector database manager
        from pipeline.app.step02_corpus.vector_database_manager import VectorDatabaseManager

        t0 = time.perf_counter()
        vector_db = VectorDatabaseManager()
        await vector_db.initialize()

        # Build corpus using the chunking and indexing methods
        indexed_count = 0
        total_chunks = 0
        total_chars = 0

        for doc in docs:
            try:
                if not doc.text or len(doc.text.strip()) < 50:
                    continue

                # Use the internal chunking method
                chunks = vector_db._chunk_content(doc)

                for chunk in chunks:
                    # Add race_id to metadata for filtering
                    success = await vector_db._index_chunk(chunk, extra_metadata={"race_id": race_id})
                    if success:
                        total_chunks += 1

                indexed_count += 1
                total_chars += len(doc.text)

            except Exception as e:
                logger.warning(f"Failed to index document: {e}")

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"Corpus built: {indexed_count} documents, {total_chunks} chunks in {duration_ms}ms")

        return {
            "race_id": race_id,
            "corpus_stats": {
                "documents_indexed": indexed_count,
                "chunks_created": total_chunks,
                "total_characters": total_chars,
                "duration_ms": duration_ms,
            },
            "status": "completed",
        }
