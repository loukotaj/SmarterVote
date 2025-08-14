from __future__ import annotations

import logging
from typing import List, Optional

from ..schema import ExtractedContent, RaceJSON, Source
from ..step02_discover import SourceDiscoveryEngine
from ..step03_fetch import WebContentFetcher
from ..step04_extract import ContentExtractor

logger = logging.getLogger(__name__)


class IngestService:
    """Orchestrates discovery, fetching, and extraction of race content."""

    def __init__(self) -> None:
        self.discovery = SourceDiscoveryEngine()
        self.fetcher = WebContentFetcher()
        self.extractor = ContentExtractor()

    async def ingest(self, race_id: str, race_json: Optional[RaceJSON] = None) -> List[ExtractedContent]:
        """Run full ingestion pipeline for a race.

        Args:
            race_id: Race identifier like ``"mo-senate-2024"``.
            race_json: Optional ``RaceJSON`` to optimize discovery.

        Returns:
            List of ``ExtractedContent`` items with associated ``Source``.
        """
        sources = await self.discovery.discover_all_sources(race_id, race_json)
        if not sources:
            logger.warning("No sources discovered for %s", race_id)
            return []

        raw_content = await self.fetcher.fetch_content(sources)
        race_context = {"race_id": race_id}
        if race_json and getattr(race_json, "candidates", None):
            race_context["candidates"] = [c.name for c in race_json.candidates]
        extracted = await self.extractor.extract_content(raw_content, race_context=race_context)

        # Ensure each extracted item has its Source and no raw content is leaked
        cleaned: List[ExtractedContent] = [ec for ec in extracted if isinstance(ec.source, Source)]
        return cleaned
