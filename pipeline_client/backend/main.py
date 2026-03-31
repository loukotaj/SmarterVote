import asyncio
import json
import logging
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List

_RACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")


def _validate_race_id(race_id: str) -> None:
    """Raise 400 if race_id contains path-traversal characters or is malformed."""
    if not _RACE_ID_RE.match(race_id):
        raise HTTPException(status_code=400, detail="Invalid race_id format")

from dotenv import load_dotenv

# Load .env from project root so agent can read API keys via os.environ
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

import httpx
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel

from .logging_manager import logging_manager
from .models import RunInfo, RunOptions, RunRequest, RunResponse
from .pipeline_runner import run_step_async
from .queue_manager import queue_manager
from .run_manager import run_manager
from .settings import settings
from .step_registry import REGISTRY
from .storage import list_artifacts, load_artifact

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(ROOT))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    loop = asyncio.get_running_loop()
    logging_manager.set_main_loop(loop)
    # Resume queue processing if there are pending items from before restart
    if queue_manager.get_next_pending():
        asyncio.create_task(queue_manager.process_next())
    yield


app = FastAPI(title=settings.app_name, description="SmarterVote Pipeline API", lifespan=lifespan)

http_bearer = HTTPBearer(auto_error=False)


async def _decode_token(token: str) -> Dict[str, Any]:
    jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        jwks = (await client.get(jwks_url)).json()
    unverified = jwt.get_unverified_header(token)
    rsa_key = next((k for k in jwks["keys"] if k.get("kid") == unverified.get("kid")), None)
    if not rsa_key:
        raise HTTPException(status_code=401, detail="Invalid token")
    return jwt.decode(
        token,
        rsa_key,
        algorithms=[unverified.get("alg", "RS256")],
        audience=settings.auth0_audience,
        issuer=f"https://{settings.auth0_domain}/",
    )


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> Dict[str, Any]:
    if not settings.auth0_domain or not settings.auth0_audience:
        return {}
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return await _decode_token(credentials.credentials)
    except (JWTError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication") from exc


async def verify_token_ws(token: str | None) -> Dict[str, Any]:
    if not settings.auth0_domain or not settings.auth0_audience:
        return {}
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return await _decode_token(token)
    except (JWTError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication") from exc


# ---------------------------------------------------------------------------
# Agent endpoint
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """Request body for the agent endpoint."""

    race_id: str
    options: RunOptions | None = None


class QueueAddRequest(BaseModel):
    """Request body for adding races to the queue."""

    race_ids: List[str]
    options: RunOptions | None = None


@app.get("/races", dependencies=[Depends(verify_token)])
async def list_published_races() -> Dict[str, Any]:
    """List all published race summaries from GCS (cloud) or data/published/ (local)."""
    races = []
    gcs_bucket = settings.gcs_bucket
    # In Cloud Run, GCS is the source of truth — local filesystem is ephemeral
    if gcs_bucket and (os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_SERVICE") or os.getenv("GOOGLE_CLOUD_PROJECT")):
        try:
            from google.cloud import storage as gcs  # type: ignore

            client = gcs.Client()
            bucket = client.bucket(gcs_bucket)
            for blob in bucket.list_blobs(prefix="races/"):
                if not blob.name.endswith(".json"):
                    continue
                try:
                    data = json.loads(blob.download_as_text())
                    races.append(
                        {
                            "id": data.get("id", blob.name[len("races/") : -len(".json")]),
                            "title": data.get("title"),
                            "office": data.get("office"),
                            "jurisdiction": data.get("jurisdiction"),
                            "election_date": data.get("election_date", ""),
                            "updated_utc": data.get("updated_utc", ""),
                            "candidates": [{"name": c.get("name", ""), "party": c.get("party")} for c in data.get("candidates", [])],
                        }
                    )
                except Exception:
                    logging.exception("Failed to read race blob %s from GCS", blob.name)
            return {"races": sorted(races, key=lambda r: r.get("id", ""))}
        except ImportError:
            logging.warning("google-cloud-storage not installed; falling back to local filesystem")
        except Exception:
            logging.exception("Failed to list races from GCS; falling back to local filesystem")

    # Local filesystem (development or GCS fallback)
    published_dir = ROOT / "data" / "published"
    if published_dir.exists():
        for path in sorted(published_dir.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                races.append(
                    {
                        "id": data.get("id", path.stem),
                        "title": data.get("title"),
                        "office": data.get("office"),
                        "jurisdiction": data.get("jurisdiction"),
                        "election_date": data.get("election_date", ""),
                        "updated_utc": data.get("updated_utc", ""),
                        "candidates": [{"name": c.get("name", ""), "party": c.get("party")} for c in data.get("candidates", [])],
                    }
                )
            except Exception:
                logging.exception("Failed to read race file %s", path)
    return {"races": races}


@app.get("/races/{race_id}", dependencies=[Depends(verify_token)])
async def get_published_race(race_id: str) -> Dict[str, Any]:
    """Get full published race data for export/download."""
    _validate_race_id(race_id)
    published_dir = ROOT / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    # Fall back to GCS when local file is absent (always the case on Cloud Run)
    gcs_bucket = settings.gcs_bucket
    if gcs_bucket:
        try:
            from google.cloud import storage as gcs  # type: ignore

            client = gcs.Client()
            blob = client.bucket(gcs_bucket).blob(f"races/{race_id}.json")
            if blob.exists():
                return json.loads(blob.download_as_text())
        except ImportError:
            logging.warning("google-cloud-storage not installed; cannot read from GCS")
        except Exception:
            logging.exception("Failed to fetch race %s from GCS", race_id)

    raise HTTPException(status_code=404, detail="Race not found")


@app.delete("/races/{race_id}", dependencies=[Depends(verify_token)])
async def delete_published_race(race_id: str) -> Dict[str, Any]:
    """Delete a published race file locally and/or from GCS."""
    _validate_race_id(race_id)
    deleted = False

    # Delete local file if present
    published_dir = ROOT / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        path.unlink()
        deleted = True

    # Delete from GCS if configured
    gcs_bucket = settings.gcs_bucket
    if gcs_bucket:
        try:
            from google.cloud import storage as gcs  # type: ignore

            client = gcs.Client()
            blob = client.bucket(gcs_bucket).blob(f"races/{race_id}.json")
            if blob.exists():
                blob.delete()
                deleted = True
                logging.info("Deleted %s from GCS: gs://%s/races/%s.json", race_id, gcs_bucket, race_id)
        except ImportError:
            logging.warning("google-cloud-storage not installed; skipping GCS delete")
        except Exception as e:
            logging.warning("Failed to delete %s from GCS: %s", race_id, e)

    if not deleted:
        raise HTTPException(status_code=404, detail="Race not found")

    return {"message": f"Race {race_id} deleted", "id": race_id}


@app.post("/api/run", dependencies=[Depends(verify_token)])
async def run_agent_endpoint(request: AgentRequest) -> Dict[str, Any]:
    """Run the agent pipeline for a race.

    The agent uses a multi-phase AI agent with web search to research
    candidates and produce a complete RaceJSON profile. If a published
    profile already exists for this race, the agent will update it.
    """
    run_request = RunRequest(
        payload={"race_id": request.race_id},
        options=request.options,
    )
    run_info = run_manager.create_run(["agent"], run_request)

    # Start execution in background
    asyncio.create_task(_execute_run_async("agent", run_request, run_info.run_id))

    return {"run_id": run_info.run_id, "status": "started", "step": "agent"}


# ---------------------------------------------------------------------------
# Queue endpoints
# ---------------------------------------------------------------------------


@app.get("/queue", dependencies=[Depends(verify_token)])
async def get_queue() -> Dict[str, Any]:
    """Get all queue items with their status."""
    items = queue_manager.get_all()
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "running": queue_manager.has_running(),
        "pending": queue_manager.pending_count(),
    }


@app.post("/queue", dependencies=[Depends(verify_token)])
async def add_to_queue(request: QueueAddRequest) -> Dict[str, Any]:
    """Add one or more races to the processing queue."""
    added = []
    errors = []
    options = request.options.model_dump(exclude_unset=True) if request.options else {}

    for race_id in request.race_ids:
        race_id = race_id.strip()
        if not race_id:
            continue
        try:
            item = queue_manager.add(race_id, options)
            added.append(item.model_dump(mode="json"))
        except ValueError as e:
            errors.append({"race_id": race_id, "error": str(e)})

    # Start processing if not already running
    asyncio.create_task(queue_manager.process_next())

    return {"added": added, "errors": errors}


@app.delete("/queue/finished", dependencies=[Depends(verify_token)])
async def clear_finished_queue() -> Dict[str, Any]:
    """Remove completed/failed/cancelled items from the queue."""
    removed = queue_manager.clear_finished()
    return {"removed": removed}


@app.delete("/queue/{item_id}", dependencies=[Depends(verify_token)])
async def remove_queue_item(item_id: str) -> Dict[str, Any]:
    """Remove or cancel a queue item."""
    if queue_manager.remove(item_id):
        return {"ok": True, "action": "removed"}
    if queue_manager.cancel(item_id):
        return {"ok": True, "action": "cancelled"}
    raise HTTPException(status_code=404, detail="Queue item not found or cannot be removed")


# ---------------------------------------------------------------------------
# Run & artifact inspection endpoints
# ---------------------------------------------------------------------------


@app.get("/run/{run_id}", dependencies=[Depends(verify_token)])
async def get_run_details(run_id: str) -> Dict[str, Any]:
    """Get full details of a specific run."""
    run_info = run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_info.model_dump(mode="json")


@app.get("/artifact/{artifact_id}", dependencies=[Depends(verify_token)])
async def get_artifact_details(artifact_id: str) -> Dict[str, Any]:
    """Get full details of a specific artifact."""
    try:
        return load_artifact(artifact_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="artifact not found")


_cors_origins = settings.allowed_origins_list
# credentials=True is incompatible with wildcard origin — use explicit list or drop credentials
_use_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _use_credentials else ["*"],
    allow_origin_regex=r"https://(.*\.)?smarter\.vote" if not _use_credentials else None,
    allow_credentials=_use_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files for frontend
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "name": settings.app_name}


@app.get("/steps", dependencies=[Depends(verify_token)])
async def steps() -> Dict[str, Any]:
    return {"steps": list(REGISTRY.keys())}


@app.post("/run/{step}", response_model=RunResponse, dependencies=[Depends(verify_token)])
async def run(step: str, request: RunRequest) -> RunResponse:
    if step not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown step '{step}'")
    return await run_step_async(step, request)


async def _execute_run_async(step: str, request: RunRequest, run_id: str):
    """Execute a single run asynchronously."""
    try:
        await run_step_async(step, request, run_id)
    except Exception:
        logging.exception("Unexpected error during async run %s", run_id)


@app.get("/runs", dependencies=[Depends(verify_token)])
async def list_runs(limit: int = 50) -> Dict[str, Any]:
    """List recent runs."""
    runs = run_manager.list_recent_runs(limit)
    return {
        "runs": [run.model_dump(mode="json") for run in runs],
        "active_count": len(run_manager.list_active_runs()),
        "total_count": len(runs),
    }


@app.get("/runs/active", dependencies=[Depends(verify_token)])
async def list_active_runs() -> Dict[str, Any]:
    """List currently active runs."""
    runs = run_manager.list_active_runs()
    return {"runs": [run.model_dump(mode="json") for run in runs], "count": len(runs)}


@app.get("/runs/{run_id}", dependencies=[Depends(verify_token)])
async def get_run(run_id: str) -> RunInfo:
    """Get details of a specific run."""
    run_info = run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_info


@app.delete("/runs/{run_id}", dependencies=[Depends(verify_token)])
async def cancel_run(run_id: str) -> Dict[str, Any]:
    """Cancel a running process."""
    run_info = run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")

    if run_info.status not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="Run is not active")

    run_manager.cancel_run(run_id)
    await logging_manager.send_run_status(run_id, "cancelled")

    return {"message": "Run cancelled", "run_id": run_id}


@app.get("/artifacts", dependencies=[Depends(verify_token)])
async def artifacts() -> Dict[str, Any]:
    return list_artifacts()


@app.get("/artifacts/{artifact_id}", dependencies=[Depends(verify_token)])
async def artifact(artifact_id: str) -> Dict[str, Any]:
    try:
        return load_artifact(artifact_id)
    except FileNotFoundError:  # pragma: no cover
        raise HTTPException(status_code=404, detail="artifact not found")


# ---------------------------------------------------------------------------
# WebSocket endpoints for live logging
# ---------------------------------------------------------------------------


@app.websocket("/ws/logs")
async def websocket_logs_all(websocket: WebSocket):
    """WebSocket endpoint for all logs."""
    token = websocket.query_params.get("token")
    try:
        await verify_token_ws(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    connection_id = str(uuid.uuid4())

    try:
        await logging_manager.connect_websocket(websocket, connection_id)

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text('{"type": "ping"}')

    except WebSocketDisconnect:
        pass
    finally:
        logging_manager.disconnect_websocket(connection_id)


@app.websocket("/ws/logs/{run_id}")
async def websocket_logs_run(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for logs of a specific run."""
    token = websocket.query_params.get("token")
    try:
        await verify_token_ws(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    connection_id = str(uuid.uuid4())

    try:
        await logging_manager.connect_websocket(websocket, connection_id, run_id)

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text('{"type": "ping"}')

    except WebSocketDisconnect:
        pass
    finally:
        logging_manager.disconnect_websocket(connection_id)


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the basic dashboard."""
    basic_frontend = Path(__file__).parent.parent / "frontend" / "index.html"
    if basic_frontend.exists():
        with open(basic_frontend, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)

    return HTMLResponse(
        content="""
        <h1>SmarterVote Pipeline API</h1>
        <p>Dashboard: <a href="http://localhost:5173/admin/pipeline">/admin/pipeline</a></p>
        <p><a href="/docs">API docs</a></p>
    """,
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Alerts endpoints
# ---------------------------------------------------------------------------

from .alerts import acknowledge_alert, evaluate_all  # noqa: E402


@app.get("/alerts", dependencies=[Depends(verify_token)])
async def get_alerts() -> Dict[str, Any]:
    """Evaluate all domain-aware alert rules and return the result list."""
    # Optionally pass analytics overview for API-health alerts
    overview = None
    races_api_url = os.getenv("RACES_API_URL", "http://localhost:8080")
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if races_api_url and admin_key:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{races_api_url}/analytics/overview", headers={"X-Admin-Key": admin_key})
                if resp.status_code == 200:
                    overview = resp.json()
        except Exception:
            pass  # Analytics unavailable — skip health alert

    alerts = evaluate_all(run_manager, overview=overview)
    unacknowledged = sum(1 for a in alerts if not a.acknowledged)
    return {
        "alerts": [a.to_dict() for a in alerts],
        "total": len(alerts),
        "unacknowledged": unacknowledged,
    }


@app.post("/alerts/{alert_id}/acknowledge", dependencies=[Depends(verify_token)])
async def ack_alert(alert_id: str) -> Dict[str, Any]:
    """Acknowledge an alert by ID."""
    acknowledge_alert(alert_id)
    return {"ok": True, "alert_id": alert_id}


# ---------------------------------------------------------------------------
# Analytics proxy (keeps ADMIN_API_KEY server-side)
# ---------------------------------------------------------------------------


@app.get("/analytics/overview", dependencies=[Depends(verify_token)])
async def proxy_analytics_overview(hours: int = 24) -> Dict[str, Any]:
    """Proxy GET /analytics/overview from the races-api."""
    return await _proxy_analytics("/analytics/overview", params={"hours": hours})


@app.get("/analytics/races", dependencies=[Depends(verify_token)])
async def proxy_analytics_races(hours: int = 24) -> Dict[str, Any]:
    """Proxy GET /analytics/races from the races-api."""
    return await _proxy_analytics("/analytics/races", params={"hours": hours})


@app.get("/analytics/timeseries", dependencies=[Depends(verify_token)])
async def proxy_analytics_timeseries(hours: int = 24, bucket: int = 60) -> Dict[str, Any]:
    """Proxy GET /analytics/timeseries from the races-api."""
    return await _proxy_analytics("/analytics/timeseries", params={"hours": hours, "bucket": bucket})


async def _proxy_analytics(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    races_api_url = os.getenv("RACES_API_URL", "http://localhost:8080")
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not admin_key:
        # No key configured — local dev, call directly without auth
        pass
    url = races_api_url.rstrip("/") + path
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers={"X-Admin-Key": admin_key})
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail="Analytics unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Analytics service unreachable") from exc
