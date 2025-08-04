"""Tests for the races API service."""

import pytest
from fastapi.testclient import TestClient


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
