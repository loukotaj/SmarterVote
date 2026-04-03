import asyncio
import json
import logging
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
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
from .race_manager import RaceRecord, race_manager
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

    # Hydrate race records from existing files/GCS
    try:
        if settings.is_cloud_run and settings.gcs_bucket:
            race_manager.hydrate_from_gcs()
        else:
            race_manager.hydrate_from_files()
    except Exception:
        logging.exception("Race hydration failed — continuing with empty race list")

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


# ---------------------------------------------------------------------------
# Helpers for reading race data from GCS or local filesystem
# ---------------------------------------------------------------------------


def _race_summary(data: Dict[str, Any], fallback_id: str) -> Dict[str, Any]:
    """Build a race summary dict from full race JSON."""
    am = data.get("agent_metrics") or {}
    return {
        "id": data.get("id", fallback_id),
        "title": data.get("title"),
        "office": data.get("office"),
        "jurisdiction": data.get("jurisdiction"),
        "election_date": data.get("election_date", ""),
        "updated_utc": data.get("updated_utc", ""),
        "candidates": [
            {"name": c.get("name", ""), "party": c.get("party")}
            for c in data.get("candidates", [])
        ],
        "agent_metrics": (
            {
                "estimated_usd": am.get("estimated_usd"),
                "model": am.get("model"),
                "total_tokens": am.get("total_tokens"),
            }
            if am
            else None
        ),
    }


def _list_races_gcs(gcs_prefix: str) -> List[Dict[str, Any]] | None:
    """List race summaries from a GCS prefix. Returns None on failure."""
    gcs_bucket = settings.gcs_bucket
    if not gcs_bucket or not settings.is_cloud_run:
        return None
    try:
        from google.cloud import storage as gcs  # type: ignore

        client = gcs.Client()
        bucket = client.bucket(gcs_bucket)
        races = []
        for blob in bucket.list_blobs(prefix=f"{gcs_prefix}/"):
            if not blob.name.endswith(".json"):
                continue
            try:
                data = json.loads(blob.download_as_text())
                stem = blob.name[len(f"{gcs_prefix}/") : -len(".json")]
                races.append(_race_summary(data, stem))
            except Exception:
                logging.exception("Failed to read blob %s from GCS", blob.name)
        return sorted(races, key=lambda r: r.get("id", ""))
    except ImportError:
        logging.warning("google-cloud-storage not installed; falling back to local filesystem")
    except Exception:
        logging.exception("Failed to list %s from GCS; falling back to local filesystem", gcs_prefix)
    return None


def _list_races_local(local_dir: Path) -> List[Dict[str, Any]]:
    """List race summaries from a local directory."""
    races = []
    if local_dir.exists():
        for path in sorted(local_dir.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                races.append(_race_summary(data, path.stem))
            except Exception:
                logging.exception("Failed to read race file %s", path)
    return races


def _get_race_gcs(race_id: str, gcs_prefix: str) -> Dict[str, Any] | None:
    """Load a single race from GCS. Returns None on miss/error."""
    gcs_bucket = settings.gcs_bucket
    if not gcs_bucket:
        return None
    try:
        from google.cloud import storage as gcs  # type: ignore

        client = gcs.Client()
        blob = client.bucket(gcs_bucket).blob(f"{gcs_prefix}/{race_id}.json")
        if blob.exists():
            return json.loads(blob.download_as_text())
    except ImportError:
        logging.warning("google-cloud-storage not installed; cannot read from GCS")
    except Exception:
        logging.exception("Failed to fetch %s/%s from GCS", gcs_prefix, race_id)
    return None


def _delete_race_gcs(race_id: str, gcs_prefix: str) -> bool:
    """Delete a race from GCS. Returns True if deleted."""
    gcs_bucket = settings.gcs_bucket
    if not gcs_bucket:
        return False
    try:
        from google.cloud import storage as gcs  # type: ignore

        client = gcs.Client()
        blob = client.bucket(gcs_bucket).blob(f"{gcs_prefix}/{race_id}.json")
        if blob.exists():
            blob.delete()
            logging.info("Deleted %s from GCS: gs://%s/%s/%s.json", race_id, gcs_bucket, gcs_prefix, race_id)
            return True
    except ImportError:
        logging.warning("google-cloud-storage not installed; skipping GCS delete")
    except Exception as e:
        logging.warning("Failed to delete %s from GCS %s/: %s", race_id, gcs_prefix, e)
    return False


def _copy_race_gcs(race_id: str, src_prefix: str, dst_prefix: str) -> bool:
    """Copy a race between GCS prefixes. Returns True if copied."""
    gcs_bucket = settings.gcs_bucket
    if not gcs_bucket:
        return False
    try:
        from google.cloud import storage as gcs  # type: ignore

        client = gcs.Client()
        bucket = client.bucket(gcs_bucket)
        src_blob = bucket.blob(f"{src_prefix}/{race_id}.json")
        if not src_blob.exists():
            return False
        bucket.copy_blob(src_blob, bucket, f"{dst_prefix}/{race_id}.json")
        logging.info("Copied %s from %s/ to %s/ in GCS", race_id, src_prefix, dst_prefix)
        return True
    except ImportError:
        logging.warning("google-cloud-storage not installed; skipping GCS copy")
    except Exception as e:
        logging.warning("Failed to copy %s from %s/ to %s/ in GCS: %s", race_id, src_prefix, dst_prefix, e)
    return False


# ---------------------------------------------------------------------------
# Published races endpoints
# ---------------------------------------------------------------------------


@app.get("/races", dependencies=[Depends(verify_token)])
async def list_published_races() -> Dict[str, Any]:
    """List all published race summaries from GCS (cloud) or data/published/ (local)."""
    races = _list_races_gcs("races")
    if races is None:
        races = _list_races_local(ROOT / "data" / "published")
    return {"races": races}


@app.get("/races/{race_id}", dependencies=[Depends(verify_token)])
async def get_published_race(race_id: str) -> Dict[str, Any]:
    """Get full published race data for export/download."""
    _validate_race_id(race_id)
    # Local first (dev), then GCS (cloud)
    published_dir = ROOT / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    data = _get_race_gcs(race_id, "races")
    if data:
        return data
    raise HTTPException(status_code=404, detail="Race not found")


@app.delete("/races/{race_id}", dependencies=[Depends(verify_token)])
async def delete_published_race(race_id: str) -> Dict[str, Any]:
    """Delete a published race file locally and/or from GCS."""
    _validate_race_id(race_id)
    deleted = False
    published_dir = ROOT / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        path.unlink()
        deleted = True
    if _delete_race_gcs(race_id, "races"):
        deleted = True
    if not deleted:
        raise HTTPException(status_code=404, detail="Race not found")
    return {"message": f"Race {race_id} deleted", "id": race_id}


# ---------------------------------------------------------------------------
# Draft races endpoints
# ---------------------------------------------------------------------------


@app.get("/drafts", dependencies=[Depends(verify_token)])
async def list_draft_races() -> Dict[str, Any]:
    """List all draft race summaries from GCS drafts/ or data/drafts/."""
    races = _list_races_gcs("drafts")
    if races is None:
        races = _list_races_local(ROOT / "data" / "drafts")
    return {"races": races}


@app.get("/drafts/{race_id}", dependencies=[Depends(verify_token)])
async def get_draft_race(race_id: str) -> Dict[str, Any]:
    """Get full draft race data."""
    _validate_race_id(race_id)
    drafts_dir = ROOT / "data" / "drafts"
    path = drafts_dir / f"{race_id}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    data = _get_race_gcs(race_id, "drafts")
    if data:
        return data
    raise HTTPException(status_code=404, detail="Draft not found")


@app.post("/drafts/{race_id}/publish", dependencies=[Depends(verify_token)])
async def publish_draft(race_id: str) -> Dict[str, Any]:
    """Promote a draft to published: copy drafts/ -> races/ in GCS + local."""
    _validate_race_id(race_id)

    # Load the draft data
    draft_data = None
    drafts_dir = ROOT / "data" / "drafts"
    draft_path = drafts_dir / f"{race_id}.json"
    if draft_path.exists():
        with draft_path.open("r", encoding="utf-8") as f:
            draft_data = json.load(f)

    if draft_data is None:
        draft_data = _get_race_gcs(race_id, "drafts")

    if draft_data is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Write to published (local)
    published_dir = ROOT / "data" / "published"
    published_dir.mkdir(parents=True, exist_ok=True)
    published_path = published_dir / f"{race_id}.json"
    json_str = json.dumps(draft_data, indent=2, default=str)
    with published_path.open("w", encoding="utf-8") as f:
        f.write(json_str)

    # Copy to published (GCS)
    gcs_bucket = settings.gcs_bucket
    if gcs_bucket:
        try:
            from google.cloud import storage as gcs  # type: ignore
            client = gcs.Client()
            bucket = client.bucket(gcs_bucket)
            blob = bucket.blob(f"races/{race_id}.json")
            blob.upload_from_string(json_str, content_type="application/json")
            logging.info("Published %s to GCS: gs://%s/races/%s.json", race_id, gcs_bucket, race_id)
        except Exception:
            logging.exception("Failed to publish %s to GCS", race_id)

    # Update race record in Firestore
    race_manager.publish_race(race_id)
    race_manager.update_race_metadata(race_id, draft_data)

    return {"message": f"Race {race_id} published", "id": race_id}


@app.post("/races/{race_id}/unpublish", dependencies=[Depends(verify_token)])
async def unpublish_race(race_id: str) -> Dict[str, Any]:
    """Remove a race from published (keeps draft). Deletes races/ entry only."""
    _validate_race_id(race_id)
    deleted = False
    published_dir = ROOT / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        path.unlink()
        deleted = True
    if _delete_race_gcs(race_id, "races"):
        deleted = True
    if not deleted:
        raise HTTPException(status_code=404, detail="Published race not found")

    # Update race record in Firestore
    race_manager.unpublish_race(race_id)

    return {"message": f"Race {race_id} unpublished (draft retained)", "id": race_id}


@app.delete("/drafts/{race_id}", dependencies=[Depends(verify_token)])
async def delete_draft_race(race_id: str) -> Dict[str, Any]:
    """Delete a draft race file."""
    _validate_race_id(race_id)
    deleted = False
    drafts_dir = ROOT / "data" / "drafts"
    path = drafts_dir / f"{race_id}.json"
    if path.exists():
        path.unlink()
        deleted = True
    if _delete_race_gcs(race_id, "drafts"):
        deleted = True
    if not deleted:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"message": f"Draft {race_id} deleted", "id": race_id}


# ---------------------------------------------------------------------------
# Unified Race Management API (Phase 1-4)
# ---------------------------------------------------------------------------


class RaceQueueRequest(BaseModel):
    """Request body for queueing races."""

    race_ids: List[str]
    options: RunOptions | None = None


@app.get("/api/races", dependencies=[Depends(verify_token)])
async def list_all_races() -> Dict[str, Any]:
    """List all race records (unified view: published, draft, queued, running, etc.)."""
    races = race_manager.list_races(500)
    return {"races": [r.model_dump(mode="json") for r in races]}


@app.get("/api/races/{race_id}", dependencies=[Depends(verify_token)])
async def get_race_record(race_id: str) -> Dict[str, Any]:
    """Get a single race record."""
    _validate_race_id(race_id)
    record = race_manager.get_race(race_id)
    if not record:
        raise HTTPException(status_code=404, detail="Race not found")
    return record.model_dump(mode="json")


@app.delete("/api/races/{race_id}", dependencies=[Depends(verify_token)])
async def delete_race_record(race_id: str) -> Dict[str, Any]:
    """Delete a race record and all associated data (published, draft, runs)."""
    _validate_race_id(race_id)

    # Delete published + draft files
    published_dir = ROOT / "data" / "published"
    drafts_dir = ROOT / "data" / "drafts"
    for d in [published_dir, drafts_dir]:
        path = d / f"{race_id}.json"
        if path.exists():
            path.unlink()

    _delete_race_gcs(race_id, "races")
    _delete_race_gcs(race_id, "drafts")

    race_manager.delete_race(race_id)
    return {"message": f"Race {race_id} deleted", "id": race_id}


@app.post("/api/races/queue", dependencies=[Depends(verify_token)])
async def queue_races(request: RaceQueueRequest) -> Dict[str, Any]:
    """Queue races for pipeline processing (unified — replaces POST /queue)."""
    options = request.options.model_dump(exclude_unset=True) if request.options else {}
    added = []
    errors = []

    valid_ids = []
    for race_id in request.race_ids:
        race_id = race_id.strip()
        if not race_id:
            continue
        try:
            _validate_race_id(race_id)
            valid_ids.append(race_id)
        except HTTPException:
            errors.append({"race_id": race_id, "error": "Invalid race_id format"})

    # Update race_manager records
    records = race_manager.queue_races(valid_ids, options)

    # Also add to queue_manager for processing
    for record in records:
        if record.status == "queued":
            try:
                queue_manager.add(record.race_id, options)
                added.append(record.model_dump(mode="json"))
            except ValueError as e:
                errors.append({"race_id": record.race_id, "error": str(e)})
        else:
            added.append(record.model_dump(mode="json"))

    # Start processing
    asyncio.create_task(queue_manager.process_next())

    return {"added": added, "errors": errors}


@app.post("/api/races/{race_id}/cancel", dependencies=[Depends(verify_token)])
async def cancel_race_queue(race_id: str) -> Dict[str, Any]:
    """Cancel a queued or running race."""
    _validate_race_id(race_id)
    race = race_manager.get_race(race_id)
    if not race or race.status not in ("queued", "running"):
        raise HTTPException(status_code=404, detail="Race is not queued or running")

    # Cancel in queue_manager
    for item in queue_manager.get_all():
        if item.race_id == race_id and item.status in ("pending", "running"):
            queue_manager.cancel(item.id)
            break

    record = race_manager.cancel_race(race_id)
    return {"message": f"Race {race_id} cancelled", "race": record.model_dump(mode="json") if record else None}


@app.post("/api/races/{race_id}/recheck", dependencies=[Depends(verify_token)])
async def recheck_race_status(race_id: str) -> Dict[str, Any]:
    """Re-derive race status from actual storage state.

    Use when a race is stuck in 'running' after a process crash or
    serialisation error.  Safe to call at any time — if the run is
    genuinely still active the status is left unchanged.
    """
    _validate_race_id(race_id)
    record = race_manager.recheck_status(race_id)
    return {"message": f"Race {race_id} rechecked", "race": record.model_dump(mode="json")}


@app.post("/api/races/{race_id}/run", dependencies=[Depends(verify_token)])
async def run_race_pipeline(race_id: str, options: RunOptions | None = None) -> Dict[str, Any]:
    """Run the pipeline for a single race (direct, not queued)."""
    _validate_race_id(race_id)

    run_request = RunRequest(
        payload={"race_id": race_id},
        options=options,
    )
    run_info = run_manager.create_run(["agent"], run_request)

    # Update race record
    race_manager.start_run(race_id, run_info.run_id)
    race_manager.save_run(race_id, run_info)

    asyncio.create_task(_execute_run_async("agent", run_request, run_info.run_id))

    return {"run_id": run_info.run_id, "status": "started", "race_id": race_id}


@app.post("/api/races/{race_id}/publish", dependencies=[Depends(verify_token)])
async def publish_race(race_id: str) -> Dict[str, Any]:
    """Publish a race (copy draft -> published). Updates race record."""
    _validate_race_id(race_id)

    # Load draft data
    draft_data = None
    drafts_dir = ROOT / "data" / "drafts"
    draft_path = drafts_dir / f"{race_id}.json"
    if draft_path.exists():
        with draft_path.open("r", encoding="utf-8") as f:
            draft_data = json.load(f)

    if draft_data is None:
        draft_data = _get_race_gcs(race_id, "drafts")

    if draft_data is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Write to published (local)
    published_dir = ROOT / "data" / "published"
    published_dir.mkdir(parents=True, exist_ok=True)
    published_path = published_dir / f"{race_id}.json"
    json_str = json.dumps(draft_data, indent=2, default=str)
    with published_path.open("w", encoding="utf-8") as f:
        f.write(json_str)

    # Copy to published (GCS)
    gcs_bucket = settings.gcs_bucket
    if gcs_bucket:
        try:
            from google.cloud import storage as gcs  # type: ignore

            client = gcs.Client()
            bucket = client.bucket(gcs_bucket)
            blob = bucket.blob(f"races/{race_id}.json")
            blob.upload_from_string(json_str, content_type="application/json")
        except Exception:
            logging.exception("Failed to publish %s to GCS", race_id)

    # Update race record
    race_manager.publish_race(race_id)
    race_manager.update_race_metadata(race_id, draft_data)

    return {"message": f"Race {race_id} published", "id": race_id}


@app.post("/api/races/{race_id}/unpublish", dependencies=[Depends(verify_token)])
async def unpublish_race_api(race_id: str) -> Dict[str, Any]:
    """Unpublish a race (remove from published, keep draft)."""
    _validate_race_id(race_id)
    deleted = False
    published_dir = ROOT / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        path.unlink()
        deleted = True
    if _delete_race_gcs(race_id, "races"):
        deleted = True
    if not deleted:
        raise HTTPException(status_code=404, detail="Published race not found")

    race_manager.unpublish_race(race_id)
    return {"message": f"Race {race_id} unpublished", "id": race_id}


@app.get("/api/races/{race_id}/runs", dependencies=[Depends(verify_token)])
async def list_race_runs(race_id: str, limit: int = 20) -> Dict[str, Any]:
    """List runs for a specific race (from subcollection)."""
    _validate_race_id(race_id)
    runs = race_manager.list_runs(race_id, limit)
    # Also include active runs from run_manager
    active_runs = [
        r for r in run_manager.list_active_runs()
        if r.payload.get("race_id") == race_id
    ]
    active_ids = {r.run_id for r in active_runs}
    combined = active_runs + [r for r in runs if r.run_id not in active_ids]
    combined.sort(key=lambda r: r.started_at or datetime.min, reverse=True)

    return {
        "runs": [r.model_dump(mode="json") for r in combined[:limit]],
        "count": len(combined[:limit]),
    }


@app.get("/api/races/{race_id}/runs/{run_id}", dependencies=[Depends(verify_token)])
async def get_race_run(race_id: str, run_id: str) -> Dict[str, Any]:
    """Get details of a specific run for a race."""
    _validate_race_id(race_id)
    # Check active first
    run_info = run_manager.get_run(run_id)
    if run_info:
        return run_info.model_dump(mode="json")
    # Then subcollection
    run_info = race_manager.get_run(race_id, run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_info.model_dump(mode="json")


@app.delete("/api/races/{race_id}/runs/{run_id}", dependencies=[Depends(verify_token)])
async def delete_race_run(race_id: str, run_id: str) -> Dict[str, Any]:
    """Cancel or delete a run for a race."""
    _validate_race_id(race_id)
    run_info = run_manager.get_run(run_id)
    if run_info and run_info.status in ("pending", "running"):
        run_manager.cancel_run(run_id)
        await logging_manager.send_run_status(run_id, "cancelled")
        return {"message": "Run cancelled", "run_id": run_id}

    if race_manager.delete_run(race_id, run_id):
        return {"message": "Run deleted", "run_id": run_id}

    # Fallback to old run_manager delete
    if run_manager.delete_run(run_id):
        return {"message": "Run deleted", "run_id": run_id}

    raise HTTPException(status_code=404, detail="Run not found")


@app.get("/api/races/{race_id}/data", dependencies=[Depends(verify_token)])
async def get_race_data(race_id: str, draft: bool = False) -> Dict[str, Any]:
    """Get full race JSON content (published or draft). For export/download."""
    _validate_race_id(race_id)

    if draft:
        drafts_dir = ROOT / "data" / "drafts"
        path = drafts_dir / f"{race_id}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        data = _get_race_gcs(race_id, "drafts")
        if data:
            return data
        raise HTTPException(status_code=404, detail="Draft not found")

    published_dir = ROOT / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    data = _get_race_gcs(race_id, "races")
    if data:
        return data
    raise HTTPException(status_code=404, detail="Race data not found")


# ---------------------------------------------------------------------------
# Legacy agent endpoint (kept for backward compatibility, delegates to unified)
# ---------------------------------------------------------------------------


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

    # Update race record
    race_manager.start_run(request.race_id, run_info.run_id)
    race_manager.save_run(request.race_id, run_info)

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
async def cancel_or_delete_run(run_id: str) -> Dict[str, Any]:
    """Cancel an active run or delete a completed/failed/cancelled run from history."""
    run_info = run_manager.get_run(run_id)
    if not run_info:
        raise HTTPException(status_code=404, detail="Run not found")

    if run_info.status in ["pending", "running"]:
        run_manager.cancel_run(run_id)
        await logging_manager.send_run_status(run_id, "cancelled")
        return {"message": "Run cancelled", "run_id": run_id}
    else:
        deleted = run_manager.delete_run(run_id)
        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete run")
        return {"message": "Run deleted", "run_id": run_id}


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


# ---------------------------------------------------------------------------
# Pipeline metrics (token usage & cost per research run)
# ---------------------------------------------------------------------------


@app.get("/pipeline/metrics", dependencies=[Depends(verify_token)])
async def get_pipeline_metrics(limit: int = 50) -> Dict[str, Any]:
    """Return recent pipeline run records with token usage and cost data."""
    from pipeline_client.backend.pipeline_metrics import get_pipeline_metrics_store

    try:
        records = await get_pipeline_metrics_store().get_recent(limit=limit)
        return {"records": records, "count": len(records)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline metrics unavailable: {exc}") from exc


@app.get("/pipeline/metrics/summary", dependencies=[Depends(verify_token)])
async def get_pipeline_metrics_summary() -> Dict[str, Any]:
    """Return aggregate pipeline cost stats (total_runs, total_usd, avg_usd, recent_30d_usd)."""
    from pipeline_client.backend.pipeline_metrics import get_pipeline_metrics_store

    try:
        return await get_pipeline_metrics_store().get_summary()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Pipeline metrics unavailable: {exc}") from exc
