"""
FastAPI service for accessing published race data.

This service exposes endpoints for listing available races and retrieving
individual race data stored as JSON files.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import List

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

# Add parent directories to path to import shared modules
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from analytics_middleware import AnalyticsMiddleware
from analytics_store import AnalyticsStore
from config import DATA_DIR
from fastapi import FastAPI, Header, HTTPException, Request
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

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _require_admin_key(x_admin_key: str = Header(default="")) -> None:
    """Dependency: reject requests missing a valid X-Admin-Key header."""
    if _ADMIN_API_KEY and x_admin_key != _ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.analytics = AnalyticsStore()
    yield


# Initialize FastAPI app
app = FastAPI(title="SmarterVote Races API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Analytics middleware — runs before CORS, records every tracked request
app.add_middleware(AnalyticsMiddleware)

# Enable CORS — public read-only API; credentials not needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*", "X-Admin-Key"],
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


# ---------------------------------------------------------------------------
# Analytics endpoints (admin-key protected)
# ---------------------------------------------------------------------------


@app.get("/analytics/overview")
async def analytics_overview(request: Request, hours: int = 24, x_admin_key: str = Header(default="")):
    """Summary stats: total requests, unique visitors, avg latency, error rate, timeseries."""
    _require_admin_key(x_admin_key)
    return await request.app.state.analytics.get_overview(hours=hours)


@app.get("/analytics/races")
async def analytics_races(request: Request, hours: int = 24, x_admin_key: str = Header(default="")):
    """Per-race request counts for the last *hours* hours."""
    _require_admin_key(x_admin_key)
    stats = await request.app.state.analytics.get_race_stats(hours=hours)
    # Enrich with freshness metadata from the publish service
    enriched = []
    for item in stats:
        race_data = publish_service.get_race_data(item["race_id"])
        item["updated_utc"] = race_data.get("updated_utc") if race_data else None
        item["title"] = race_data.get("title") if race_data else None
        enriched.append(item)
    return {"races": enriched, "hours": hours}


@app.get("/analytics/timeseries")
async def analytics_timeseries(
    request: Request,
    hours: int = 24,
    bucket: int = 60,
    x_admin_key: str = Header(default=""),
):
    """Bucketed request counts for charting. *bucket* is the bucket size in minutes."""
    _require_admin_key(x_admin_key)
    return {
        "timeseries": await request.app.state.analytics.get_timeseries(hours=hours, bucket_minutes=bucket),
        "hours": hours,
        "bucket_minutes": bucket,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
