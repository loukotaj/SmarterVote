"""Tests for the races API service."""

import json
import os
import sys
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    """Create a TestClient with temporary data directory."""
    # Set the environment variable BEFORE importing the app
    os.environ["DATA_DIR"] = str(tmp_path)
    
    # Clear any cached imports to ensure environment variable takes effect
    if 'main' in sys.modules:
        del sys.modules['main']
    
    # Create sample race file in the temporary directory
    race_data = {
        "id": "race1", 
        "title": "Test Race 1",
        "office": "Office",
        "jurisdiction": "Jurisdiction", 
        "election_date": "2024-11-05T00:00:00",
        "updated_utc": "2023-01-02T00:00:00",
        "candidates": [],
        "generator": ["gpt-4o"]
    }
    (tmp_path / "race1.json").write_text(json.dumps(race_data))

    # Import the app AFTER setting the environment variable and clearing cache
    import main
    return TestClient(main.app)


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
