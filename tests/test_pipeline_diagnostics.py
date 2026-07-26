"""Tests for self-contained pipeline diagnostic exports."""

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

RACES_API_DIR = pathlib.Path(__file__).parent.parent / "services" / "races-api"

import pytest

if str(RACES_API_DIR) not in sys.path:
    sys.path.insert(0, str(RACES_API_DIR))

from pipeline_diagnostics import build_diagnostics_bundle

from shared.pipeline_options import PipelineRunOptions


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


def test_debug_mode_is_a_canonical_pipeline_option():
    options = PipelineRunOptions(debug_mode=True)

    assert options.model_dump(exclude_none=True)["debug_mode"] is True


def test_diagnostics_bundle_combines_and_sanitizes_run_evidence():
    exposed_url = "https://example.test/search?key=secret-value&mode=debug"
    run_doc = _Doc(
        "run-debug",
        {
            "run_id": "run-debug",
            "race_id": "tx-senate-2026",
            "status": "completed",
            "debug_mode": True,
            "options": {"debug_mode": True, "enabled_steps": ["discovery"]},
        },
    )
    log_docs = [
        _Doc(
            "001",
            {
                "timestamp": "2026-07-26T12:00:00+00:00",
                "level": "info",
                "message": f"Step started via {exposed_url}",
                "step": "discovery",
                "extra": {"event": "step_started", "overall_progress": 1},
            },
        ),
        _Doc(
            "002",
            {
                "timestamp": "2026-07-26T12:00:01+00:00",
                "level": "warning",
                "message": "Candidate summary was missing",
                "step": "discovery",
                "extra": {"event": "agent_log"},
            },
        ),
    ]
    queue_docs = [
        _Doc(
            "queue-1",
            {"id": "queue-1", "run_id": "run-debug", "status": "completed", "runner": "cloud_run"},
        )
    ]
    race_doc = _Doc("tx-senate-2026", {"race_id": "tx-senate-2026", "status": "draft"})

    run_ref = MagicMock()
    run_ref.get.return_value = run_doc
    log_collection = run_ref.collection.return_value
    log_collection.order_by.return_value = log_collection
    log_collection.limit.return_value = log_collection
    log_collection.stream.return_value = iter(log_docs)
    runs_collection = MagicMock()
    runs_collection.document.return_value = run_ref

    queue_query = MagicMock()
    queue_query.limit.return_value = queue_query
    queue_query.stream.return_value = iter(queue_docs)
    queue_collection = MagicMock()
    queue_collection.where.return_value = queue_query

    race_ref = MagicMock()
    race_ref.get.return_value = race_doc
    races_collection = MagicMock()
    races_collection.document.return_value = race_ref

    db = MagicMock()
    db.collection.side_effect = lambda name: {
        "pipeline_runs": runs_collection,
        "pipeline_queue": queue_collection,
        "races": races_collection,
    }[name]
    draft = {
        "id": "tx-senate-2026",
        "candidates": [
            {
                "name": "Alice Example",
                "summary": "Candidate summary",
                "summary_sources": ["https://example.test/summary"],
                "roster_sources": ["https://example.test/roster"],
                "issues": {
                    "healthcare": {"stance": "DRAFT", "sources": []},
                    "economy": {"stance": "Supports lower taxes", "sources": ["https://example.test/tax"]},
                },
            }
        ],
        "pipeline_state": {"complete": True, "remaining_steps": []},
        "validation_grade": {"grade": "B", "passed": True},
        "agent_metrics": {"total_tokens": 1234, "estimated_usd": 0.02},
    }

    with patch("pipeline_diagnostics._load_draft", return_value=draft):
        bundle = build_diagnostics_bundle("run-debug", db)

    assert bundle is not None
    assert bundle["schema"] == "smartervote.pipeline-diagnostics.v1"
    assert bundle["debug_mode"] is True
    assert bundle["summary"]["log_levels"] == {"info": 1, "warning": 1}
    assert bundle["summary"]["event_counts"] == {"step_started": 1, "agent_log": 1}
    assert bundle["summary"]["draft_quality"]["placeholder_stance_count"] == 1
    assert bundle["summary"]["draft_quality"]["candidate_count"] == 1
    assert bundle["timeline"][0]["event"] == "step_started"
    assert bundle["queue_items"][0]["id"] == "queue-1"
    assert "secret-value" not in bundle["logs"][0]["message"]
    assert "key=[REDACTED]" in bundle["logs"][0]["message"]
    log_collection.limit.assert_called_once_with(2000)


@pytest.mark.asyncio
async def test_debug_mode_emits_structured_step_events_and_step_context():
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()

    async def fake_run_agent(*_args, **kwargs):
        tracker = kwargs["step_tracker"]
        tracker["start"]("discovery")
        tracker["progress"]("discovery", pct=41, message="Checking roster")
        tracker["progress"]("discovery", pct=49, message="Still checking roster")
        kwargs["on_log"]("warning", "Roster source needs review")
        tracker["complete"]("discovery", duration_ms=321)
        return {"id": "test-race", "candidates": [{"name": "Alice", "issues": {}}]}

    with (
        patch("pipeline_client.agent.agent.run_agent", side_effect=fake_run_agent),
        patch.object(
            handler,
            "_save_draft",
            new_callable=AsyncMock,
            return_value=pathlib.Path("/tmp/test-race.json"),
        ),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as logger_class,
    ):
        await handler.handle(
            {"race_id": "test-race"},
            {"run_id": "run-debug", "debug_mode": True, "enabled_steps": ["discovery"]},
        )

    log_calls = logger_class.return_value.log.call_args_list
    events = [call.kwargs.get("extra", {}).get("event") for call in log_calls if call.kwargs.get("extra")]
    assert events.count("step_progress") == 1
    assert "step_started" in events
    assert "step_completed" in events
    agent_log = next(call for call in log_calls if call.kwargs.get("extra", {}).get("event") == "agent_log")
    assert agent_log.kwargs["step"] == "discovery"
