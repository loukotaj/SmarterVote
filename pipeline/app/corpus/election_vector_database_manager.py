"""Election specific extensions to the VectorDatabaseManager.

This module provides helpers that apply election metadata (race IDs and
canonical issues) on top of the generic :class:`~.vector_database_manager.VectorDatabaseManager`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..schema import CanonicalIssue, ExtractedContent, VectorDocument
from .vector_database_manager import VectorDatabaseManager

logger = logging.getLogger(__name__)


class ElectionVectorDatabaseManager(VectorDatabaseManager):
    """Vector database manager with election specific helpers."""

    async def build_corpus(self, race_id: str, content: List[ExtractedContent]) -> bool:
        """Index extracted content in the vector database for a given race."""
        from datetime import datetime
        
        start_time = datetime.utcnow()
        logger.info(f"🗂️  Starting corpus build for race {race_id} with {len(content)} content items")

        if not self.client:
            await self.initialize()

        total_chunks = 0
        indexed_count = 0
        failed_items = 0
        
        # First pass: count total chunks for progress tracking
        for item in content:
            chunks = self._chunk_content(item)
            total_chunks += len(chunks)
            
        logger.info(f"📄 Generated {total_chunks} total chunks from {len(content)} content items")
        
        # Second pass: actual indexing with progress
        processed_chunks = 0
        for i, item in enumerate(content):
            try:
                chunks = self._chunk_content(item)
                source_chunks_indexed = 0
                
                for chunk in chunks:
                    success = await self._index_chunk(chunk, extra_metadata={"race_id": race_id})
                    if success:
                        indexed_count += 1
                        source_chunks_indexed += 1
                    
                    processed_chunks += 1
                    
                    # Log progress every 20% or 50 chunks
                    if processed_chunks % max(1, total_chunks // 5) == 0 or processed_chunks % 50 == 0:
                        progress = (processed_chunks / total_chunks) * 100
                        logger.info(f"📊 Indexing progress: {progress:.1f}% ({processed_chunks}/{total_chunks} chunks)")
                
                # Log per-source results
                logger.debug(f"✅ Indexed {source_chunks_indexed}/{len(chunks)} chunks from {item.source.url}")
                
            except Exception as exc:
                failed_items += 1
                logger.warning(f"❌ Failed to index content from {item.source.url}: {type(exc).__name__}: {str(exc)[:100]}")

        # Final statistics
        duration = (datetime.utcnow() - start_time).total_seconds()
        success_rate = (indexed_count / total_chunks) * 100 if total_chunks > 0 else 0
        
        logger.info(f"✅ Corpus build completed for {race_id}")
        logger.info(f"📊 Successfully indexed {indexed_count}/{total_chunks} chunks ({success_rate:.1f}% success)")
        logger.info(f"⏱️  Build duration: {duration:.1f}s ({total_chunks/duration:.1f} chunks/sec)")
        
        if failed_items > 0:
            logger.warning(f"⚠️  {failed_items}/{len(content)} content items had indexing failures")
            
        return indexed_count > 0

    async def search_similar(
        self,
        query: str,
        race_id: Optional[str] = None,
        issue: Optional[CanonicalIssue] = None,
        limit: int = 10,
    ) -> List[VectorDocument]:
        """Search for similar content scoped to a race/issue."""
        where: Dict[str, Any] = {}
        if race_id:
            where["race_id"] = race_id
        if issue:
            where["issue"] = issue.value

        return await super().search_similar(query, where=where or None, limit=limit)

    async def search_content(self, race_id: str, issue: Optional[CanonicalIssue] = None) -> List[ExtractedContent]:
        """Search and retrieve content for summarization."""
        where: Dict[str, Any] = {"race_id": race_id}
        if issue:
            where["issue"] = issue.value
        return await super().search_content(where)

    async def get_race_content(self, race_id: str, issue: Optional[CanonicalIssue] = None) -> List[VectorDocument]:
        """Retrieve documents for a specific race."""
        where: Dict[str, Any] = {"race_id": race_id}
        if issue:
            where["issue"] = issue.value
        return await super().get_documents(where)

    async def get_content_stats(self, race_id: str) -> Dict[str, Any]:
        """Get statistics about indexed content for a race."""
        return await super().get_content_stats({"race_id": race_id})
