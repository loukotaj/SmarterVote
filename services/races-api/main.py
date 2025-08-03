"""
FastAPI service for accessing published race data.

This service exposes endpoints for listing available races and retrieving
individual race data stored as JSON files.
"""

import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pipeline.app.publish import PublishService
from pipeline.app.schema import Race

# Configure data directory from environment variable
DATA_DIR = os.getenv("DATA_DIR", "data/published/")

# Initialize publish service with custom data directory
publish_service = PublishService()
publish_service.output_dir = Path(DATA_DIR)
publish_service.output_dir.mkdir(parents=True, exist_ok=True)

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
    return publish_service.get_published_races()


@app.get("/races/{race_id}", response_model=Race)
def get_race(race_id: str) -> Race:
    """Retrieve race data by ID."""
    race_data = publish_service.get_race_data(race_id)
    if not race_data:
        raise HTTPException(status_code=404, detail="Race not found")
    return Race(**race_data)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
