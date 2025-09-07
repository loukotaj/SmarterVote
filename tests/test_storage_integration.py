from datetime import datetime
from pathlib import Path

import pytest

from pipeline.app.schema import Candidate, ConfidenceLevel, RaceJSON, RaceMetadata
from pipeline_client.backend.handlers.step01_relevance import Step01RelevanceHandler
from pipeline_client.backend.storage_backend import LocalStorageBackend
from shared.models import ExtractedContent, Source, SourceType


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.external_api
async def test_metadata_service_saves_race_json(tmp_path):
    module = pytest.importorskip("pipeline.app.step01_ingest.MetaDataService.race_metadata_service")
    storage = LocalStorageBackend(tmp_path)
    service = module.RaceMetadataService(storage_backend=storage)

    # Avoid network calls by patching internals
    service._seed_urls = lambda *a, **k: []

    async def mock_fetch_and_extract_docs(urls, trace_id):
        return []

    async def mock_llm_candidates(**kwargs):
        cand = Candidate(name="Jane Doe", party="Democratic", incumbent=False)
        return [cand], "Democratic", []

    service._fetch_and_extract_docs = mock_fetch_and_extract_docs
    service._llm_candidates = mock_llm_candidates

    race_json = await service.extract_race_metadata("xx-senate-2024")
    assert race_json.id == "xx-senate-2024"
    assert service.race_json_uri
    assert Path(service.race_json_uri).exists()


@pytest.mark.anyio
async def test_relevance_handler_uploads_files(tmp_path):
    storage = LocalStorageBackend(tmp_path)
    handler = Step01RelevanceHandler(storage)

    class DummyFilter:
        async def filter_content(self, docs, race_name, candidates):
            for d in docs:
                d.metadata["relevance"] = {"is_relevant": True}
            return docs

    handler.filter_cls = DummyFilter

    src = Source(url="http://example.com", type=SourceType.WEBSITE, last_accessed=datetime.utcnow())
    doc = ExtractedContent(
        source=src,
        text="hello world",
        metadata={},
        extraction_timestamp=datetime.utcnow(),
        word_count=2,
    )
    race_json = RaceJSON(
        id="xx-senate-2024",
        election_date=datetime.utcnow(),
        candidates=[Candidate(name="Jane Doe", party="Democratic", incumbent=False)],
        updated_utc=datetime.utcnow(),
        generator=[],
        race_metadata=RaceMetadata(
            race_id="xx-senate-2024",
            state="XX",
            office_type="senate",
            year=2024,
            full_office_name="U.S. Senate",
            jurisdiction="XX",
            district=None,
            election_date=datetime.utcnow(),
            race_type="federal",
            is_primary=False,
            primary_date=None,
            is_special_election=False,
            is_runoff=False,
            incumbent_party=None,
            major_issues=[],
            geographic_keywords=[],
            confidence=ConfidenceLevel.LOW,
            extracted_at=datetime.utcnow(),
        ),
    )
    payload = {
        "race_id": "xx-senate-2024",
        "processed_content": [doc.model_dump(mode="json", by_alias=True, exclude_none=True)],
        "race_json": race_json.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    result = await handler.handle(payload, {})
    uri = result[0]["metadata"]["storage_uri"]
    assert Path(uri).exists()
