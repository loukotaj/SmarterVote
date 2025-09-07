import sys
import types

import pytest

from pipeline.app.schema import RaceJSON
from pipeline_client.backend.storage_backend import LocalStorageBackend


class DummyRaceMetadataService:
    def __init__(self, providers=None, storage_backend=None):
        self.storage_backend = storage_backend
        self.race_json_uri = None

    async def extract_race_metadata(self, race_id: str):
        data = {
            "id": race_id,
            "election_date": "2025-11-04T00:00:00",
            "candidates": [],
            "updated_utc": "2024-08-19T00:00:00",
            "generator": [],
            "race_metadata": None,
        }
        race_json = RaceJSON.model_validate(data)
        if self.storage_backend:
            payload = race_json.model_dump(mode="json", by_alias=True, exclude_none=True)
            self.race_json_uri = self.storage_backend.save_race_json(race_id, payload)
        return race_json


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.external_api
async def test_local_metadata_handler_returns_valid_race_json(tmp_path, anyio_backend, monkeypatch):
    module = types.SimpleNamespace(RaceMetadataService=DummyRaceMetadataService)
    monkeypatch.setitem(
        sys.modules,
        "pipeline.app.step01_ingest.MetaDataService.race_metadata_service",
        module,
    )

    from pipeline_client.backend.handlers.step01_metadata import Step01MetadataHandler

    handler = Step01MetadataHandler(LocalStorageBackend(tmp_path))
    result = await handler.handle({"race_id": "xx-senate-2024"}, {})
    assert isinstance(result["race_json"], dict)
    RaceJSON.model_validate(result["race_json"])
    assert result.get("race_json_uri")
