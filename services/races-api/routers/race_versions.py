"""Archived race-version read and restore endpoints."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import firestore_helpers
import gcs_helpers
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException
from request_models import validate_race_id

router = APIRouter()
logger = logging.getLogger("races_api")


def _validate_version_filename(filename: str) -> None:
    if "/" in filename or "\\" in filename or not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid version filename")


def _version_bucket() -> Any:
    if not gcs_helpers._GCS_BUCKET:
        raise HTTPException(status_code=503, detail="GCS not configured")
    client = gcs_helpers._get_gcs_admin()
    if client is None:
        raise HTTPException(status_code=503, detail="GCS unavailable")
    return client.bucket(gcs_helpers._GCS_BUCKET)


@router.get("/api/races/{race_id}/versions", dependencies=[Depends(verify_token)])
async def list_race_versions(race_id: str) -> Dict[str, Any]:
    """List retired versions for a race, newest first."""
    validate_race_id(race_id)
    versions = gcs_helpers._gcs_list_versions(race_id)
    versions.sort(key=lambda version: version.get("archived_at") or "", reverse=True)
    return {"versions": versions, "count": len(versions)}


@router.get("/api/races/{race_id}/versions/{filename}", dependencies=[Depends(verify_token)])
async def get_race_version(race_id: str, filename: str) -> Dict[str, Any]:
    """Return one retired version without exposing provider errors to clients."""
    validate_race_id(race_id)
    _validate_version_filename(filename)
    try:
        blob = _version_bucket().blob(f"retired/{race_id}/{filename}")
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Version not found")
        return json.loads(blob.download_as_text())
    except HTTPException:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Invalid archived race JSON for %s/%s: %s", race_id, filename, type(exc).__name__)
        raise HTTPException(status_code=422, detail="Archived version contains invalid JSON") from exc
    except Exception as exc:  # Provider libraries expose multiple transport exception types.
        logger.exception("Unable to read archived race version %s/%s", race_id, filename)
        raise HTTPException(status_code=502, detail="Unable to read archived version") from exc


@router.post("/api/races/{race_id}/versions/{filename}/restore", dependencies=[Depends(verify_token)])
async def restore_version_as_draft(race_id: str, filename: str) -> Dict[str, Any]:
    """Restore one retired version as the active draft."""
    validate_race_id(race_id)
    _validate_version_filename(filename)
    try:
        source = _version_bucket().blob(f"retired/{race_id}/{filename}")
        if not source.exists():
            raise HTTPException(status_code=404, detail="Retired version not found")
        version_data = json.loads(source.download_as_text())
    except HTTPException:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Invalid archived race JSON for %s/%s: %s", race_id, filename, type(exc).__name__)
        raise HTTPException(status_code=422, detail="Archived version contains invalid JSON") from exc
    except Exception as exc:  # Provider libraries expose multiple transport exception types.
        logger.exception("Unable to restore archived race version %s/%s", race_id, filename)
        raise HTTPException(status_code=502, detail="Unable to read archived version") from exc

    gcs_helpers._gcs_archive_race(race_id, "drafts", "draft")
    gcs_helpers._gcs_put_race_json(race_id, "drafts", version_data)
    firestore_helpers._fs_update_race(
        race_id,
        {
            "status": "draft",
            "published_at": None,
            "draft_updated_at": datetime.now(timezone.utc).isoformat(),
            **firestore_helpers._fs_build_draft_catalog_fields(race_id, version_data),
        },
    )
    return {
        "message": f"Retired version restored as draft for {race_id}",
        "id": race_id,
        "restored_from": filename,
    }
