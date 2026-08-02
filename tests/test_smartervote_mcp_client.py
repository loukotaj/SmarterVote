import os
from importlib.util import find_spec
from unittest.mock import AsyncMock

import httpx
import pytest

from smartervote_mcp.client import RacesApiClient, compact_options
from smartervote_mcp.gcp_launcher import _cloud_run_audience, configure_cloud_run_identity_token_from_gcp


@pytest.mark.asyncio
async def test_smartervote_mcp_exposes_lean_tool_surface():
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp.server import mcp

    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "health",
        "list_published_races",
        "list_race_summaries",
        "get_published_race",
        "list_admin_races",
        "scan_catalog",
        "get_race_record",
        "list_draft_races",
        "list_pipeline_steps",
        "get_race_data",
        "audit_draft_vs_published",
        "plan_repairs",
        "audit_race_assets",
        "assess_publish_readiness",
        "queue_races",
        "refresh_race_core",
        "run_race",
        "publish_race",
        "publish_races",
        "list_unpublished_drafts",
        "unpublish_race",
        "recheck_race",
        "recheck_all_races",
        "list_races_by_state",
        "delete_race",
        "delete_draft",
        "sleep",
        "cancel_race",
        "get_queue",
        "list_runs",
        "list_active_runs",
        "get_run",
        "get_run_logs",
        "get_run_diagnostics",
        "list_race_runs",
        "get_race_run",
        "list_race_versions",
        "get_race_version",
        "restore_race_version",
        "cancel_or_delete_run",
        "get_pipeline_metrics",
        "get_pipeline_metrics_summary",
        "get_gcp_pipeline_costs",
        "summarize_run_costs",
        "clear_races_api_cache",
        "get_analytics_overview",
        "get_race_analytics",
        "get_analytics_timeseries",
        "get_traffic_analytics",
        "publish_chamber_forecasts",
        "review_chamber_forecast_drafts",
        "generate_chamber_forecasts",
        "sync_kalshi_markets",
        "verify_live_forecast_page_data",
    }


@pytest.mark.asyncio
async def test_races_api_client_adds_auth_headers(monkeypatch):
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["admin_key"] = request.headers.get("x-admin-key")
        seen["serverless_authorization"] = request.headers.get("x-serverless-authorization")
        return httpx.Response(200, json={"ok": True})

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)
    client = RacesApiClient(
        base_url="http://races.test/",
        bearer_token="jwt",
        admin_key="key",
        cloud_run_id_token="google-id-token",
    )

    assert await client.get("/health") == {"ok": True}
    assert seen == {
        "authorization": "Bearer jwt",
        "admin_key": "key",
        "serverless_authorization": "Bearer google-id-token",
    }


@pytest.mark.asyncio
async def test_races_api_client_raises_useful_error(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Race not found"})

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)
    client = RacesApiClient(base_url="http://races.test")

    with pytest.raises(RuntimeError, match="races-api 404 for GET /races/missing: Race not found"):
        await client.get("/races/missing")


class _StubRacesClient:
    """Fake RacesApiClient for testing MCP tool logic without network access.

    Keyed purely by path (ignoring query params), since the tools under test never issue
    two different GETs against the same path within one call.
    """

    def __init__(self, get_responses: dict):
        self._responses = get_responses

    async def get(self, path, *, params=None):
        value = self._responses[path]
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.asyncio
async def test_audit_draft_vs_published_reports_roster_and_grade_diffs(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    responses = {
        "/api/races/al-governor-2026/data": {
            "candidates": [{"name": "Doug Jones"}, {"name": "Tommy Tuberville"}],
            "validation_grade": {"grade": "B", "score": 85, "passed": True, "summary": "ok"},
            "pipeline_state": {"complete": True},
        },
        "/races/al-governor-2026": {"candidates": [{"name": "Tommy Tuberville"}]},
        "/api/races/missing-race/data": RuntimeError("races-api 404 for GET /api/races/missing-race/data: not found"),
        "/races/missing-race": RuntimeError("races-api 404 for GET /races/missing-race: not found"),
    }
    monkeypatch.setattr(server, "_client", lambda: _StubRacesClient(responses))

    result = await server.audit_draft_vs_published(["al-governor-2026", "missing-race"])

    assert result["race_count"] == 2
    assert result["mismatched_race_ids"] == ["al-governor-2026"]
    assert result["rows"][0] == {
        "race_id": "al-governor-2026",
        "draft_exists": True,
        "published_exists": True,
        "full": True,
        "draft_count": 2,
        "published_count": 1,
        "draft_names": ["Doug Jones", "Tommy Tuberville"],
        "published_names": ["Tommy Tuberville"],
        "names_match": False,
        "grade": "B",
        "passed": True,
    }
    missing_row = result["rows"][1]
    assert missing_row["race_id"] == "missing-race"
    assert missing_row["draft_exists"] is False
    assert missing_row["published_exists"] is False
    assert missing_row["names_match"] is True  # both rosters empty counts as "matching"
    assert missing_row["grade"] is None


@pytest.mark.asyncio
async def test_scan_catalog_returns_compact_ranked_health_rows(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    monkeypatch.setattr(
        server,
        "list_admin_races",
        AsyncMock(
            return_value={
                "races": [
                    {
                        "race_id": "ca-house-05-2026",
                        "state": "California",
                        "office": "U.S. House",
                        "published_exists": True,
                        "quality_grade": None,
                        "freshness": "stale",
                        "candidates": [{"name": "One", "image_url": None}, {"name": "Two", "image_url": "https://ok"}],
                        "forecast": {"rating": "lean_r"},
                    },
                    {
                        "race_id": "ca-house-06-2026",
                        "state": "California",
                        "office": "U.S. House",
                        "published_exists": True,
                        "quality_grade": "A",
                        "freshness": "recent",
                        "candidates": [{"name": "Three", "image_url": "https://ok"}],
                        "forecast": {"rating": "safe_d"},
                    },
                ]
            }
        ),
    )
    monkeypatch.setattr(
        server,
        "_client",
        lambda: _StubRacesClient(
            {
                "/analytics/traffic": {
                    "configured": True,
                    "top_pages": [
                        {"name": "/races/ca-house-05-2026", "pageviews": 1000},
                        {"name": "/races/ca-house-05-2026/candidates/one", "pageviews": 240},
                    ],
                },
                "/analytics/races": {
                    "races": [{"race_id": "ca-house-05-2026", "requests_24h": 17}],
                },
            }
        ),
    )

    result = await server.scan_catalog(
        state="California",
        office="House",
        publication="published",
        research_tier="discovery_only",
        missing_images_only=True,
        competitive_only=True,
    )

    assert result["matched"] == 1
    assert result["has_more"] is False
    assert result["rows"][0]["race_id"] == "ca-house-05-2026"
    assert result["rows"][0]["research_tier"] == "discovery_only"
    assert result["rows"][0]["missing_image_count"] == 1
    assert result["rows"][0]["pageviews"] == 1240
    assert result["rows"][0]["api_requests"] == 17
    assert result["rows"][0]["priority_reasons"] == [
        "discovery_only",
        "competitive",
        "missing_images",
        "stale",
        "user_demand",
    ]
    assert result["summary"]["traffic_configured"] is True


@pytest.mark.asyncio
async def test_plan_repairs_forwards_bounded_read_only_request(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    client = type("Client", (), {"post": AsyncMock(return_value={"plans": []})})()
    monkeypatch.setattr(server, "_client", lambda: client)

    result = await server.plan_repairs(["ca-house-05-2026"])

    assert result == {"plans": []}
    client.post.assert_awaited_once_with(
        "/api/races/repair-plan",
        json={"race_ids": ["ca-house-05-2026"]},
    )


@pytest.mark.asyncio
async def test_audit_race_assets_forwards_persistence_controls(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    client = type("Client", (), {"post": AsyncMock(return_value={"results": []})})()
    monkeypatch.setattr(server, "_client", lambda: client)

    await server.audit_race_assets(["ca-house-05-2026"], persist=True, max_urls_per_race=25)

    client.post.assert_awaited_once_with(
        "/api/races/asset-audit",
        json={"race_ids": ["ca-house-05-2026"], "persist": True, "max_urls_per_race": 25},
    )


@pytest.mark.asyncio
async def test_refresh_race_core_queues_auditable_standard_step_set(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    queued = AsyncMock(return_value={"added": [{"race_id": "al-house-02-2026"}], "errors": []})
    monkeypatch.setattr(server, "queue_races", queued)

    result = await server.refresh_race_core(["al-house-02-2026"])

    assert result["mode"] == "core_refresh"
    assert result["enabled_steps"] == ["discovery", "images", "polling", "forecast", "voter_resources"]
    queued.assert_awaited_once_with(
        ["al-house-02-2026"],
        cheap_mode=True,
        force_fresh=False,
        baseline_source="latest",
        save_artifact=True,
        enabled_steps=["discovery", "images", "polling", "forecast", "voter_resources"],
        debug_mode=True,
        note="Pipeline-driven core refresh: roster, summaries, polling, forecast, and resources.",
        goal=(
            "Verify the exact office/district roster from current-cycle evidence, remove wrong-contest contamination, "
            "refresh candidate summaries, then update polling and the evidence-backed forecast."
        ),
        runner="local",
    )


@pytest.mark.asyncio
async def test_recheck_all_races_follows_bounded_cursor_pages(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    client = type(
        "Client",
        (),
        {
            "request": AsyncMock(
                side_effect=[
                    {"checked": 50, "updated": 10, "has_more": True, "next_cursor": "race-050"},
                    {"checked": 8, "updated": 2, "has_more": False, "next_cursor": None},
                ]
            )
        },
    )()
    monkeypatch.setattr(server, "_client", lambda: client)

    result = await server.recheck_all_races()

    assert result == {
        "message": "Rechecked 58 races across 2 page(s)",
        "checked": 58,
        "updated": 12,
        "page_count": 2,
    }
    assert client.request.await_count == 2
    assert client.request.await_args_list[1].kwargs["params"]["cursor"] == "race-050"


@pytest.mark.asyncio
async def test_assess_publish_readiness_blocks_failed_or_placeholder_drafts(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    responses = {
        "/api/races/ca-house-01-2026/data": {
            "candidates": [{"name": "Ready Candidate"}],
            "validation_grade": {"passed": True},
            "run_health": {"status": "healthy"},
            "pipeline_state": {"complete": True},
        },
        "/races/ca-house-01-2026": {"candidates": [{"name": "Old Candidate"}]},
        "/api/races/ca-house-02-2026/data": {
            "candidates": [{"name": "DRAFT"}],
            "validation_grade": {"passed": False},
            "run_health": {"verdict": "failed"},
            "pipeline_state": {"complete": False},
        },
        "/races/ca-house-02-2026": RuntimeError("not published"),
    }
    monkeypatch.setattr(server, "_client", lambda: _StubRacesClient(responses))

    result = await server.assess_publish_readiness(["ca-house-01-2026", "ca-house-02-2026"])

    assert result["ready_race_ids"] == ["ca-house-01-2026"]
    assert result["blocked_race_ids"] == ["ca-house-02-2026"]
    assert result["rows"][0]["warnings"] == ["candidate_roster_changes"]
    assert set(result["rows"][1]["blockers"]) == {
        "validation_not_passed",
        "run_health_failed",
        "literal_placeholder_content",
    }
    assert "pipeline_not_complete" in result["rows"][1]["warnings"]


@pytest.mark.asyncio
async def test_assess_publish_readiness_allows_unreviewed_maintenance_draft(monkeypatch):
    """A discovery/polling/forecast draft has no grade and the races-api still publishes it.

    ``gcs_helpers._assert_publishable_race`` only rejects ``passed is False`` and
    tolerates ``remaining_steps == ["review"]``, so treating a missing grade as a
    blocker made this tool contradict the endpoint it is supposed to predict.
    """
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    responses = {
        "/api/races/ne-house-02-2026/data": {
            "candidates": [{"name": "Denise Powell"}, {"name": "Brinker Harding"}],
            "validation_grade": None,
            "reviews": [],
            "pipeline_state": {"complete": False, "remaining_steps": ["review"]},
        },
        "/races/ne-house-02-2026": {"candidates": [{"name": "Denise Powell"}]},
        "/api/races/ne-house-03-2026/data": {
            "candidates": [{"name": "Adrian Smith"}],
            "validation_grade": None,
            "pipeline_state": {"complete": False, "remaining_steps": ["issues", "review"]},
        },
        "/races/ne-house-03-2026": {"candidates": [{"name": "Adrian Smith"}]},
    }
    monkeypatch.setattr(server, "_client", lambda: _StubRacesClient(responses))

    result = await server.assess_publish_readiness(["ne-house-02-2026", "ne-house-03-2026"])

    assert result["ready_race_ids"] == ["ne-house-02-2026"]
    assert set(result["rows"][0]["warnings"]) == {
        "validation_absent_unreviewed",
        "run_health_unknown",
        "pipeline_not_complete",
        "candidate_roster_changes",
    }
    # Work outstanding beyond `review` is a hard rejection at the API, not a warning.
    assert result["rows"][1]["blockers"] == ["pipeline_incomplete_beyond_review"]


@pytest.mark.asyncio
async def test_assess_publish_readiness_blocks_unresolved_review_flags(monkeypatch):
    """The API rejects warning-or-higher review flags even with a passing grade."""
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    responses = {
        "/api/races/nh-senate-2026/data": {
            "candidates": [{"name": "Alice Example"}],
            "validation_grade": {"passed": True, "grade": "A"},
            "reviews": [{"flags": [{"severity": "warning", "concern": "Summary has no sources."}]}],
            "pipeline_state": {"complete": True},
        },
        "/races/nh-senate-2026": {"candidates": [{"name": "Alice Example"}]},
    }
    monkeypatch.setattr(server, "_client", lambda: _StubRacesClient(responses))

    result = await server.assess_publish_readiness(["nh-senate-2026"])

    assert result["rows"][0]["blockers"] == ["unresolved_review_flags"]


@pytest.mark.asyncio
async def test_publish_races_never_posts_when_readiness_is_blocked(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    client = type("Client", (), {"post": AsyncMock()})()
    monkeypatch.setattr(server, "_client", lambda: client)
    monkeypatch.setattr(
        server,
        "assess_publish_readiness",
        AsyncMock(
            return_value={
                "all_ready": False,
                "blocked_race_ids": ["ca-house-02-2026"],
                "ready_race_ids": ["ca-house-01-2026"],
            }
        ),
    )

    result = await server.publish_races(["ca-house-01-2026", "ca-house-02-2026"])

    assert result["published"] == []
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_races_and_run_race_forward_debug_mode(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    client = type("Client", (), {"post": AsyncMock(return_value={"added": []})})()
    monkeypatch.setattr(server, "_client", lambda: client)

    await server.queue_races(["ca-house-05-2026"], debug_mode=True)
    await server.run_race("ca-house-05-2026", debug_mode=True)

    first_call, second_call = client.post.await_args_list
    assert first_call.kwargs["json"]["options"]["debug_mode"] is True
    assert second_call.kwargs["json"]["debug_mode"] is True


@pytest.mark.asyncio
async def test_get_run_logs_forwards_opaque_cursor(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    client = type("Client", (), {"get": AsyncMock(return_value={"logs": [], "next_cursor": "002"})})()
    monkeypatch.setattr(server, "_client", lambda: client)

    await server.get_run_logs("run-1", cursor="001", limit=25)

    client.get.assert_awaited_once_with("/runs/run-1/logs", params={"cursor": "001", "limit": 25})


@pytest.mark.asyncio
async def test_summarize_run_costs_normalizes_nested_and_top_level_fields(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    responses = {
        "/runs/run-full": {
            "run_id": "run-full",
            "race_id": "ar-governor-2026",
            "status": "completed",
            "estimated_usd": 3.6,
            "prompt_tokens": 111,
            "completion_tokens": 11,
            "model_breakdown": {
                "google/gemini-2.5-flash": {"prompt_tokens": 100, "completion_tokens": 10},
            },
        },
        "/runs/run-nested": {
            "run_id": "run-nested",
            "status": "failed",
            "payload": {
                "race_id": "al-house-02-2026",
                "agent_metrics": {
                    "model_breakdown": {
                        "google/gemini-2.5-flash": {"prompt_tokens": 200, "completion_tokens": 20},
                    },
                },
            },
        },
        "/runs/run-missing": RuntimeError("races-api 404 for GET /runs/run-missing: Run not found"),
    }
    monkeypatch.setattr(server, "_client", lambda: _StubRacesClient(responses))

    result = await server.summarize_run_costs(["run-full", "run-nested", "run-missing"])

    assert result["status_counts"] == {"completed": 1, "failed": 1, "missing": 1}
    assert result["failed_run_ids"] == ["run-nested"]
    assert result["active_run_ids"] == []
    assert result["totals"] == {
        "cost": 3.6,
        "prompt_tokens": 311,
        "completion_tokens": 31,
        "run_count": 3,
    }

    full_row, nested_row, missing_row = result["rows"]
    assert full_row["race_id"] == "ar-governor-2026"
    assert full_row["has_cost"] is True
    assert nested_row["race_id"] == "al-house-02-2026"
    assert nested_row["has_cost"] is False
    assert nested_row["cost"] == 0.0
    assert nested_row["prompt_tokens"] == 200
    assert missing_row == {"run_id": "run-missing", "status": "missing"}


@pytest.mark.asyncio
async def test_summarize_run_costs_prefers_exact_metrics_record(monkeypatch):
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp import server

    responses = {
        "/pipeline/metrics": {
            "records": [
                {
                    "run_id": "run-1",
                    "race_id": "ca-house-05-2026",
                    "cost_usd": 0.6037413091999998,
                    "estimated_usd": 0.595471,
                    "cost_source": "provider",
                    "prompt_tokens": 2813117,
                    "completion_tokens": 303664,
                    "model_breakdown": {},
                }
            ]
        },
        "/runs/run-1": {
            "run_id": "run-1",
            "race_id": "ca-house-05-2026",
            "status": "completed",
        },
    }
    monkeypatch.setattr(server, "_client", lambda: _StubRacesClient(responses))

    result = await server.summarize_run_costs(["run-1"])

    assert result["rows"][0]["cost"] == 0.6037413091999998
    assert result["rows"][0]["cost_source"] == "provider"
    assert result["rows"][0]["prompt_tokens"] == 2813117
    assert result["totals"]["cost"] == 0.6037413091999998


def test_compact_options_keeps_false_and_drops_none():
    assert compact_options(cheap_mode=False, note=None, goal="refresh") == {"cheap_mode": False, "goal": "refresh"}


def test_races_api_client_from_env_reads_environment(monkeypatch):
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "https://races.example.com/api/")
    monkeypatch.setenv("SMARTERVOTE_RACES_API_TOKEN", "jwt-token")
    monkeypatch.setenv("SMARTERVOTE_RACES_API_ADMIN_KEY", "admin-key")
    monkeypatch.setenv("SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN", "id-token")
    monkeypatch.setenv("SMARTERVOTE_RACES_API_TIMEOUT", "15")

    client = RacesApiClient.from_env()

    assert client.base_url == "https://races.example.com/api"
    assert client.bearer_token == "jwt-token"
    assert client.admin_key == "admin-key"
    assert client.cloud_run_id_token == "id-token"
    assert client.timeout_seconds == 15.0


def test_races_api_client_from_env_falls_back_to_defaults(monkeypatch):
    for var in (
        "SMARTERVOTE_RACES_API_URL",
        "RACES_API_URL",
        "SMARTERVOTE_RACES_API_TOKEN",
        "RACES_API_BEARER_TOKEN",
        "SMARTERVOTE_RACES_API_ADMIN_KEY",
        "ADMIN_API_KEY",
        "SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN",
        "SMARTERVOTE_RACES_API_ID_TOKEN",
        "RACES_API_CLOUD_RUN_ID_TOKEN",
        "SMARTERVOTE_RACES_API_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)

    client = RacesApiClient.from_env()

    assert client.base_url == "http://127.0.0.1:8080"
    assert client.bearer_token == ""
    assert client.admin_key == ""
    assert client.cloud_run_id_token == ""
    assert client.timeout_seconds == 60.0


def test_races_api_client_from_env_invalid_timeout_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SMARTERVOTE_RACES_API_TIMEOUT", "not-a-number")

    client = RacesApiClient.from_env()

    assert client.timeout_seconds == 60.0


@pytest.mark.asyncio
async def test_races_api_client_returns_none_for_empty_response_body(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)
    client = RacesApiClient(base_url="http://races.test")

    assert await client.delete("/races/x") is None


@pytest.mark.asyncio
async def test_races_api_client_error_with_non_json_body_uses_raw_text(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal server error, not json")

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)
    client = RacesApiClient(base_url="http://races.test")

    with pytest.raises(RuntimeError, match="internal server error, not json"):
        await client.post("/do-thing", json={"a": 1})


def test_mcp_pipeline_options_default_to_cheap_mode():
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp.server import _pipeline_options

    assert _pipeline_options(note="refresh") == {"cheap_mode": True, "note": "refresh"}
    assert _pipeline_options(baseline_source="published") == {
        "cheap_mode": True,
        "baseline_source": "published",
    }
    assert _pipeline_options(resume_partial=True) == {
        "cheap_mode": True,
        "resume_partial": True,
    }


def test_mcp_pipeline_options_require_explicit_false_for_quality_profile():
    if find_spec("mcp") is None:
        pytest.skip("MCP SDK is optional outside the local MCP environment")

    from smartervote_mcp.server import _pipeline_options

    with pytest.raises(ValueError, match="requires explicit cheap_mode=False"):
        _pipeline_options(model_profile="quality")

    assert _pipeline_options(cheap_mode=False, model_profile="quality") == {
        "cheap_mode": False,
        "model_profile": "quality",
    }


def test_cloud_run_audience_detects_run_app_url(monkeypatch):
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "https://races-api-dev-ddsvfazica-uc.a.run.app/api")

    assert _cloud_run_audience() == "https://races-api-dev-ddsvfazica-uc.a.run.app"


def test_cloud_run_audience_ignores_local_url(monkeypatch):
    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "http://127.0.0.1:8080")

    assert _cloud_run_audience() is None


def test_configure_cloud_run_identity_token_from_gcp(monkeypatch):
    calls = []

    def fake_run_gcloud(args):
        calls.append(args)
        return "token"

    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "https://races-api-dev-ddsvfazica-uc.a.run.app")
    monkeypatch.setenv("SMARTERVOTE_GCP_PROJECT", "smartervote")
    monkeypatch.setenv("SMARTERVOTE_GCP_ENVIRONMENT", "dev")
    monkeypatch.setenv("SMARTERVOTE_RACES_API_USE_CLOUD_RUN_ID_TOKEN", "true")
    monkeypatch.delenv("SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN", raising=False)
    monkeypatch.delenv("SMARTERVOTE_RACES_API_ID_TOKEN", raising=False)
    monkeypatch.delenv("SMARTERVOTE_RACES_API_IMPERSONATE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.setattr("smartervote_mcp.gcp_launcher._run_gcloud", fake_run_gcloud)

    configure_cloud_run_identity_token_from_gcp()

    assert calls == [
        [
            "auth",
            "print-identity-token",
            "--audiences=https://races-api-dev-ddsvfazica-uc.a.run.app",
            "--impersonate-service-account=races-api-dev@smartervote.iam.gserviceaccount.com",
        ]
    ]
    assert os.environ["SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN"] == "token"


def test_configure_cloud_run_identity_token_is_opt_out(monkeypatch):
    calls = []

    def fake_run_gcloud(args):
        calls.append(args)
        return "token"

    monkeypatch.setenv("SMARTERVOTE_RACES_API_URL", "https://races-api-dev-ddsvfazica-uc.a.run.app")
    monkeypatch.setenv("SMARTERVOTE_RACES_API_USE_CLOUD_RUN_ID_TOKEN", "false")
    monkeypatch.delenv("SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN", raising=False)
    monkeypatch.delenv("SMARTERVOTE_RACES_API_ID_TOKEN", raising=False)
    monkeypatch.delenv("SMARTERVOTE_RACES_API_IMPERSONATE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.setattr("smartervote_mcp.gcp_launcher._run_gcloud", fake_run_gcloud)

    configure_cloud_run_identity_token_from_gcp()

    assert calls == []
    assert "SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN" not in os.environ
