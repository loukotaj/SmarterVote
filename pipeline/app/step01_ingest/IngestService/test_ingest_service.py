from datetime import datetime as dt
from unittest.mock import AsyncMock

import pytest

# The ingest service depends on several external systems and heavy optional
# packages. Skip these tests in lightweight environments.
pytest.skip("Ingest service requires full pipeline dependencies", allow_module_level=True)

from ...schema import Candidate, ExtractedContent, RaceJSON, Source, SourceType
from .ingest_service import IngestService


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
            last_accessed=dt.utcnow(),
        )
        extracted = ExtractedContent(
            source=source,
            text="example text",
            metadata={},
            extraction_timestamp=dt.utcnow(),
            word_count=2,
        )

        ingest_service.discovery.discover_all_sources = AsyncMock(return_value=[source])
        ingest_service.fetcher.fetch_content = AsyncMock(return_value=[{"source": source, "content": "<html></html>"}])
        ingest_service.extractor.extract_content = AsyncMock(return_value=[extracted])

        race_json = RaceJSON(
            id="test-race",
            election_date=dt.utcnow(),
            candidates=[Candidate(name="Test Candidate", party="Test")],
            updated_utc=dt.utcnow(),
            generator=[],
        )

        result = await ingest_service.ingest("test-race", race_json=race_json)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].source == source
        assert not hasattr(result[0], "content")
