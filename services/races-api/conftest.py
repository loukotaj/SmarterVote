"""Pytest configuration for races-api tests."""

import json
import os
import sys
from pathlib import Path
import importlib.util

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    """Create a TestClient with temporary data directory."""
    # Set the environment variable BEFORE importing the app
    os.environ["DATA_DIR"] = str(tmp_path)

    # Clear any cached imports to ensure environment variable takes effect
    modules_to_clear = [
        mod
        for mod in sys.modules.keys()
        if mod == "main" or mod.endswith(".main") or "races_main" in mod
    ]
    for mod in modules_to_clear:
        del sys.modules[mod]

    # Create sample race file in the temporary directory
    race_data = {
        "id": "race1",
        "title": "Test Race 1",
        "office": "Office",
        "jurisdiction": "Jurisdiction",
        "election_date": "2024-11-05T00:00:00",
        "updated_utc": "2023-01-02T00:00:00",
        "candidates": [],
        "generator": ["gpt-4o"],
    }
    (tmp_path / "race1.json").write_text(json.dumps(race_data))

    # Import the app using absolute file import to avoid conflicts
    current_dir = Path(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))

    main_path = current_dir / "main.py"
    spec = importlib.util.spec_from_file_location("races_api_main", main_path)
    main_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_module)

    return TestClient(main_module.app)
