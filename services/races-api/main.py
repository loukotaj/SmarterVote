"""
FastAPI service for accessing published race data.

This service exposes public read endpoints for race data, analytics, and
admin management endpoints for the SmarterVote pipeline.

Admin endpoints are split into routers:
    routers/queue.py        - queue management
    routers/runs.py         - run details and logs
    routers/races_admin.py  - race record CRUD, drafts, publish, versions
    routers/pipeline.py     - metrics, admin chat
"""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load local environment variables from root .env
if "pytest" not in sys.modules:
    for p in Path(__file__).resolve().parents:
        env_path = p / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            break

import schemas
from analytics_middleware import AnalyticsMiddleware
from analytics_store import AnalyticsStore
from auth import verify_token
from cloudflare_analytics import CloudflareAnalytics
from config import DATA_DIR
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from rate_limit import limiter
from routers import admin_agent as admin_agent_router_module
from routers import payments as payments_router_module
from routers import pipeline as pipeline_router_module
from routers import queue as queue_router_module
from routers import races_admin as races_admin_router_module
from routers import runs as runs_router_module
from simple_publish_service import SimplePublishService
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Initialize simple publish service
publish_service = SimplePublishService(data_directory=DATA_DIR)


_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
_http_bearer = HTTPBearer(auto_error=False)


def _require_admin_key(x_admin_key: str = Header(default="")) -> None:
    """Dependency: reject requests missing a valid X-Admin-Key header."""
    if not _ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin API key not configured")
    if not secrets.compare_digest(x_admin_key, _ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key")


async def _require_admin_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(_http_bearer),
    x_admin_key: str = Header(default=""),
) -> None:
    """Dependency: authorize with bearer token OR legacy X-Admin-Key."""
    if _ADMIN_API_KEY:
        if x_admin_key:
            if secrets.compare_digest(x_admin_key, _ADMIN_API_KEY):
                return
            # Keep legacy semantics for key-auth callers when bearer token is absent.
            if credentials is None:
                raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key")
        elif credentials is None:
            raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key")

    # Fall back to Auth0 bearer auth used by the admin frontend.
    await verify_token(credentials)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.analytics = AnalyticsStore()
    app.state.cloudflare_analytics = CloudflareAnalytics()
    yield


# Initialize FastAPI app
app = FastAPI(title="SmarterVote Races API", lifespan=lifespan)
app.state.limiter = limiter
app.state.publish_service = publish_service
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Analytics middleware - runs before CORS, records every tracked request
app.add_middleware(AnalyticsMiddleware)

# Enable CORS - public read API + authenticated admin writes
origins = [
    "https://smarter.vote",
    "https://www.smarter.vote",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://sveltekit-prerender",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.pages\.dev|https://.*\.workers\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Admin routers
# ---------------------------------------------------------------------------
app.include_router(queue_router_module.router)
app.include_router(runs_router_module.router)
app.include_router(races_admin_router_module.router)
app.include_router(pipeline_router_module.router)
app.include_router(admin_agent_router_module.router)

# ---------------------------------------------------------------------------
# Payment routers (public checkout + webhook)
# ---------------------------------------------------------------------------
app.include_router(payments_router_module.router)


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


@app.get("/health", include_in_schema=False)
def health():
    """Liveness probe - always returns OK if the process is up."""
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def readiness():
    """Readiness probe - checks that the publish service can serve data."""
    races = publish_service.get_published_races()
    return {"ready": True, "race_count": len(races)}


@app.get("/races", response_model=List[str], dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def list_races(request: Request, response: Response) -> List[str]:
    """List available race IDs."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return publish_service.get_published_races()


@app.get("/races/summaries", response_model=List[schemas.RaceSummary], dependencies=[Depends(verify_token)])
@limiter.limit("30/minute")
def get_race_summaries(request: Request, response: Response) -> List[schemas.RaceSummary]:
    """Get summaries of all races for search and listing."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return publish_service.get_race_summaries()


@app.get("/races/chamber_forecasts", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def get_chamber_forecasts(request: Request, response: Response):
    """Retrieve overall chamber-level forecasts (narratives) from GCS or local file."""
    data = publish_service.get_chamber_forecasts_data()
    if not data:
        raise HTTPException(status_code=404, detail="Chamber forecasts not found")
    response.headers["Cache-Control"] = "public, max-age=300"
    return data


@app.get("/races/{race_id}", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def get_race(request: Request, response: Response, race_id: str):
    """Retrieve race data by ID."""
    from request_models import validate_race_id

    validate_race_id(race_id)
    race_data = publish_service.get_race_data(race_id)
    if not race_data:
        raise HTTPException(status_code=404, detail="Race not found")
    response.headers["Cache-Control"] = "public, max-age=300"
    return race_data


# ---------------------------------------------------------------------------
# Analytics endpoints (admin-key protected)
# ---------------------------------------------------------------------------


@app.post("/cache/clear")
@limiter.limit("10/minute")
async def clear_cache(request: Request, _auth: None = Depends(_require_admin_access)):
    """Clear the in-memory GCS response cache so the next request re-fetches fresh data.

    Call this after pushing new race data to GCS so the API reflects the update
    without waiting for the TTL to expire.
    """
    publish_service.clear_cache()
    return {"message": "Cache cleared", "cache_ttl_seconds": publish_service.cache_ttl}


@app.get("/analytics/overview")
@limiter.limit("20/minute")
async def analytics_overview(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    _auth: None = Depends(_require_admin_access),
):
    """Summary stats: total requests, unique visitors, avg latency, error rate, timeseries."""
    return await request.app.state.analytics.get_overview(hours=hours)


@app.get("/analytics/traffic")
@limiter.limit("20/minute")
async def analytics_traffic(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    _auth: None = Depends(_require_admin_access),
):
    """Static-site page views, visits, and dimensions from Cloudflare Web Analytics."""
    return await request.app.state.cloudflare_analytics.get_summary(hours=hours)


@app.get("/analytics/races")
@limiter.limit("20/minute")
async def analytics_races(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    _auth: None = Depends(_require_admin_access),
):
    """Per-race request counts for the last *hours* hours."""
    stats = await request.app.state.analytics.get_race_stats(hours=hours)
    # Batch-load summaries once to avoid N+1 per-race lookups
    summaries = publish_service.get_race_summaries()
    summary_by_id = {s["id"]: s for s in summaries}
    for item in stats:
        summary = summary_by_id.get(item["race_id"])
        item["updated_utc"] = summary.get("updated_utc") if summary else None
        item["title"] = summary.get("title") if summary else None
    return {"races": stats, "hours": hours}


@app.get("/analytics/timeseries")
@limiter.limit("20/minute")
async def analytics_timeseries(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    bucket: int = Query(default=60, ge=5, le=360),
    _auth: None = Depends(_require_admin_access),
):
    """Bucketed request counts for charting. *bucket* is the bucket size in minutes."""
    return {
        "timeseries": await request.app.state.analytics.get_timeseries(hours=hours, bucket_minutes=bucket),
        "hours": hours,
        "bucket_minutes": bucket,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
