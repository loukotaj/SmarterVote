"""Election specific extensions to the VectorDatabaseManager.

This module provides helpers that apply election metadata (race IDs and
canonical issues) on top of the generic :class:`~.vector_database_manager.VectorDatabaseManager`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..schema import CanonicalIssue, ExtractedContent, VectorDocument
from ..utils.ai_enrichment import ai_enrich, hash_claims
from .vector_database_manager import VectorDatabaseManager

logger = logging.getLogger(__name__)


class ElectionVectorDatabaseManager(VectorDatabaseManager):
    """Vector database manager with election specific helpers."""

    async def build_corpus(self, race_id: str, content: List[ExtractedContent]) -> bool:
        """Index extracted content in the vector database for a given race with AI enrichment."""
        logger.info(f"Indexing {len(content)} content items for race {race_id}")

        if not self.client:
            await self.initialize()

        indexed_count = 0
        for item in content:
            try:
                chunks = self._chunk_content(item)
                for chunk in chunks:
                    # AI enrichment step - enrich each chunk before indexing
                    try:
                        annotations = ai_enrich(chunk["text"], meta={"race_id": race_id, **chunk["metadata"]})
                        
                        # Filter out low-usefulness content
                        if annotations.usefulness.get("score", 0.0) < 0.35:
                            logger.debug(f"Skipping low-usefulness chunk (score: {annotations.usefulness.get('score', 0.0)})")
                            continue
                        
                        # Merge AI annotations into chunk metadata
                        chunk["metadata"].update({
                            "ai_issues": annotations.issues,
                            "ai_candidates": annotations.candidates,
                            "ai_index_summary": annotations.index_summary,
                            "ai_qa_pairs": annotations.qa_pairs,
                            "ai_usefulness": annotations.usefulness.get("score", 0.0),
                            "claim_hash": hash_claims(annotations.claims),
                            "stance": annotations.stance,
                            # Set primary issue for backward compatibility
                            "issue": annotations.issues[0] if annotations.issues else chunk["metadata"].get("issue"),
                        })
                        
                    except Exception as enrich_error:
                        logger.warning(f"AI enrichment failed for chunk, proceeding without enrichment: {enrich_error}")
                        # Continue with original chunk if enrichment fails
                        chunk["metadata"]["ai_usefulness"] = 0.5  # Default score
                    
                    success = await self._index_chunk(chunk, extra_metadata={"race_id": race_id})
                    if success:
                        indexed_count += 1
            except Exception as exc:  # pragma: no cover - logging
                logger.error(f"Failed to index content from {item.source.url}: {exc}")

        logger.info(f"Successfully indexed {indexed_count} chunks for race {race_id}")
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
