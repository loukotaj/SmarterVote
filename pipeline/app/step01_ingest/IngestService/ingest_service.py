from __future__ import annotations

import logging
from typing import List

from ...schema import ExtractedContent, RaceJSON, Source
from ..ContentExtractor import ContentExtractor
from ..ContentFetcher import WebContentFetcher
from ..DiscoveryService import SourceDiscoveryEngine

logger = logging.getLogger(__name__)


class IngestService:
    """Orchestrates discovery, fetching, and extraction of race content."""

    def __init__(self) -> None:
        self.discovery = SourceDiscoveryEngine()
        self.fetcher = WebContentFetcher()
        self.extractor = ContentExtractor()

    async def ingest(self, race_id: str, race_json: RaceJSON) -> List[ExtractedContent]:
        """Run full ingestion pipeline for a race.

        Args:
            race_id: Race identifier like ``"mo-senate-2024"``.
            race_json: ``RaceJSON`` produced by the metadata service.

        Returns:
            List of ``ExtractedContent`` items with associated ``Source``.
        """
        if race_json is None:
            raise ValueError("race_json is required for ingestion")

        sources = await self.discovery.discover_all_sources(race_id, race_json)
        if not sources:
            logger.warning("No sources discovered for %s", race_id)
            return []

        raw_content = await self.fetcher.fetch_content(sources)
        extracted = await self.extractor.extract_content(raw_content)

        # Ensure each extracted item has its Source and no raw content is leaked
        cleaned: List[ExtractedContent] = [ec for ec in extracted if isinstance(ec.source, Source)]
        return cleaned
