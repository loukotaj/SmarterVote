import json
import sys
import types
from pathlib import Path

import pytest

from pipeline.app.schema import RaceJSON
from pipeline_client.backend.storage_backend import LocalStorageBackend


class DummyRaceMetadataService:
    def __init__(self, providers=None, storage_backend=None):
        self.storage_backend = storage_backend
        self.race_json_uri = None

    async def extract_race_metadata(self, race_id: str):  # pragma: no cover - simple stub
        data = {
            "id": race_id,
            "election_date": "2024-11-05T00:00:00",
            "candidates": [],
            "updated_utc": "2024-08-19T00:00:00",
            "generator": [],
            "race_metadata": None,
        }
        if self.storage_backend:
            self.race_json_uri = self.storage_backend.save_race_json(race_id, data)
        return json.dumps(data)


@pytest.fixture
def anyio_backend():  # pragma: no cover - fixture for async support
    return "asyncio"


@pytest.mark.anyio
async def test_local_metadata_output_is_dict(monkeypatch, tmp_path):
    module = types.SimpleNamespace(RaceMetadataService=DummyRaceMetadataService)
    monkeypatch.setitem(
        sys.modules,
        "pipeline.app.step01_ingest.MetaDataService.race_metadata_service",
        module,
    )

    from pipeline_client.backend.handlers.step01_metadata import Step01MetadataHandler

    metadata_handler = Step01MetadataHandler(LocalStorageBackend(tmp_path))
    result = await metadata_handler.handle({"race_id": "xx-senate-2024"}, {})
    assert isinstance(result["race_json"], dict)

    # Ensure the race_json payload can be validated
    RaceJSON.model_validate(result["race_json"])
