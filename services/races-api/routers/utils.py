"""Shared utility functions for FastAPI routers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.pipeline_config import RetentionConfig

_RETENTION = RetentionConfig.from_env()


def _now() -> str:
    """Return the current time in UTC ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """Return a new UUID."""
    return str(uuid.uuid4())


def _queue_ttl_at() -> datetime:
    """Return the queue item TTL datetime."""
    return datetime.now(timezone.utc) + timedelta(days=_RETENTION.completed_queue_days)


def _coerce_datetime(value: Any) -> datetime | None:
    """Parse Firestore timestamps and ISO strings into aware datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None
