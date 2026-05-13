"""Local FastAPI entrypoint for running and inspecting the pipeline agent.

Production/admin race, draft, queue, analytics, and chat endpoints live in
services/races-api. This app intentionally exposes only local runner endpoints.
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from .logging_manager import logging_manager
from .models import RunInfo, RunOptions, RunRequest, RunResponse
from .pipeline_runner import run_step_async
from .run_manager import run_manager
from .settings import settings
from .step_registry import REGISTRY

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

_RACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
_gcs_client = None
http_bearer = HTTPBearer(auto_error=False)


def _validate_race_id(race_id: str) -> None:
    """Raise 400 if race_id contains path-traversal characters or is malformed."""
    if not _RACE_ID_RE.match(race_id):
        raise HTTPException(status_code=400, detail="Invalid race_id format")


def _get_gcs_client():
    """Return a lazily initialized GCS client, or None if the library is missing."""
    global _gcs_client
    if _gcs_client is not None:
        return _gcs_client
    try:
        from google.cloud import storage as gcs  # type: ignore

        _gcs_client = gcs.Client()
        return _gcs_client
    except ImportError:
        logging.warning("google-cloud-storage not installed")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure loop-bound logging helpers for local background runs."""
    logging_manager.set_main_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title=settings.app_name, description="SmarterVote local pipeline runner", lifespan=lifespan)

_cors_origins = settings.allowed_origins_list
_use_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _use_credentials else ["*"],
    allow_origin_regex=r"https://(.*\.)?smarter\.vote" if not _use_credentials else None,
    allow_credentials=_use_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _decode_token(token: str) -> Dict[str, Any]:
    jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        jwks = resp.json()
    unverified = jwt.get_unverified_header(token)
    rsa_key = next((k for k in jwks["keys"] if k.get("kid") == unverified.get("kid")), None)
    if not rsa_key:
        raise HTTPException(status_code=401, detail="Invalid token")
    return jwt.decode(
        token,
        rsa_key,
        algorithms=["RS256"],
        audience=settings.auth0_audience,
        issuer=f"https://{settings.auth0_domain}/",
    )


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> Dict[str, Any]:
    if settings.skip_auth:
        return {}
    if not settings.auth0_domain or not settings.auth0_audience:
        raise HTTPException(
            status_code=503,
            detail="Authentication not configured. Set SKIP_AUTH=true for local dev.",
        )
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return await _decode_token(credentials.credentials)
    except (JWTError, httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication") from exc


class AgentRequest(BaseModel):
    """Request body for running the full agent locally."""

    race_id: str
    options: RunOptions | None = None


async def _execute_run_async(step: str, request: RunRequest, run_id: str) -> None:
    try:
        await run_step_async(step, request, run_id)
    except Exception:
        logging.exception("Unexpected error during async run %s", run_id)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "name": settings.app_name, "mode": "local-runner"}


@app.get("/steps", dependencies=[Depends(verify_token)])
async def steps() -> Dict[str, Any]:
    return {"steps": list(REGISTRY.keys())}


@app.post("/run/{step}", response_model=RunResponse, dependencies=[Depends(verify_token)])
async def run(step: str, request: RunRequest) -> RunResponse:
    """Run one registered pipeline step and return its response."""
    if step not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown step '{step}'")
    return await run_step_async(step, request)


@app.post("/api/run", dependencies=[Depends(verify_token)])
async def run_agent_endpoint(request: AgentRequest) -> Dict[str, Any]:
    """Start a local full-agent run in the background."""
    _validate_race_id(request.race_id)
    run_request = RunRequest(payload={"race_id": request.race_id}, options=request.options)
    run_info = run_manager.create_run(["agent"], run_request)
    asyncio.create_task(_execute_run_async("agent", run_request, run_info.run_id))
    return {"run_id": run_info.run_id, "status": "started", "step": "agent"}


@app.get("/runs", dependencies=[Depends(verify_token)])
async def list_runs(limit: int = 50) -> Dict[str, Any]:
    runs = run_manager.list_recent_runs(limit)
    return {
        "runs": [run.model_dump(mode="json") for run in runs],
        "active_count": len(run_manager.list_active_runs()),
        "total_count": len(runs),
    }


@app.get("/runs/active", dependencies=[Depends(verify_token)])
async def list_active_runs() -> Dict[str, Any]:
    runs = run_manager.list_active_runs()
    return {"runs": [run.model_dump(mode="json") for run in runs], "count": len(runs)}


@app.get("/runs/{run_id}", dependencies=[Depends(verify_token)])
async def get_run(run_id: str) -> RunInfo:
    run_info = run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_info


@app.get("/runs/{run_id}/logs", dependencies=[Depends(verify_token)])
async def get_run_logs(run_id: str, since: int = 0) -> Dict[str, Any]:
    logs = run_manager.get_run_logs(run_id)
    sliced = logs[since:] if since < len(logs) else []
    return {"logs": sliced, "total": len(logs)}


@app.delete("/runs/{run_id}", dependencies=[Depends(verify_token)])
async def cancel_or_delete_run(run_id: str) -> Dict[str, Any]:
    run_info = run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")
    if run_info.status in ["pending", "running"]:
        run_manager.cancel_run(run_id)
        await logging_manager.send_run_status(run_id, "cancelled")
    run_manager.delete_run(run_id)
    return {"message": "Run deleted", "run_id": run_id}
