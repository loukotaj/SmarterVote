import os

import httpx
import pytest

from smartervote_mcp.client import RacesApiClient, compact_options
from smartervote_mcp.gcp_launcher import _cloud_run_audience, configure_cloud_run_identity_token_from_gcp


@pytest.mark.asyncio
async def test_smartervote_mcp_exposes_lean_tool_surface():
    from smartervote_mcp.server import mcp

    tools = await mcp.list_tools()
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "health",
        "list_published_races",
        "list_race_summaries",
        "get_published_race",
        "list_admin_races",
        "get_race_record",
        "list_draft_races",
        "list_pipeline_steps",
        "get_race_data",
        "queue_races",
        "run_race",
        "publish_race",
        "publish_races",
        "list_unpublished_drafts",
        "trigger_web_deploy",
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
        "cancel_or_delete_run",
        "get_pipeline_metrics",
        "get_pipeline_metrics_summary",
        "clear_races_api_cache",
        "get_analytics_overview",
        "get_race_analytics",
        "get_analytics_timeseries",
        "get_traffic_analytics",
        "update_chamber_forecasts",
        "publish_chamber_forecasts",
        "review_chamber_forecast_drafts",
        "generate_chamber_forecasts",
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


def test_compact_options_keeps_false_and_drops_none():
    assert compact_options(cheap_mode=False, note=None, goal="refresh") == {"cheap_mode": False, "goal": "refresh"}


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
