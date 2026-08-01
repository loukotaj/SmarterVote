"""Tests for AgentHandler integration."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline_client.agent.handlers import _normalize_source
from pipeline_client.agent.llm import _normalize_source as _normalize_llm_source
from pipeline_client.backend.handlers.agent import AgentHandler


@pytest.fixture(autouse=True)
def fast_handler_side_effects(monkeypatch, tmp_path):
    """Keep AgentHandler tests from touching real metrics/race metadata backends."""
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.setenv("PIPELINE_METRICS_DB_PATH", str(tmp_path / "pipeline_metrics.db"))
    with (
        patch(
            "pipeline_client.backend.handlers.agent.AgentHandler._load_existing_from_gcs",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("pipeline_client.backend.race_manager.race_manager.update_race_metadata"),
        patch("pipeline_client.backend.pipeline_metrics.get_pipeline_metrics_store") as metrics_store,
    ):
        metrics_store.return_value.record_run = AsyncMock()
        yield


def test_normalize_source_maps_candidate_link_types_to_source_types():
    source = _normalize_source(
        {"url": "https://justfacts.votesmart.org/candidate/123", "type": "votesmart", "title": "Vote Smart"}
    )

    assert source is not None
    assert source["type"] == "website"

    source = _normalize_source({"url": "https://www.congress.gov/member/example", "type": "govtrack"})

    assert source is not None
    assert source["type"] == "government"


def test_llm_source_normalization_maps_freeform_source_types():
    source = {
        "url": "https://www.warner.senate.gov/about/priorities/health-care/",
        "type": "official campaign page",
    }

    _normalize_llm_source(source, "2026-05-17T00:00:00+00:00")

    assert source["type"] == "government"
    assert source["last_accessed"] == "2026-05-17T00:00:00+00:00"


@pytest.mark.asyncio
async def test_v2_handler_raises_on_missing_race_id():
    """AgentHandler raises ValueError when race_id is missing."""
    handler = AgentHandler()
    with pytest.raises(ValueError, match="Missing 'race_id'"):
        await handler.handle({}, {})


@pytest.mark.asyncio
async def test_v2_handler_runs_agent_and_publishes():
    """AgentHandler calls run_agent and saves draft."""
    handler = AgentHandler()
    fake_result = {"id": "test-race", "candidates": []}

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_save_draft", new_callable=AsyncMock) as mock_save_draft,
    ):
        mock_agent.return_value = fake_result
        mock_save_draft.return_value = Path("/tmp/test-race.json")

        result = await handler.handle(
            {"race_id": "test-race"},
            {"cheap_mode": True},
        )

    assert result["race_id"] == "test-race"
    assert result["status"] == "draft"
    mock_agent.assert_called_once()


@pytest.mark.asyncio
async def test_v2_handler_passes_enabled_steps():
    """AgentHandler passes enabled_steps option to run_agent."""
    handler = AgentHandler()
    fake_result = {"id": "test-race", "candidates": []}

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_save_draft", new_callable=AsyncMock) as mock_save_draft,
    ):
        mock_agent.return_value = fake_result
        mock_save_draft.return_value = Path("/tmp/test-race.json")

        await handler.handle(
            {"race_id": "test-race"},
            {
                "cheap_mode": True,
                "enabled_steps": ["discovery", "images", "issues"],
                "candidate_names": ["Jeff Wadlin"],
                "resume_partial": True,
            },
        )

    mock_agent.assert_called_once()
    call_kwargs = mock_agent.call_args
    assert call_kwargs.kwargs["enabled_steps"] == ["discovery", "images", "issues"]
    assert call_kwargs.kwargs["candidate_names"] == ["Jeff Wadlin"]
    assert call_kwargs.kwargs["resume_partial"] is True


@pytest.mark.asyncio
async def test_v2_handler_defaults_updates_to_low_cost_non_issue_steps():
    """An existing baseline gets maintenance steps unless the caller opts in."""
    handler = AgentHandler()
    existing = {"id": "test-race", "candidates": [{"name": "Alice", "issues": {}}]}

    with (
        patch.object(handler, "_load_existing_from_gcs", new_callable=AsyncMock, return_value=existing),
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_save_draft", new_callable=AsyncMock) as mock_save_draft,
    ):
        mock_agent.return_value = existing
        mock_save_draft.return_value = Path("/tmp/test-race.json")

        await handler.handle({"race_id": "test-race"}, {"cheap_mode": True})

    enabled_steps = mock_agent.call_args.kwargs["enabled_steps"]
    assert enabled_steps == [
        "discovery",
        "images",
        "finance",
        "refinement",
        "polling",
        "forecast",
        "voter_resources",
    ]
    assert "issues" not in enabled_steps
    assert "review" not in enabled_steps
    assert "iteration" not in enabled_steps


@pytest.mark.asyncio
async def test_v2_handler_uses_run_id_for_firestore_logs_when_pipeline_import_fails():
    """run_id from options should still drive Firestore logging if optional imports fail."""
    handler = AgentHandler()
    fake_result = {
        "id": "test-race",
        "candidates": [{"name": "Alice", "issues": {}}],
    }

    async def _fake_run_agent(*_args, **kwargs):
        on_log = kwargs.get("on_log")
        if on_log:
            on_log("info", "hello from test")
        return fake_result

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_save_draft", new_callable=AsyncMock) as mock_save_draft,
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
        patch.dict(sys.modules, {"pipeline_client.backend.pipeline_runner": None}),
    ):
        mock_agent.side_effect = _fake_run_agent
        mock_save_draft.return_value = Path("/tmp/test-race.json")

        await handler.handle(
            {"race_id": "test-race"},
            {"cheap_mode": True, "run_id": "run-123"},
        )

    mock_fs_logger_cls.assert_called_with("run-123")
    mock_fs_logger_cls.return_value.log.assert_called()


@pytest.mark.asyncio
async def test_v2_handler_tracks_step_progress_in_firestore_without_run_manager():
    """Step tracker should still write current_step/progress when run_manager imports fail."""
    handler = AgentHandler()
    fake_result = {
        "id": "test-race",
        "candidates": [{"name": "Alice", "issues": {}}],
    }

    async def _fake_run_agent(*_args, **kwargs):
        tracker = kwargs.get("step_tracker")
        assert tracker is not None
        tracker["start"]("issues")
        tracker["progress"]("issues", pct=42, message="Working issues")
        tracker["complete"]("issues", duration_ms=123)
        return fake_result

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_save_draft", new_callable=AsyncMock) as mock_save_draft,
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
        patch.dict(sys.modules, {"pipeline_client.backend.pipeline_runner": None}),
    ):
        mock_agent.side_effect = _fake_run_agent
        mock_save_draft.return_value = Path("/tmp/test-race.json")

        await handler.handle(
            {"race_id": "test-race"},
            {"cheap_mode": True, "run_id": "run-steps"},
        )

    mock_fs_logger_cls.assert_called_with("run-steps")
    # start + progress + complete callbacks should all update progress fields
    assert mock_fs_logger_cls.return_value.update_progress.call_count >= 3
    args_list = mock_fs_logger_cls.return_value.update_progress.call_args_list
    assert any(call.kwargs.get("current_step") == "issues" for call in args_list)
    assert any(call.kwargs.get("current_step_progress") == 42 for call in args_list)
    assert any(call.kwargs.get("progress_message") == "Working issues" for call in args_list)


@pytest.mark.asyncio
async def test_v2_handler_uses_fallback_progress_when_run_manager_has_no_local_run():
    """Cloud Function handlers have a run manager module but no in-memory RunInfo."""
    handler = AgentHandler()

    async def _fake_run_agent(*_args, **kwargs):
        tracker = kwargs["step_tracker"]
        tracker["start"]("issues")
        tracker["progress"]("issues", pct=42, message="Working issues")
        return {"id": "test-race", "candidates": [{"name": "Alice", "issues": {}}]}

    with (
        patch("pipeline_client.agent.agent.run_agent", side_effect=_fake_run_agent),
        patch.object(handler, "_save_draft", new_callable=AsyncMock, return_value=Path("/tmp/test-race.json")),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
        patch("pipeline_client.backend.run_manager.run_manager.get_run", return_value=MagicMock()),
    ):
        await handler.handle(
            {"race_id": "test-race"},
            {"run_id": "run-cloud", "enabled_steps": ["issues"]},
        )

    progress_updates = mock_fs_logger_cls.return_value.update_progress.call_args_list
    issue_update = next(call for call in progress_updates if call.kwargs.get("current_step_progress") == 42)
    assert issue_update.args[0] == 42


@pytest.mark.asyncio
async def test_v2_handler_continuation_progress_includes_prior_completed_steps():
    handler = AgentHandler()

    async def _fake_run_agent(*_args, **kwargs):
        tracker = kwargs["step_tracker"]
        tracker["start"]("refinement")
        tracker["progress"]("refinement", pct=25, message="Refining candidates")
        return {"id": "test-race", "candidates": [{"name": "Alice"}]}

    with (
        patch("pipeline_client.agent.agent.run_agent", side_effect=_fake_run_agent),
        patch.object(handler, "_save_draft", new_callable=AsyncMock, return_value=Path("/tmp/test-race.json")),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
    ):
        await handler.handle(
            {"race_id": "test-race"},
            {
                "run_id": "run-continuation",
                "is_continuation": True,
                "enabled_steps": ["refinement", "polling", "voter_resources", "review", "iteration"],
                "all_enabled_steps": [
                    "discovery",
                    "images",
                    "issues",
                    "finance",
                    "refinement",
                    "polling",
                    "voter_resources",
                    "review",
                    "iteration",
                ],
                "completed_steps": ["discovery", "images", "issues", "finance"],
            },
        )

    progress_updates = mock_fs_logger_cls.return_value.update_progress.call_args_list
    refinement_update = next(call for call in progress_updates if call.kwargs.get("current_step_progress") == 25)
    assert refinement_update.args[0] == 58


@pytest.mark.asyncio
async def test_v2_handler_leaves_durable_race_finalization_to_cloud_function():
    """Queue executions must not race the Cloud Function with a stale full-document write."""
    handler = AgentHandler()

    with (
        patch(
            "pipeline_client.agent.agent.run_agent",
            new_callable=AsyncMock,
            return_value={"id": "test-race", "candidates": [{"name": "Alice"}]},
        ),
        patch.object(handler, "_save_draft", new_callable=AsyncMock, return_value=Path("/tmp/test-race.json")),
        patch("pipeline_client.backend.race_manager.race_manager.update_race_metadata") as mock_update_metadata,
    ):
        await handler.handle(
            {"race_id": "test-race"},
            {"run_id": "run-cloud", "queue_item_id": "queue-cloud"},
        )

    mock_update_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_v2_handler_stops_when_queue_item_cancelled():
    """Cloud Function runs should stop at the next step boundary after cancellation."""
    from pipeline_client.backend.handlers.agent import AgentCancelled

    handler = AgentHandler()

    async def _fake_run_agent(*_args, **kwargs):
        tracker = kwargs.get("step_tracker")
        assert tracker is not None
        tracker["start"]("issues")
        return {"id": "test-race", "candidates": [{"name": "Alice", "issues": {}}]}

    queue_doc = MagicMock()
    queue_doc.exists = True
    queue_doc.to_dict.return_value = {"status": "cancelled"}
    queue_ref = MagicMock()
    queue_ref.get.return_value = queue_doc
    queue_coll = MagicMock()
    queue_coll.document.return_value = queue_ref
    mock_db = MagicMock()
    mock_db.collection.return_value = queue_coll

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger", MagicMock()),
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
        patch.dict(sys.modules, {"pipeline_client.backend.pipeline_runner": None}),
    ):
        mock_agent.side_effect = _fake_run_agent
        with pytest.raises(AgentCancelled):
            await handler.handle(
                {"race_id": "test-race"},
                {"cheap_mode": True, "run_id": "run-cancel", "queue_item_id": "item-cancel"},
            )


@pytest.mark.asyncio
async def test_save_draft_rejects_placeholder_only_candidates():
    """A one-candidate Unknown draft should not overwrite usable race data."""
    handler = AgentHandler()

    with pytest.raises(ValueError, match="all candidate names are placeholders"):
        await handler._save_draft(
            "ga-governor-2026",
            {
                "id": "ga-governor-2026",
                "election_date": "2026-11-03",
                "updated_utc": "2026-05-15T00:00:00+00:00",
                "candidates": [{"name": "Unknown"}],
            },
        )


@pytest.mark.asyncio
async def test_save_draft_preserves_baseline_candidate_but_rejects_unverified_update_addition():
    handler = AgentHandler()
    race_json = {
        "id": "ga-house-01-2026",
        "candidates": [
            {"name": "Existing Candidate", "summary": "Previously researched."},
            {"name": "New Candidate", "roster_sources": []},
        ],
    }

    with pytest.raises(ValueError, match="New Candidate"):
        await handler._save_draft(
            "ga-house-01-2026",
            race_json,
            verified_baseline_candidate_names={"existing candidate"},
        )

    assert race_json["candidates"][0]["summary"] == "Previously researched."


@pytest.mark.asyncio
async def test_save_draft_treats_every_fresh_candidate_as_addition(tmp_path):
    handler = AgentHandler()
    unverified = {"id": "ga-house-01-2026", "candidates": [{"name": "Alice Candidate"}]}
    with pytest.raises(ValueError, match="Alice Candidate"):
        await handler._save_draft(
            "ga-house-01-2026",
            unverified,
            verified_baseline_candidate_names=set(),
        )

    verified = {
        "id": "ga-house-01-2026",
        "candidates": [
            {
                "name": "Alice Candidate",
                "roster_sources": [
                    {
                        "url": "https://sos.ga.gov/2026-candidates",
                        "type": "official",
                        "title": "2026 qualified candidates",
                        "evidence": "Alice Candidate filed for Georgia's 1st Congressional District in 2026.",
                        "published_at": "2026-03-10",
                        "race_id": "ga-house-01-2026",
                        "evidence_tier": 1,
                        "retrieval_status": "content",
                    }
                ],
            }
        ],
    }
    with (
        patch("pipeline_client.backend.handlers.agent.local_paths", MagicMock(drafts_dir=tmp_path)),
        patch.object(handler, "_archive_gcs_version", new_callable=AsyncMock),
        patch.object(handler, "_upload_to_gcs", new_callable=AsyncMock),
    ):
        output = await handler._save_draft(
            "ga-house-01-2026",
            verified,
            verified_baseline_candidate_names=set(),
        )

    assert output.exists()
