import asyncio
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List

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
    import asyncio

    loop = asyncio.get_running_loop()
    logging_manager.set_main_loop(loop)
    yield


app = FastAPI(title=settings.app_name, description="SmarterVote Pipeline V2 API", lifespan=lifespan)

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
# V2 Agent endpoint
# ---------------------------------------------------------------------------


class V2AgentRequest(BaseModel):
    """Request body for the v2 agent endpoint."""

    race_id: str
    options: RunOptions | None = None


@app.post("/api/v2/run", dependencies=[Depends(verify_token)])
async def run_v2_agent(request: V2AgentRequest) -> Dict[str, Any]:
    """Run the v2 agent pipeline for a race.

    The v2 agent uses a multi-phase AI agent with web search to research
    candidates and produce a complete RaceJSON profile. If a published
    profile already exists for this race, the agent will update it.
    """
    run_request = RunRequest(
        payload={"race_id": request.race_id},
        options=request.options,
    )
    run_info = run_manager.create_run(["v2_agent"], run_request)

    # Start execution in background
    asyncio.create_task(_execute_run_async("v2_agent", run_request, run_info.run_id))

    return {"run_id": run_info.run_id, "status": "started", "step": "v2_agent"}


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


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
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
        <h1>SmarterVote Pipeline V2 API</h1>
        <p>Dashboard: <a href="http://localhost:5173/admin/pipeline">/admin/pipeline</a></p>
        <p><a href="/docs">API docs</a></p>
    """,
        status_code=200,
    )
