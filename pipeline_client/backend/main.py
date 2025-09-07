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
from .models import BatchRunRequest, BatchRunResponse, ContinueRunRequest, RunInfo, RunOptions, RunRequest, RunResponse
from .pipeline_runner import run_step_async
from .run_manager import run_manager
from .settings import settings
from .step_orchestrator import continue_run as continue_pipeline
from .step_registry import REGISTRY
from .storage import list_artifacts, load_artifact

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(ROOT))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    import asyncio

    loop = asyncio.get_running_loop()
    logging_manager.set_main_loop(loop)
    yield
    # Shutdown


app = FastAPI(title=settings.app_name, description="Enhanced Pipeline Client with Live Logging", lifespan=lifespan)

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


# Request model for running the full Step 01 sequence
class Step01Request(BaseModel):
    race_id: str
    options: RunOptions | None = None


async def _run_step01_sequence(race_id: str, options: RunOptions | None = None) -> Dict[str, Any]:
    """Run metadata through ingest using the step orchestrator."""
    run_req = RunRequest(payload={"race_id": race_id}, options=options)
    first = await run_step_async("step01a_metadata", run_req)
    if not first.ok:
        raise RuntimeError(first.error or "metadata step failed")
    cont = await continue_pipeline(first.meta["run_id"], steps=["all"])
    cont["runs"].insert(
        0,
        {
            "step": "step01a_metadata",
            "run_id": first.meta["run_id"],
            "artifact_id": first.artifact_id,
        },
    )
    cont["run_id"] = first.meta["run_id"]
    return cont


# Endpoint to run the full Step 01 sequence
@app.post("/run/step01", dependencies=[Depends(verify_token)])
async def run_step01(request: Step01Request) -> Dict[str, Any]:
    try:
        return await _run_step01_sequence(request.race_id, request.options)
    except RuntimeError as exc:  # pragma: no cover - surface pipeline error
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# New endpoints for frontend modal details
@app.get("/run/{run_id}", dependencies=[Depends(verify_token)])
async def get_run_details(run_id: str) -> Dict[str, Any]:
    """Get full details of a specific run as dict (for modal view)."""
    run_info = run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")
    # Return as dict for frontend
    return run_info.model_dump(mode="json")


@app.get("/artifact/{artifact_id}", dependencies=[Depends(verify_token)])
async def get_artifact_details(artifact_id: str) -> Dict[str, Any]:
    """Get full details of a specific artifact as dict (for modal view)."""
    try:
        artifact = load_artifact(artifact_id)
        return artifact
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


# Enhanced API endpoint for frontend
@app.post("/api/execute", dependencies=[Depends(verify_token)])
async def api_execute(request: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced execute endpoint for the frontend dashboard"""
    step = request.get("step")
    payload = request.get("payload", {})
    options = request.get("options", {})

    if not step:
        raise HTTPException(status_code=400, detail="Missing 'step' parameter")

    if step not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown step '{step}'")

    # Create run request
    run_request = RunRequest(payload=payload, options=options)
    run_info = run_manager.create_run([step], run_request)

    # Start execution in background
    asyncio.create_task(_execute_run_async(step, run_request, run_info.run_id))

    return {"run_id": run_info.run_id, "status": "started", "step": step}


@app.post("/api/continue", dependencies=[Depends(verify_token)])
async def api_continue(request: ContinueRunRequest) -> Dict[str, Any]:
    """Enhanced continue endpoint for the frontend dashboard."""

    try:
        return await continue_pipeline(request.run_id, steps=request.steps, state=request.state)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _execute_run_async(step: str, request: RunRequest, run_id: str):
    """Execute a single run asynchronously."""
    try:
        await run_step_async(step, request, run_id)
    except Exception:
        logging.exception("Unexpected error during async run %s", run_id)


@app.post("/batch/{step}", response_model=BatchRunResponse, dependencies=[Depends(verify_token)])
async def batch_run(step: str, request: BatchRunRequest) -> BatchRunResponse:
    """Run a step for multiple race IDs."""
    if step not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown step '{step}'")

    batch_id = str(uuid.uuid4())
    runs = []

    for race_id in request.race_ids:
        run_request = RunRequest(payload={"race_id": race_id}, options=request.options)
        run_info = run_manager.create_run([step], run_request)
        runs.append(run_info)

    # Start batch execution in background
    asyncio.create_task(_execute_batch(step, runs, request.options))

    return BatchRunResponse(batch_id=batch_id, total_runs=len(runs), runs=runs)


async def _execute_batch(step: str, runs: List[RunInfo], options):
    """Execute batch runs in background."""
    for run_info in runs:
        try:
            request = RunRequest(payload=run_info.payload, options=options)
            await run_step_async(step, request, run_info.run_id)
        except Exception:
            logging.exception("Run %s failed during batch execution", run_info.run_id)


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


@app.post("/runs/{run_id}/continue", dependencies=[Depends(verify_token)])
async def continue_run_endpoint(run_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
    """Continue a pipeline run by executing subsequent steps.

    The request body may include:

    - ``steps``: list of steps to execute. ``["all"]`` runs all remaining steps.
      Omitted or empty runs only the next step.
    - ``state``: optional JSON object allowing edits before execution.
    """

    steps = request.get("steps")
    state = request.get("state")

    try:
        return await continue_pipeline(run_id, steps=steps, state=state)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/artifacts", dependencies=[Depends(verify_token)])
async def artifacts() -> Dict[str, Any]:
    return list_artifacts()


@app.get("/artifacts/{artifact_id}", dependencies=[Depends(verify_token)])
async def artifact(artifact_id: str) -> Dict[str, Any]:
    try:
        return load_artifact(artifact_id)
    except FileNotFoundError:  # pragma: no cover
        raise HTTPException(status_code=404, detail="artifact not found")


# WebSocket endpoints for live logging
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

        # Keep connection alive
        while True:
            # Wait for client messages (like ping/pong)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
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

        # Keep connection alive
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text('{"type": "ping"}')

    except WebSocketDisconnect:
        pass
    finally:
        logging_manager.disconnect_websocket(connection_id)


# Root endpoint serves basic frontend
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the basic dashboard (enhanced dashboard is now in the web project)"""
    basic_frontend = Path(__file__).parent.parent / "frontend" / "index.html"
    if basic_frontend.exists():
        with open(basic_frontend, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)

    return HTMLResponse(
        content="""
        <h1>Pipeline Client API</h1>
        <p>Enhanced dashboard is available in the web project at: <a href="http://localhost:5173/admin/pipeline">/admin/pipeline</a></p>
        <p><a href="/docs">View API docs</a></p>
    """,
        status_code=200,
    )


if __name__ == "__main__":  # pragma: no cover - CLI utility
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Run Step 01 pipeline sequence")
    parser.add_argument("race_id", help="Race identifier to process")
    args = parser.parse_args()

    result = asyncio.run(_run_step01_sequence(args.race_id))
    print(json.dumps(result, indent=2))
