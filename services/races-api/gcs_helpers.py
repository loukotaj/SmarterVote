"""GCS helpers for the races-api admin backend."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Resolved once at startup; can be overridden in tests.
_GCS_BUCKET = os.getenv("GCS_BUCKET", "")

# Module-level singleton — tests can patch _get_gcs_admin to return a mock.
_gcs_admin_client = None


def _get_gcs_admin() -> Any:
    """Return a lazily-initialised GCS client, or None if unavailable."""
    global _gcs_admin_client
    if _gcs_admin_client is not None:
        return _gcs_admin_client
    try:
        from google.cloud import storage as gcs  # type: ignore

        _gcs_admin_client = gcs.Client()
        return _gcs_admin_client
    except ImportError:
        return None


def _gcs_list_race_ids(prefix: str) -> Optional[List[str]]:
    """List race IDs (JSON filename stems) under the given GCS prefix."""
    if not _GCS_BUCKET:
        return None
    client = _get_gcs_admin()
    if client is None:
        return None
    try:
        bucket = client.bucket(_GCS_BUCKET)
        blobs = list(bucket.list_blobs(prefix=f"{prefix}/"))
        return [b.name.split("/")[-1][:-5] for b in blobs if b.name.endswith(".json")]
    except Exception as exc:
        logging.warning("GCS list %s failed: %s", prefix, exc)
        return None


def _gcs_get_race_json(race_id: str, prefix: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse a race JSON blob from GCS."""
    if not _GCS_BUCKET:
        return None
    client = _get_gcs_admin()
    if client is None:
        return None
    try:
        bucket = client.bucket(_GCS_BUCKET)
        blob = bucket.blob(f"{prefix}/{race_id}.json")
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())
    except Exception as exc:
        logging.warning("GCS get %s/%s failed: %s", prefix, race_id, exc)
        return None


def _gcs_put_race_json(race_id: str, prefix: str, data: Dict[str, Any]) -> bool:
    """Upload a race JSON blob to GCS. Returns True on success."""
    if not _GCS_BUCKET:
        return False
    client = _get_gcs_admin()
    if client is None:
        return False
    try:
        bucket = client.bucket(_GCS_BUCKET)
        bucket.blob(f"{prefix}/{race_id}.json").upload_from_string(json.dumps(data, indent=2), content_type="application/json")
        return True
    except Exception as exc:
        logging.warning("GCS put %s/%s failed: %s", prefix, race_id, exc)
        return False


def _gcs_delete_race_json(race_id: str, prefix: str) -> bool:
    """Delete a race JSON blob from GCS. Returns True if it existed."""
    if not _GCS_BUCKET:
        return False
    client = _get_gcs_admin()
    if client is None:
        return False
    try:
        bucket = client.bucket(_GCS_BUCKET)
        blob = bucket.blob(f"{prefix}/{race_id}.json")
        if blob.exists():
            blob.delete()
            return True
        return False
    except Exception as exc:
        logging.warning("GCS delete %s/%s failed: %s", prefix, race_id, exc)
        return False


def _gcs_archive_race(race_id: str, src_prefix: str, source_label: str) -> bool:
    """Copy current blob to retired/{race_id}/<ts>-{source_label}.json."""
    if not _GCS_BUCKET:
        return False
    client = _get_gcs_admin()
    if client is None:
        return False
    try:
        bucket = client.bucket(_GCS_BUCKET)
        src_blob = bucket.blob(f"{src_prefix}/{race_id}.json")
        if not src_blob.exists():
            return False
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bucket.copy_blob(src_blob, bucket, f"retired/{race_id}/{ts}-{source_label}.json")
        return True
    except Exception as exc:
        logging.warning("GCS archive %s/%s failed: %s", src_prefix, race_id, exc)
        return False


def _gcs_list_versions(race_id: str) -> List[Dict[str, Any]]:
    """List retired versions for a race from GCS."""
    if not _GCS_BUCKET:
        return []
    client = _get_gcs_admin()
    if client is None:
        return []
    versions: List[Dict[str, Any]] = []
    try:
        bucket = client.bucket(_GCS_BUCKET)
        for blob in bucket.list_blobs(prefix=f"retired/{race_id}/"):
            fname = blob.name.split("/")[-1]
            if not fname.endswith(".json"):
                continue
            stem = fname[:-5]
            parts = stem.rsplit("-", 1)
            source = parts[-1] if len(parts) == 2 else "unknown"
            ts_raw = parts[0] if len(parts) == 2 else stem
            try:
                ts: Optional[str] = datetime.strptime(ts_raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                ts = None
            versions.append({"filename": fname, "source": source, "archived_at": ts, "size_bytes": blob.size})
    except Exception as exc:
        logging.warning("GCS list versions %s failed: %s", race_id, exc)
    return versions


def _assert_publishable_race(data: Dict[str, Any]) -> None:
    """Block publishing data that the review gate explicitly failed."""
    validation_grade = data.get("validation_grade")
    if not isinstance(validation_grade, dict):
        return
    if validation_grade.get("passed") is False:
        grade = validation_grade.get("grade") or "unknown"
        score = validation_grade.get("score")
        detail = f"Race failed validation ({grade}"
        if score is not None:
            detail += f", {score}/100"
        detail += ") and cannot be published"
        raise ValueError(detail)


def publish_race_to_gcs(race_id: str, data: Dict[str, Any]) -> None:
    """Archive existing blobs, write new published blob, delete draft, update Firestore."""
    import firestore_helpers  # avoid circular at module load

    _assert_publishable_race(data)
    _gcs_archive_race(race_id, "races", "published")
    _gcs_archive_race(race_id, "drafts", "draft")
    if not _gcs_put_race_json(race_id, "races", data):
        raise RuntimeError(f"Failed to write published race blob for {race_id}")

    # Publish is only considered successful if the source draft is gone.
    if not _gcs_delete_race_json(race_id, "drafts") and _gcs_get_race_json(race_id, "drafts") is not None:
        raise RuntimeError(f"Published race {race_id} but failed to remove draft blob")

    firestore_helpers._fs_update_race(
        race_id,
        {
            "status": "published",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "draft_updated_at": None,
            "current_run_id": None,
        },
    )


# Alias used by races_admin router
_publish_race_gcs = publish_race_to_gcs
