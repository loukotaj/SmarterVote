"""Tests for the races API service.

Covers:
- Health/root endpoints
- List races
- Get race summaries
- Get individual race by ID
- 404 for missing races
"""

import json
import os
import sys
import tempfile
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from simple_publish_service import SimplePublishService

# Add project root for shared imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _load_main_module(data_dir: str, monkeypatch) -> Any:
    """Reload config/main against an isolated temp data directory."""
    monkeypatch.setenv("DATA_DIR", data_dir)
    monkeypatch.delenv("GCS_BUCKET_NAME", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("CLOUD_RUN_SERVICE", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("GAE_APPLICATION", raising=False)
    monkeypatch.delenv("SKIP_AUTH", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ANALYTICS_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ANALYTICS_ACCOUNT_TAG", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ANALYTICS_SITE_TAG", raising=False)

    import importlib

    # Reload modules in order of dependency to avoid using stale DATA_DIR
    import constants

    importlib.reload(constants)

    import config as cfg_mod

    importlib.reload(cfg_mod)

    import gcs_helpers

    importlib.reload(gcs_helpers)

    import firestore_helpers

    importlib.reload(firestore_helpers)

    import routers.races_admin

    importlib.reload(routers.races_admin)

    import main as main_mod
    import rate_limit
    import routers.payments

    importlib.reload(rate_limit)
    importlib.reload(routers.payments)
    main_mod = importlib.reload(main_mod)
    setattr(main_mod, "publish_service", main_mod.SimplePublishService(data_directory=data_dir))
    main_mod.limiter.reset()
    return main_mod


@pytest.fixture
def sample_race():
    """Minimal valid RaceJSON data."""
    return {
        "id": "mo-senate-2024",
        "title": "Missouri Senate Race",
        "office": "U.S. Senator",
        "jurisdiction": "Missouri",
        "election_date": "2024-11-05",
        "updated_utc": "2024-06-01T12:00:00Z",
        "generator": ["pipeline-agent"],
        "candidates": [
            {
                "name": "Jane Doe",
                "party": "Democrat",
                "incumbent": False,
                "summary": "A candidate.",
                "issues": {},
                "career_history": [],
                "education": [],
                "donor_summary": None,
                "links": [],
                "social_media": {},
            }
        ],
    }


@pytest.fixture
def data_dir(sample_race):
    """Create a temporary data directory with a sample race file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        race_file = os.path.join(tmpdir, "mo-senate-2024.json")
        with open(race_file, "w") as f:
            json.dump(sample_race, f)
        yield tmpdir


@pytest.fixture
def client(data_dir, monkeypatch):
    """Create a test client with DATA_DIR pointed at the temp directory."""
    main_mod = _load_main_module(data_dir, monkeypatch)
    from auth import verify_token

    main_mod.app.dependency_overrides[verify_token] = lambda: {"auth": "test"}
    with TestClient(main_mod.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_races(client):
    """GET /races returns list of race IDs."""
    resp = client.get("/races")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert "mo-senate-2024" in data


def test_get_race_summaries(client):
    """GET /races/summaries returns list of race summary objects."""
    resp = client.get("/races/summaries")
    assert resp.status_code == 200
    summaries = resp.json()
    assert isinstance(summaries, list)
    assert len(summaries) == 1
    assert summaries[0]["id"] == "mo-senate-2024"
    assert summaries[0]["office"] == "U.S. Senator"
    assert len(summaries[0]["candidates"]) == 1
    assert summaries[0]["candidates"][0]["name"] == "Jane Doe"


def test_get_race_by_id(client):
    """GET /races/{race_id} returns full race data."""
    resp = client.get("/races/mo-senate-2024")
    assert resp.status_code == 200
    race = resp.json()
    assert race["id"] == "mo-senate-2024"
    assert len(race["candidates"]) == 1


def test_get_race_not_found(client):
    """GET /races/{race_id} returns 404 for missing race."""
    resp = client.get("/races/nonexistent-race-9999")
    assert resp.status_code == 404


def test_list_races_empty(monkeypatch):
    """GET /races returns empty list when no data directory exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _load_main_module(tmpdir, monkeypatch)
        from auth import verify_token

        main_mod.app.dependency_overrides[verify_token] = lambda: {"auth": "test"}
        test_client = TestClient(main_mod.app)
        resp = test_client.get("/races")
        assert resp.status_code == 200
        assert resp.json() == []


def test_cloud_listing_uses_static_summaries_index(tmp_path):
    service = SimplePublishService.__new__(SimplePublishService)
    service.data_directory = tmp_path
    service.gcs_bucket_name = "test-bucket"
    service.cloud_configured = True
    service.cache_ttl = 0
    service._race_list_cache = None
    service._race_data_cache = {}
    service._race_summaries_cache = None
    service._cache_lock = threading.Lock()

    race_blob = MagicMock()
    race_blob.name = "races/ga-senate-2026.json"
    race_blob.download_as_text.return_value = json.dumps({"id": "ga-senate-2026", "candidates": []})
    index_blob = MagicMock()
    index_blob.name = "races/summaries.json"
    index_blob.exists.return_value = True
    index_blob.download_as_text.return_value = json.dumps([{"id": "ga-senate-2026"}])

    bucket = MagicMock()
    bucket.list_blobs.return_value = [race_blob, index_blob]
    bucket.blob.return_value = index_blob
    service.gcs_client = MagicMock()
    service.gcs_client.bucket.return_value = bucket

    assert service.get_published_races() == ["ga-senate-2026"]
    assert [summary["id"] for summary in service.get_race_summaries()] == ["ga-senate-2026"]
    bucket.list_blobs.assert_not_called()


def test_cloud_listing_does_not_scan_gcs_when_summaries_index_is_missing(tmp_path):
    service = SimplePublishService.__new__(SimplePublishService)
    service.data_directory = tmp_path
    service.gcs_bucket_name = "test-bucket"
    service.cloud_configured = True
    service.cache_ttl = 0
    service._race_list_cache = None
    service._race_data_cache = {}
    service._race_summaries_cache = None
    service._cache_lock = threading.Lock()

    index_blob = MagicMock()
    index_blob.exists.return_value = False

    bucket = MagicMock()
    bucket.blob.return_value = index_blob
    service.gcs_client = MagicMock()
    service.gcs_client.bucket.return_value = bucket

    assert service.get_published_races() == []
    assert service.get_race_summaries() == []
    bucket.list_blobs.assert_not_called()


def test_local_listing_uses_static_summaries_index(tmp_path):
    sample_summary = [{"id": "ga-senate-2026", "title": "Georgia Senate Race", "candidates": []}]
    (tmp_path / "summaries.json").write_text(json.dumps(sample_summary), encoding="utf-8")

    service = SimplePublishService.__new__(SimplePublishService)
    service.data_directory = tmp_path
    service.gcs_bucket_name = ""
    service.cloud_configured = False
    service.gcs_client = None
    service.cache_ttl = 0
    service._race_list_cache = None
    service._race_data_cache = {}
    service._race_summaries_cache = None
    service._cache_lock = threading.Lock()

    assert service.get_published_races() == ["ga-senate-2026"]
    assert service.get_race_summaries() == sample_summary


def test_race_summary_schema_accepts_forecast():
    from schemas import RaceSummary

    summary = RaceSummary(
        id="ga-senate-2026",
        election_date="2026-11-03",
        updated_utc="2026-06-20T00:00:00Z",
        candidates=[],
        quality_grade="A",
        forecast={
            "predicted_winner_name": "Alice",
            "predicted_winner_party": "Democratic",
            "win_probability": 0.6,
            "party_probabilities": {"Democratic": 0.6, "Republican": 0.4},
            "margin_estimate": 1.5,
            "rating": "tilt_d",
            "confidence": "medium",
            "rationale": "Narrow advantage.",
            "based_on_poll_count": 1,
            "generated_at": "2026-06-20T00:00:00Z",
            "model": "openai/gpt-5.4",
            "source_urls": ["https://example.com/poll"],
        },
    )

    assert summary.forecast is not None
    assert summary.forecast.rating == "tilt_d"
    assert summary.quality_grade == "A"


def test_rate_limit_exceeded(client):
    """Exceeding the rate limit returns 429 Too Many Requests."""
    import main as main_mod

    main_mod.limiter.reset()

    for _ in range(60):
        resp = client.get("/races")
        assert resp.status_code == 200

    resp = client.get("/races")
    assert resp.status_code == 429


def test_rate_limit_bypass_prerender(client):
    """Requests with Origin: http://sveltekit-prerender bypass the rate limit."""
    import main as main_mod

    main_mod.limiter.reset()

    for _ in range(70):
        resp = client.get("/races", headers={"Origin": "http://sveltekit-prerender"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Analytics endpoint tests
# ---------------------------------------------------------------------------


def test_analytics_overview_no_key(client):
    """GET /analytics/overview without admin key returns 401 when key is configured."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = "secret"
    try:
        resp = client.get("/analytics/overview")
        assert resp.status_code == 401
    finally:
        main_mod._ADMIN_API_KEY = original


def test_analytics_overview_wrong_key(client):
    """GET /analytics/overview with wrong key returns 401."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = "secret"
    try:
        resp = client.get("/analytics/overview", headers={"X-Admin-Key": "wrong"})
        assert resp.status_code == 401
    finally:
        main_mod._ADMIN_API_KEY = original


def test_analytics_overview_correct_key(client):
    """GET /analytics/overview with correct key returns 200."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = "secret"
    try:
        resp = client.get("/analytics/overview", headers={"X-Admin-Key": "secret"})
        assert resp.status_code == 200
        assert "total_requests" in resp.json()
    finally:
        main_mod._ADMIN_API_KEY = original


def test_traffic_analytics_reports_unconfigured_provider(client):
    """Static traffic endpoint does not silently report configured zero traffic."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = "secret"
    try:
        resp = client.get("/analytics/traffic", headers={"X-Admin-Key": "secret"})
        assert resp.status_code == 200
        assert resp.json()["configured"] is False
        assert resp.json()["provider"] == "cloudflare"
    finally:
        main_mod._ADMIN_API_KEY = original


def test_analytics_races_correct_key(client):
    """GET /analytics/races with correct key returns 200."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = "secret"
    try:
        resp = client.get("/analytics/races", headers={"X-Admin-Key": "secret"})
        assert resp.status_code == 200
        assert "races" in resp.json()
    finally:
        main_mod._ADMIN_API_KEY = original


def test_analytics_timeseries_correct_key(client):
    """GET /analytics/timeseries with correct key returns 200."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = "secret"
    try:
        resp = client.get("/analytics/timeseries", headers={"X-Admin-Key": "secret"})
        assert resp.status_code == 200
        assert "timeseries" in resp.json()
    finally:
        main_mod._ADMIN_API_KEY = original


def test_analytics_no_key_or_auth_configured(client, monkeypatch):
    """When neither admin key nor Auth0 is configured, admin endpoints return 503."""
    client.app.dependency_overrides.clear()
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = None
    monkeypatch.delenv("AUTH0_DOMAIN", raising=False)
    monkeypatch.delenv("AUTH0_AUDIENCE", raising=False)
    try:
        resp = client.get("/analytics/overview")
        assert resp.status_code == 503
    finally:
        main_mod._ADMIN_API_KEY = original


def test_analytics_no_key_falls_back_to_bearer_auth(client, monkeypatch):
    """When Auth0 is configured, missing bearer credentials return 401."""
    client.app.dependency_overrides.clear()
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = None
    monkeypatch.setenv("AUTH0_DOMAIN", "example.auth0.com")
    monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.example.com")
    try:
        resp = client.get("/analytics/overview")
        assert resp.status_code == 401
    finally:
        main_mod._ADMIN_API_KEY = original


def test_analytics_overview_hours_bounds(client):
    """GET /analytics/overview enforces hours bounds."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = "secret"
    try:
        assert client.get("/analytics/overview?hours=0", headers={"X-Admin-Key": "secret"}).status_code == 422
        assert client.get("/analytics/overview?hours=720", headers={"X-Admin-Key": "secret"}).status_code == 200
        assert client.get("/analytics/overview?hours=721", headers={"X-Admin-Key": "secret"}).status_code == 422
    finally:
        main_mod._ADMIN_API_KEY = original


def test_analytics_timeseries_bucket_bounds(client):
    """GET /analytics/timeseries enforces bucket bounds."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = "secret"
    try:
        assert client.get("/analytics/timeseries?bucket=4", headers={"X-Admin-Key": "secret"}).status_code == 422
        assert client.get("/analytics/timeseries?bucket=5", headers={"X-Admin-Key": "secret"}).status_code == 200
        assert client.get("/analytics/timeseries?bucket=361", headers={"X-Admin-Key": "secret"}).status_code == 422
    finally:
        main_mod._ADMIN_API_KEY = original


def test_chamber_forecasts_endpoints(client, monkeypatch, data_dir):
    """GET and publish for chamber_forecasts."""
    import config
    import gcs_helpers

    monkeypatch.setattr(config, "DATA_DIR", data_dir)

    # First GET when no file exists should return 404
    resp = client.get("/races/chamber_forecasts")
    assert resp.status_code == 404

    # Setup admin key for POST in env
    monkeypatch.setenv("ADMIN_API_KEY", "secret")

    payload = {
        "schema_version": "chamber_forecasts.v2",
        "house": "House is Tilt R",
        "senate": "Senate is Lean D",
        "governors": "Governors is Safe R",
        "updated_at": "2026-06-22T00:00:00+00:00",
        "house_narrative": "House is Tilt R",
        "senate_narrative": "Senate is Lean D",
        "governors_narrative": "Governors is Safe R",
        "chambers": {
            "house": {
                "projected_seats": {"Democratic": 217, "Republican": 218},
                "control_party": "Republican",
                "seat_distribution": {"218R-217D": 1.0},
                "bottom_line": "House is narrowly Republican",
                "why_party_favored": "Seat math",
                "opposing_party_path": "Win one more seat",
                "key_uncertainty": "Close districts",
            },
            "senate": {
                "projected_seats": {"Democratic": 50, "Republican": 50},
                "control_party": "Republican",
                "vp_tiebreak_party": "Republican",
                "seat_distribution": {"50R-50D": 1.0},
                "bottom_line": "Senate is 50-50",
                "why_party_favored": "Fundamentals",
                "opposing_party_path": "Path",
                "key_uncertainty": "Uncertainty",
            },
            "governors": {
                "projected_seats": {"Democratic": 24, "Republican": 26},
                "control_party": "Republican",
                "seat_distribution": {"26R-24D": 1.0},
                "bottom_line": "Governors are narrowly Republican",
                "why_party_favored": "Holdover map",
                "opposing_party_path": "Flip two states",
                "key_uncertainty": "Open seats",
            },
        },
    }

    invalid_schema_payload = json.loads(json.dumps(payload))
    invalid_schema_payload["schema_version"] = "chamber_forecasts.v1"
    gcs_helpers.save_chamber_forecasts(invalid_schema_payload, draft=True)
    publish_resp = client.post("/api/races/chamber_forecasts/publish", headers={"X-Admin-Key": "secret"})
    assert publish_resp.status_code == 400
    assert "Expected schema_version chamber_forecasts.v2" in publish_resp.json()["detail"]

    invalid_totals_payload = json.loads(json.dumps(payload))
    invalid_totals_payload["chambers"]["house"]["projected_seats"] = {"Democratic": 217, "Republican": 217}
    gcs_helpers.save_chamber_forecasts(invalid_totals_payload, draft=True)
    publish_resp = client.post("/api/races/chamber_forecasts/publish", headers={"X-Admin-Key": "secret"})
    assert publish_resp.status_code == 400
    assert "house projected seats must sum to 435" in publish_resp.json()["detail"]

    gcs_helpers.save_chamber_forecasts(payload, draft=True)

    # Publish draft so it becomes public
    publish_resp = client.post("/api/races/chamber_forecasts/publish", headers={"X-Admin-Key": "secret"})
    assert publish_resp.status_code == 200

    # GET should now return 200 and the saved data
    resp = client.get("/races/chamber_forecasts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["house"] == "House is Tilt R"
    assert data["senate"] == "Senate is Lean D"
    assert data["governors"] == "Governors is Safe R"
    assert "updated_at" in data

    manual_save_resp = client.post(
        "/api/races/chamber_forecasts",
        headers={"X-Admin-Key": "secret"},
        json={"house_narrative": "Manual bypass"},
    )
    assert manual_save_resp.status_code == 405


def test_generate_chamber_forecasts_defaults_to_gemini_35_flash(client, monkeypatch):
    """POST /api/races/chamber_forecasts/generate uses the requested default model."""
    seen_models = []

    async def fake_generate_chamber_analysis(chamber_name, context_text, *, model):
        seen_models.append(model)
        return {
            "narrative": f"{chamber_name} narrative",
            "bottom_line": f"{chamber_name} bottom line",
            "why_party_favored": f"{chamber_name} why favored",
            "opposing_party_path": f"{chamber_name} opposing path",
            "key_uncertainty": f"{chamber_name} uncertainty",
        }

    import chamber_narratives

    monkeypatch.setattr(chamber_narratives, "generate_chamber_analysis", fake_generate_chamber_analysis)

    resp = client.post("/api/races/chamber_forecasts/generate", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "google/gemini-3.5-flash"
    assert seen_models == ["google/gemini-3.5-flash"] * 3


def test_generate_chamber_forecasts_fails_without_saving_when_llm_fails(client, monkeypatch):
    """LLM failures should return an explicit error and not save deterministic fallback data."""

    async def failing_generate_chamber_analysis(chamber_name, context_text, *, model):
        raise RuntimeError("provider unavailable")

    import chamber_narratives

    monkeypatch.setattr(chamber_narratives, "generate_chamber_analysis", failing_generate_chamber_analysis)

    resp = client.post("/api/races/chamber_forecasts/generate", json={"model": "test/model"})

    assert resp.status_code == 502
    assert "LLM chamber forecast generation failed" in resp.json()["detail"]

    draft_resp = client.get("/api/races/chamber_forecasts/draft")
    assert draft_resp.status_code == 404
