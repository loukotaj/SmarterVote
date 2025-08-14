from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from ..schema import ExtractedContent, Source, SourceType
from . import IngestService


class TestIngestService:
    """Tests for the IngestService."""

    @pytest.fixture
    def ingest_service(self) -> IngestService:
        return IngestService()

    @pytest.mark.asyncio
    async def test_ingest_returns_extracted_content(self, ingest_service: IngestService):
        source = Source(
            url="https://example.com/test",
            type=SourceType.WEBSITE,
            title="Test Source",
            last_accessed=datetime.utcnow(),
        )
        extracted = ExtractedContent(
            source=source,
            text="example text",
            metadata={},
            extraction_timestamp=datetime.utcnow(),
            word_count=2,
        )

        ingest_service.discovery.discover_all_sources = AsyncMock(return_value=[source])
        ingest_service.fetcher.fetch_content = AsyncMock(return_value=[{"source": source, "content": "<html></html>"}])
        ingest_service.extractor.extract_content = AsyncMock(return_value=[extracted])

        result = await ingest_service.ingest("test-race")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].source == source
        assert not hasattr(result[0], "content")
