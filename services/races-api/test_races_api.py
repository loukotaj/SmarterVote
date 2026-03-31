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

import pytest
from fastapi.testclient import TestClient

# Add project root for shared imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    monkeypatch.setenv("DATA_DIR", data_dir)
    # Re-import to pick up patched env
    import importlib

    import config as cfg_mod

    importlib.reload(cfg_mod)

    import main as main_mod

    # Reinitialize the publish service with the new data dir
    main_mod.publish_service = main_mod.SimplePublishService(data_directory=data_dir)
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


def test_list_races_empty():
    """GET /races returns empty list when no data directory exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import importlib

        import config as cfg_mod
        import main as main_mod

        os.environ["DATA_DIR"] = tmpdir
        importlib.reload(cfg_mod)
        main_mod.publish_service = main_mod.SimplePublishService(data_directory=tmpdir)
        test_client = TestClient(main_mod.app)
        resp = test_client.get("/races")
        assert resp.status_code == 200
        assert resp.json() == []


def test_rate_limit_exceeded(client):
    """Exceeding the rate limit returns 429 Too Many Requests."""
    import main as main_mod

    main_mod.limiter.reset()

    for _ in range(60):
        resp = client.get("/races")
        assert resp.status_code == 200

    resp = client.get("/races")
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


def test_analytics_no_key_configured(client):
    """When no key is configured, unauthenticated access is permitted (dev mode)."""
    import main as main_mod

    original = main_mod._ADMIN_API_KEY
    main_mod._ADMIN_API_KEY = ""
    try:
        resp = client.get("/analytics/overview")
        assert resp.status_code == 200
    finally:
        main_mod._ADMIN_API_KEY = original
