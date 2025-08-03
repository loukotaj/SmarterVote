"""Tests for the races API service."""

import json
import os
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    """Create a TestClient with temporary data directory."""
    # Create sample race file
    race_data = {
        "id": "race1",
        "title": "Test Race 1",
        "office": "Office",
        "jurisdiction": "Jurisdiction",
        "election_date": "2024-11-05T00:00:00",
        "candidates": [],
        "description": "Test race",
        "key_issues": [],
        "status": "completed",
        "sources": [],
        "created_at": "2023-01-01T00:00:00",
        "last_updated": "2023-01-02T00:00:00",
        "confidence": "unknown"
    }
    (tmp_path / "race1.json").write_text(json.dumps(race_data))

    os.environ["DATA_DIR"] = str(tmp_path)

    # Dynamically import the app after setting DATA_DIR
    main_path = Path(__file__).resolve().parents[3] / "services" / "races-api" / "main.py"
    sys.path.append(str(main_path.parents[2]))
    spec = importlib.util.spec_from_file_location("races_api", main_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore

    return TestClient(module.app)


def test_list_races(client):
    response = client.get("/races")
    assert response.status_code == 200
    assert response.json() == ["race1"]


def test_get_race(client):
    response = client.get("/races/race1")
    assert response.status_code == 200
    assert response.json()["id"] == "race1"


def test_get_race_not_found(client):
    response = client.get("/races/unknown")
    assert response.status_code == 404
