"""
FastAPI service for accessing published race data.

This service exposes endpoints for listing available races and retrieving
individual race data stored as JSON files.
"""

import os
import sys
from typing import List

# Add parent directories to path to import shared modules
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config import DATA_DIR
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from schemas import CandidateSummary, RaceSummary
from simple_publish_service import SimplePublishService

from shared.models import RaceJSON as Race

# Initialize simple publish service
publish_service = SimplePublishService(data_directory=DATA_DIR)

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


@app.get("/races/summaries", response_model=List[RaceSummary])
def get_race_summaries() -> List[RaceSummary]:
    """Get summaries of all races for search and listing."""
    race_ids = publish_service.get_published_races()
    summaries = []

    for race_id in race_ids:
        race_data = publish_service.get_race_data(race_id)
        if race_data:
            # Extract candidate summaries
            candidate_summaries = [
                CandidateSummary(
                    name=candidate["name"], party=candidate.get("party"), incumbent=candidate.get("incumbent", False)
                )
                for candidate in race_data.get("candidates", [])
            ]

            # Create race summary
            summary = RaceSummary(
                id=race_data.get("id", race_id),
                title=race_data.get("title"),
                office=race_data.get("office"),
                jurisdiction=race_data.get("jurisdiction"),
                election_date=race_data.get("election_date", ""),
                updated_utc=race_data.get("updated_utc", ""),
                candidates=candidate_summaries,
            )
            summaries.append(summary)

    return summaries


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
