"""
FastAPI service for accessing published race data.

This service exposes endpoints for listing available races and retrieving
individual race data stored as JSON files.
"""

import importlib.util
import json
import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Load RaceJSON model without importing the full pipeline package
_schema_path = Path(__file__).resolve().parents[2] / "pipeline" / "app" / "schema.py"
_spec = importlib.util.spec_from_file_location("race_schema", _schema_path)
_race_schema = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_race_schema)
RaceJSON = _race_schema.RaceJSON

# Configure data directory from environment variable
DATA_DIR = Path(os.getenv("DATA_DIR", "data/published"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


# Utility helpers
def _list_race_files() -> List[Path]:
    """Return JSON files in the data directory."""
    return sorted(DATA_DIR.glob("*.json"))


def _load_race(race_id: str) -> dict | None:
    """Load a race JSON file by ID."""
    file_path = DATA_DIR / f"{race_id}.json"
    if not file_path.exists():
        return None
    with file_path.open() as f:
        return json.load(f)


# Initialize FastAPI app
app = FastAPI(title="SmarterVote Races API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/races", response_model=List[str])
def list_races() -> List[str]:
    """List available race IDs."""
    return [p.stem for p in _list_race_files()]


@app.get("/races/{race_id}", response_model=RaceJSON)
def get_race(race_id: str) -> RaceJSON:
    """Retrieve race data by ID."""
    race_data = _load_race(race_id)
    if race_data is None:
        raise HTTPException(status_code=404, detail="Race not found")
    return RaceJSON(**race_data)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
