"""One place to build a Google Cloud Storage client.

Six modules used to construct their own, and one of them lived in
``backend/main.py`` — the local debug API that CLAUDE.md documents as "not
production". ``race_manager``, the central production race-state service,
imported ``_get_gcs_client`` from it. Because that import is lazy (inside the
function, per this project's circular-dependency convention) it does not fail at
startup: it fails the first time a run actually needs GCS, part-way through, in
whichever deployment did not expect to be importing a FastAPI debug app.

Importing this module has no side effects and pulls in no web framework.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("pipeline")

_client: Optional[Any] = None
_lock = threading.Lock()


def get_gcs_client() -> Optional[Any]:
    """Return a lazily built, process-wide GCS client, or None if unavailable.

    Returns None rather than raising when the library is missing or credentials
    cannot be resolved: callers run in local mode without GCS, and every call
    site already branches on a falsy client. The reason is logged once.
    """
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:  # another thread won the race
            return _client
        try:
            from google.cloud import storage  # type: ignore

            _client = storage.Client()
        except ImportError:
            logger.warning("google-cloud-storage is not installed; GCS features are unavailable")
            return None
        except Exception as exc:  # credentials missing, metadata server unreachable
            logger.warning("GCS client init failed: %s", exc)
            return None
    return _client


def reset_gcs_client() -> None:
    """Drop the memoized client. For tests; harmless in production."""
    global _client
    with _lock:
        _client = None
