"""
FastAPI service for accessing published race data.

This service exposes endpoints for listing available races and retrieving
individual race data stored as JSON files.
"""

import logging
import os
import sys
from typing import List

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

# Add parent directories to path to import shared modules
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config import DATA_DIR
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from schemas import CandidateSummary, RaceSummary
from simple_publish_service import SimplePublishService
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from shared.models import RaceJSON as Race

# Initialize simple publish service
publish_service = SimplePublishService(data_directory=DATA_DIR)

# Rate limiter (keyed by client IP)
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI app
app = FastAPI(title="SmarterVote Races API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enable CORS — public read-only API; credentials not needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/races", response_model=List[str])
@limiter.limit("60/minute")
def list_races(request: Request) -> List[str]:
    """List available race IDs."""
    return publish_service.get_published_races()


@app.get("/races/summaries", response_model=List[RaceSummary])
@limiter.limit("30/minute")
def get_race_summaries(request: Request) -> List[RaceSummary]:
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


@app.get("/races/{race_id}")
@limiter.limit("60/minute")
def get_race(request: Request, race_id: str):
    """Retrieve race data by ID."""
    race_data = publish_service.get_race_data(race_id)
    if not race_data:
        raise HTTPException(status_code=404, detail="Race not found")
    return race_data


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
