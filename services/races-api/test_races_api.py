"""Tests for the races API service.

Covers:
- Health/root endpoints
- List races
- Get race summaries
- Get individual race by ID
- 404 for missing races
"""

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from typing import Any
from unittest.mock import MagicMock

import httpx
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


def test_prerender_origin_cannot_bypass_rate_limit(client):
    """A caller-controlled Origin header must not disable rate limiting."""
    import main as main_mod

    main_mod.limiter.reset()

    for _ in range(60):
        resp = client.get("/races", headers={"Origin": "http://sveltekit-prerender"})
        assert resp.status_code == 200

    resp = client.get("/races", headers={"Origin": "http://sveltekit-prerender"})
    assert resp.status_code == 429


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
        payload = resp.json()
        assert "races" in payload
        assert payload["hours"] == 24
        if payload["races"]:
            assert "requests" in payload["races"][0]
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


def test_generate_chamber_forecasts_defaults_to_catalog_model(client, monkeypatch):
    """POST /api/races/chamber_forecasts/generate uses the catalogued default model.

    Assert against the catalog constant rather than a model ID. This endpoint
    deliberately tracks ``PREMIUM_REVIEW_GEMINI``, so pinning a version here just
    fails whenever that role is legitimately upgraded -- and the old name said
    3.5 while the assertion said 3.6, so the pin had already drifted from itself.
    """
    seen_models = []
    seen_cycle_years = []

    async def fake_generate_chamber_analysis(chamber_name, context_text, *, model, cycle_year=None):
        seen_models.append(model)
        seen_cycle_years.append(cycle_year)
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
    from shared.model_catalog import DEFAULT_CHAMBER_FORECAST_MODEL

    assert body["model"] == DEFAULT_CHAMBER_FORECAST_MODEL
    assert seen_models == [DEFAULT_CHAMBER_FORECAST_MODEL] * 3
    # The cycle must reach the prompt from the race data, not a hardcoded literal.
    # These fixtures are mo-senate-2024, so a "2026" here would mean the prompt is
    # still naming a cycle of its own choosing.
    assert seen_cycle_years == ["2024"] * 3


def test_generate_chamber_forecasts_fails_without_saving_when_llm_fails(client, monkeypatch):
    """LLM failures should return an explicit error and not save deterministic fallback data."""

    async def failing_generate_chamber_analysis(chamber_name, context_text, *, model, cycle_year=None):
        raise RuntimeError("provider unavailable")

    import chamber_narratives

    monkeypatch.setattr(chamber_narratives, "generate_chamber_analysis", failing_generate_chamber_analysis)

    resp = client.post("/api/races/chamber_forecasts/generate", json={"model": "test/model"})

    assert resp.status_code == 502
    assert "LLM chamber forecast generation failed" in resp.json()["detail"]

    draft_resp = client.get("/api/races/chamber_forecasts/draft")
    assert draft_resp.status_code == 404


def _stub_analysis(chamber_name):
    return {
        "narrative": f"{chamber_name} narrative",
        "bottom_line": f"{chamber_name} bottom line",
        "why_party_favored": f"{chamber_name} why favored",
        "opposing_party_path": f"{chamber_name} opposing path",
        "key_uncertainty": f"{chamber_name} uncertainty",
    }


def test_generate_chamber_forecasts_skips_review_by_default(client, monkeypatch):
    """The review pass costs an extra call per chamber, so it stays opt-in."""
    reviewed = []

    async def fake_generate(chamber_name, context_text, *, model, cycle_year=None):
        return _stub_analysis(chamber_name)

    async def fake_review(chamber_name, context_text, analysis, *, model, goal=None):
        reviewed.append(chamber_name)
        return analysis, []

    import chamber_narratives

    monkeypatch.setattr(chamber_narratives, "generate_chamber_analysis", fake_generate)
    monkeypatch.setattr(chamber_narratives, "review_chamber_analysis", fake_review)

    resp = client.post("/api/races/chamber_forecasts/generate", json={})

    assert resp.status_code == 200
    assert reviewed == []
    assert resp.json()["reviewed"] is False


def test_generate_chamber_forecasts_review_applies_corrections_and_forwards_goal(client, monkeypatch):
    """review=true rewrites the draft and reports what it actually corrected."""
    seen_goals = []

    async def fake_generate(chamber_name, context_text, *, model, cycle_year=None):
        return _stub_analysis(chamber_name)

    async def fake_review(chamber_name, context_text, analysis, *, model, goal=None):
        seen_goals.append(goal)
        corrected = {**analysis, "narrative": f"{chamber_name} corrected narrative"}
        return corrected, [f"{chamber_name}: called a Republican-held seat a Democratic defense"]

    import chamber_narratives

    monkeypatch.setattr(chamber_narratives, "generate_chamber_analysis", fake_generate)
    monkeypatch.setattr(chamber_narratives, "review_chamber_analysis", fake_review)

    resp = client.post(
        "/api/races/chamber_forecasts/generate",
        json={"review": True, "goal": "lead with the tipping-point races"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reviewed"] is True
    assert seen_goals == ["lead with the tipping-point races"] * 3
    assert body["forecast"]["senate"] == "US Senate corrected narrative"
    assert "Republican-held seat" in body["review_corrections"]["senate"][0]
    # Operator-facing only: the published payload must not carry it.
    assert "review_corrections" not in body["forecast"]["chambers"]["senate"]


@pytest.mark.asyncio
async def test_review_chamber_analysis_returns_the_draft_when_the_pass_fails(monkeypatch):
    """A review that cannot run is not a reason to lose a usable narrative."""
    import chamber_narratives

    async def failing_call(messages, *, model):
        raise ValueError("provider unavailable")

    monkeypatch.setattr(chamber_narratives, "_call_openrouter", failing_call)

    draft = _stub_analysis("US Senate")
    result, corrections = await chamber_narratives.review_chamber_analysis("US Senate", "context", draft, model="test/model")

    assert result == draft
    assert corrections == []


def test_singleflight_coalesces_concurrent_summaries_fetches(tmp_path):
    service = SimplePublishService.__new__(SimplePublishService)
    service.data_directory = tmp_path
    service.gcs_bucket_name = "test-bucket"
    service.cloud_configured = True
    service.cache_ttl = 300
    service._race_list_cache = None
    service._race_data_cache = {}
    service._race_summaries_cache = None

    fetch_count = 0
    fetch_lock = threading.Lock()

    def mock_load_cloud_index(client):
        nonlocal fetch_count
        with fetch_lock:
            fetch_count += 1
        time.sleep(0.05)
        return [{"id": "ga-senate-2026", "title": "Georgia Senate"}]

    service._load_cloud_summaries_index = mock_load_cloud_index
    service.gcs_client = MagicMock()

    results = []

    def worker(call_type):
        if call_type == "races":
            results.append(service.get_published_races())
        else:
            results.append(service.get_race_summaries())

    threads = [threading.Thread(target=worker, args=("races" if i % 2 == 0 else "summaries",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fetch_count == 1
    assert len(results) == 10
    for res in results:
        if isinstance(res[0], str):
            assert res == ["ga-senate-2026"]
        else:
            assert res[0]["id"] == "ga-senate-2026"


def test_singleflight_discards_stale_data_if_cleared_during_fetch(tmp_path):
    service = SimplePublishService.__new__(SimplePublishService)
    service.data_directory = tmp_path
    service.gcs_bucket_name = "test-bucket"
    service.cloud_configured = True
    service.cache_ttl = 300
    service._race_list_cache = None
    service._race_data_cache = {}
    service._race_summaries_cache = None

    def mock_fetch():
        service.clear_cache()
        return [{"id": "stale-race"}]

    service._fetch_summaries_unlocked = mock_fetch

    res = service.get_race_summaries()
    assert res == [{"id": "stale-race"}]
    # Because clear_cache incremented generation during fetch, cache must NOT be populated
    assert service._race_summaries_cache is None


def test_singleflight_wakes_waiters_on_exception(tmp_path):
    service = SimplePublishService.__new__(SimplePublishService)
    service.data_directory = tmp_path
    service.gcs_bucket_name = "test-bucket"
    service.cloud_configured = True
    service.cache_ttl = 300
    service._race_list_cache = None
    service._race_data_cache = {}
    service._race_summaries_cache = None

    def mock_failing_fetch():
        time.sleep(0.02)
        raise RuntimeError("GCS network failure")

    service._fetch_summaries_unlocked = mock_failing_fetch

    waiter_failed = False

    def leader_worker():
        try:
            service.get_race_summaries()
        except RuntimeError:
            pass

    def follower_worker():
        nonlocal waiter_failed
        try:
            time.sleep(0.005)
            service.get_race_summaries()
        except RuntimeError:
            waiter_failed = True

    t1 = threading.Thread(target=leader_worker)
    t2 = threading.Thread(target=follower_worker)
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert waiter_failed is True


def test_singleflight_cache_ttl_zero_coalesces_without_retaining(tmp_path):
    service = SimplePublishService.__new__(SimplePublishService)
    service.data_directory = tmp_path
    service.gcs_bucket_name = "test-bucket"
    service.cloud_configured = True
    service.cache_ttl = 0
    service._race_list_cache = None
    service._race_data_cache = {}
    service._race_summaries_cache = None

    fetch_count = 0

    def mock_fetch():
        nonlocal fetch_count
        fetch_count += 1
        time.sleep(0.03)
        return [{"id": "race-1"}]

    service._fetch_summaries_unlocked = mock_fetch

    threads = [threading.Thread(target=service.get_race_summaries) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fetch_count == 1
    # cache_ttl=0 means results are not stored long-term
    assert service._race_summaries_cache is None


def test_openrouter_error_payload_reports_the_provider_message():
    """A rate limit arrives as HTTP 200 with an error object, not choices.

    Indexing straight into the response turned that into a bare
    KeyError: 'choices', which reached the caller as "chamber forecast
    generation failed: 'choices'" and named no cause.
    """
    import chamber_narratives

    payload = {"error": {"message": "Rate limit exceeded: free-models-per-day", "code": 429}}

    with pytest.raises(ValueError) as excinfo:
        chamber_narratives._extract_choice_content(payload)

    assert "Rate limit exceeded" in str(excinfo.value)


def test_openrouter_empty_choices_is_reported_clearly():
    import chamber_narratives

    with pytest.raises(ValueError) as excinfo:
        chamber_narratives._extract_choice_content({"choices": []})

    assert "no choices" in str(excinfo.value)


def test_openrouter_content_is_returned_when_present():
    import chamber_narratives

    payload = {"choices": [{"message": {"content": "  hello  "}}]}

    assert chamber_narratives._extract_choice_content(payload) == "hello"


def test_call_openrouter_retries_a_rate_limit_then_succeeds(monkeypatch):
    """429 clears on its own within seconds; losing a chamber forecast to it is needless."""
    import chamber_narratives

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    calls = {"n": 0}
    success = {"choices": [{"message": {"content": "{}"}}]}

    class _Resp:
        def __init__(self, status):
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("boom", request=None, response=self)

        def json(self):
            return success

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            calls["n"] += 1
            return _Resp(429 if calls["n"] == 1 else 200)

    monkeypatch.setattr(chamber_narratives.httpx, "AsyncClient", lambda **kw: _Client())

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(chamber_narratives.asyncio, "sleep", _no_sleep)

    result = asyncio.run(chamber_narratives._call_openrouter([{"role": "user", "content": "x"}], model="m"))

    assert result is success
    assert calls["n"] == 2


def test_call_openrouter_does_not_retry_a_client_error(monkeypatch):
    """A bad request will not fix itself, so retrying it only wastes time."""
    import chamber_narratives

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls = {"n": 0}

    class _Resp:
        status_code = 400

        def raise_for_status(self):
            raise httpx.HTTPStatusError("bad request", request=None, response=self)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr(chamber_narratives.httpx, "AsyncClient", lambda **kw: _Client())

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(chamber_narratives._call_openrouter([{"role": "user", "content": "x"}], model="m"))

    assert calls["n"] == 1
