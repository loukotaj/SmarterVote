import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from pipeline_client.backend.handlers.agent import AgentHandler
from pipeline_client.backend.models import RunOptions


def test_pipeline_run_options_validate_baseline_source():
    assert RunOptions().baseline_source == "latest"
    assert RunOptions(baseline_source="published").baseline_source == "published"

    with pytest.raises(ValidationError):
        RunOptions(baseline_source="draft")


@pytest.mark.asyncio
async def test_published_baseline_ignores_draft_blob():
    handler = AgentHandler()
    blobs = {
        "drafts/test-race.json": {"id": "test-race", "candidates": [{"name": "Draft Candidate"}]},
        "races/test-race.json": {"id": "test-race", "candidates": [{"name": "Published Candidate"}]},
    }

    def blob_for(name):
        blob = MagicMock()
        blob.exists.return_value = name in blobs
        blob.download_as_text.return_value = json.dumps(blobs.get(name))
        return blob

    bucket = MagicMock()
    bucket.blob.side_effect = blob_for
    client = MagicMock()
    client.bucket.return_value = bucket

    with (
        patch("pipeline_client.backend.settings.settings.gcs_bucket", "test-bucket"),
        patch.object(handler, "_get_storage_client", return_value=client),
    ):
        result = await handler._load_existing_from_gcs("test-race", baseline_source="published")

    assert result["candidates"][0]["name"] == "Published Candidate"
    bucket.blob.assert_called_once_with("races/test-race.json")


@pytest.mark.asyncio
async def test_latest_baseline_keeps_draft_first_behavior():
    handler = AgentHandler()
    blob = MagicMock()
    blob.exists.return_value = True
    blob.download_as_text.return_value = json.dumps({"id": "test-race", "candidates": [{"name": "Draft Candidate"}]})
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket

    with (
        patch("pipeline_client.backend.settings.settings.gcs_bucket", "test-bucket"),
        patch.object(handler, "_get_storage_client", return_value=client),
    ):
        result = await handler._load_existing_from_gcs("test-race")

    assert result["candidates"][0]["name"] == "Draft Candidate"
    bucket.blob.assert_called_once_with("drafts/test-race.json")
