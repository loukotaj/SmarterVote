from __future__ import annotations

import logging
from typing import List

from ...schema import ExtractedContent, RaceJSON, Source
from ...utils.ai_relevance_filter import AIRelevanceFilter
from ..ContentExtractor import ContentExtractor
from ..ContentFetcher import WebContentFetcher
from ..DiscoveryService import SourceDiscoveryEngine

logger = logging.getLogger(__name__)


class IngestService:
    """Orchestrates discovery, fetching, extraction and relevance filtering."""

    def __init__(self) -> None:
        self.discovery = SourceDiscoveryEngine()
        self.fetcher = WebContentFetcher()
        self.extractor = ContentExtractor()
        self.relevance = AIRelevanceFilter()

    async def discover_sources(self, race_id: str, race_json: RaceJSON) -> List[Source]:
        return await self.discovery.discover_all_sources(race_id, race_json)

    async def fetch_raw_content(self, sources: List[Source]):
        return await self.fetcher.fetch_content(sources)

    async def extract_text(self, raw_content):
        return await self.extractor.extract_content(raw_content)

    async def ai_relevance_check(self, extracted: List[ExtractedContent], race_json: RaceJSON) -> List[ExtractedContent]:
        race_name = race_json.title or race_json.id
        candidates = [c.name for c in race_json.candidates]
        return await self.relevance.filter_content(extracted, race_name, candidates)

    async def ingest(self, race_id: str, race_json: RaceJSON) -> List[ExtractedContent]:
        """Run full ingestion pipeline for a race."""

        if race_json is None:
            raise ValueError("race_json is required for ingestion")

        sources = await self.discover_sources(race_id, race_json)
        if not sources:
            logger.warning("No sources discovered for %s", race_id)
            return []

        raw_content = await self.fetch_raw_content(sources)
        extracted = await self.extract_text(raw_content)
        filtered = await self.ai_relevance_check(extracted, race_json)

        # Ensure each extracted item has its Source and no raw content is leaked
        cleaned: List[ExtractedContent] = [ec for ec in filtered if isinstance(ec.source, Source)]
        return cleaned
