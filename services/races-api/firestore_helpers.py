"""Firestore helpers for the races-api admin backend."""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import HTTPException

from shared.config import FIRESTORE_RACES_COLLECTION
from shared.race_catalog import build_race_summary_fields, build_versioned_catalog_fields

_FIRESTORE_PROJECT = os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID")

# Module-level singleton — tests reset this to None to force re-creation.
_fs_db = None


def _get_fs() -> Any:
    """Return a lazily-initialised Firestore client, or raise 503 if unavailable."""
    global _fs_db
    if _fs_db is not None:
        return _fs_db
    try:
        from google.cloud import firestore  # type: ignore

        _fs_db = firestore.Client(project=_FIRESTORE_PROJECT) if _FIRESTORE_PROJECT else firestore.Client()
        return _fs_db
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Firestore unavailable: {exc}") from exc


def _ts_to_str(v: Any) -> Any:
    """Convert Firestore/datetime timestamps to ISO strings."""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _strip_quality_score(value: Any) -> Any:
    """Remove legacy race-level quality_score fields from Firestore payloads."""
    if isinstance(value, dict):
        return {k: _strip_quality_score(v) for k, v in value.items() if k != "quality_score"}
    if isinstance(value, list):
        return [_strip_quality_score(v) for v in value]
    return value


def _doc_to_plain(doc: Any) -> Optional[Dict[str, Any]]:
    """Convert a Firestore DocumentSnapshot to a JSON-serialisable dict, or None."""
    if not doc.exists:
        return None
    raw = doc.to_dict() or {}
    plain = {k: _ts_to_str(v) for k, v in raw.items()}
    return _strip_quality_score(plain)


def _fs_update_race(race_id: str, fields: Dict[str, Any]) -> None:
    """Merge fields into the races/{race_id} Firestore document (best-effort)."""
    try:
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore

        fields = _strip_quality_score(dict(fields))
        fields.setdefault("updated_at", SERVER_TIMESTAMP)
        if fields.get("race_id") is None:
            fields["race_id"] = race_id
        _get_fs().collection(FIRESTORE_RACES_COLLECTION).document(race_id).set(fields, merge=True)
    except Exception as exc:
        logging.warning("Firestore race update %s failed: %s", race_id, exc)


def _fs_build_draft_catalog_fields(race_id: str, race_data: Dict[str, Any]) -> Dict[str, Any]:
    fields = build_race_summary_fields(race_id, race_data)
    fields.update(build_versioned_catalog_fields("draft", race_data))
    fields["draft_updated_at"] = race_data.get("updated_utc")
    return fields


def _fs_build_published_catalog_fields(race_id: str, race_data: Dict[str, Any]) -> Dict[str, Any]:
    fields = build_race_summary_fields(race_id, race_data)
    fields.update(build_versioned_catalog_fields("published", race_data))
    fields["published_at"] = race_data.get("updated_utc")
    return fields
