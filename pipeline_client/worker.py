"""Long-lived local pipeline worker.

Leases ``runner == "local"`` items from the Firestore ``pipeline_queue`` and runs
them to completion in-process with a far-future deadline (see
``pipeline_client/backend/queue_processor.py``). It runs alongside the default
one-shot Cloud Run Job path; runner-scoped claims keep the two modes from
competing for the same work.

Usage:
    python -m pipeline_client.worker

Env:
    WORKER_CONCURRENCY     max races in flight at once (default 2)
    WORKER_POLL_SECONDS    idle poll interval (default 3)
    GCS_BUCKET             GCS bucket for drafts/checkpoints (else settings)
    FIRESTORE_PROJECT / PROJECT_ID   Firestore project
Requires GCP credentials (GOOGLE_APPLICATION_CREDENTIALS or ADC) with Firestore +
GCS access, plus the LLM/search API keys the agent needs (via .env / env).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any, Set

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# Shared backends use FIRESTORE_PROJECT for mode detection, while workstation
# environments commonly provide only GOOGLE_CLOUD_PROJECT.
if not os.getenv("FIRESTORE_PROJECT"):
    _configured_project = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if _configured_project:
        os.environ["FIRESTORE_PROJECT"] = _configured_project

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("pipeline_worker")

_RUNNER = os.getenv("WORKER_RUNNER", "local").strip().lower()
_CONCURRENCY = max(1, int(os.getenv("WORKER_CONCURRENCY", "2")))
_POLL_SECONDS = max(1, int(os.getenv("WORKER_POLL_SECONDS", "3")))
_ONCE = os.getenv("WORKER_ONCE", "false").strip().lower() in {"1", "true", "yes"}
# How often the long-lived worker proves it's still alive. This has nothing to do
# with race progress — it fires whether or not any race is in flight — so an admin
# can tell "worker process is dead/not restarted" apart from "worker is just idle".
# See infra/monitoring.tf's `pipeline_worker_heartbeat` log-based metric + the
# `local_worker_stale` alert policy, which fire off the log line this writes.
_HEARTBEAT_SECONDS = max(30, int(os.getenv("WORKER_HEARTBEAT_SECONDS", "300")))
_cloud_logger: Any = None
_cloud_logger_init_failed = False


def _get_cloud_logger() -> Any:
    """Lazily create a Cloud Logging client bound to the `pipeline-worker-heartbeat`
    log. Only WORKER_ONCE=false (long-lived) callers need this — the one-shot Cloud
    Run Job path already ships stdout to Cloud Logging automatically and doesn't call
    this. Returns None (and logs a one-time warning) if google-cloud-logging isn't
    installed or ADC lacks roles/logging.logWriter — the heartbeat is best-effort and
    must never crash the worker.
    """
    global _cloud_logger, _cloud_logger_init_failed
    if _cloud_logger is not None or _cloud_logger_init_failed:
        return _cloud_logger
    try:
        from google.cloud import logging as gcloud_logging  # type: ignore

        project = os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID")
        client = gcloud_logging.Client(project=project) if project else gcloud_logging.Client()
        _cloud_logger = client.logger("pipeline-worker-heartbeat")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cloud Logging heartbeat disabled (init failed): %s", exc)
        _cloud_logger_init_failed = True
        _cloud_logger = None
    return _cloud_logger


def _emit_heartbeat() -> None:
    """Write one structured heartbeat entry to Cloud Logging, if available.

    Best-effort: any failure here only logs a local warning and never propagates,
    since a heartbeat outage must not take down race processing.
    """
    cloud_logger = _get_cloud_logger()
    if cloud_logger is None:
        return
    try:
        cloud_logger.log_struct(
            {"event": "pipeline_worker_heartbeat", "runner": _RUNNER, "hostname": os.getenv("HOSTNAME", "local-worker")},
            severity="INFO",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to emit worker heartbeat: %s", exc)


def _get_db() -> Any:
    from pipeline_client.backend.firestore_logger import _get_db as _fl_get_db

    db = _fl_get_db()
    if db is None:
        from google.cloud import firestore  # type: ignore

        project = os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID")
        db = firestore.Client(project=project) if project else firestore.Client()
    return db


def _get_gcs() -> Any:
    try:
        from google.cloud import storage  # type: ignore

        return storage.Client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("GCS client init failed: %s", exc)
        return None


def _bucket_name() -> str:
    from pipeline_client.backend.settings import settings

    return settings.gcs_bucket or os.getenv("GCS_BUCKET", "")


def _pending_items(db: Any, runner: str, limit: int = 50):
    """Return pending items for one runner, oldest first.

    Both filters execute in Firestore so completed history can never starve new
    work. Ordering stays client-side to avoid requiring a three-field index.
    """
    from google.cloud.firestore_v1 import FieldFilter  # type: ignore

    query = db.collection("pipeline_queue").where(filter=FieldFilter("runner", "==", runner))
    query = query.where(filter=FieldFilter("status", "==", "pending"))
    docs = list(query.limit(limit).stream())
    items = []
    for doc in docs:
        data = doc.to_dict() or {}
        items.append((doc.id, data))
    items.sort(key=lambda pair: str(pair[1].get("created_at") or ""))
    return items


async def _process_one(
    db: Any, gcs: Any, bucket: str, item_id: str, item_data: dict, sem: asyncio.Semaphore, runner: str
) -> None:
    from pipeline_client.backend.queue_processor import claim_item, process_claimed_item

    async with sem:
        lease_owner = f"{os.getenv('HOSTNAME', 'local-worker')}:{uuid.uuid4()}"
        item_ref = db.collection("pipeline_queue").document(item_id)
        claimed = await asyncio.to_thread(claim_item, db, item_ref, lease_owner, runner)
        if not claimed:
            return  # lost the race / already terminal
        race_id = claimed.get("race_id", "?")
        logger.info("Worker leased %s (race %s)", item_id, race_id)
        try:
            await process_claimed_item(db, gcs, bucket, item_id, claimed, lease_owner, runner=runner)
            logger.info("Worker finished %s (race %s)", item_id, race_id)
        except Exception:  # noqa: BLE001
            logger.exception("Worker crashed processing %s (race %s)", item_id, race_id)


async def run_worker() -> None:
    db = _get_db()
    gcs = _get_gcs()
    bucket = _bucket_name()
    if not bucket:
        logger.warning("No GCS bucket configured — drafts/checkpoints will not persist")
    logger.info(
        "Pipeline worker started (runner=%s, once=%s, concurrency=%d, poll=%ds, bucket=%s)",
        _RUNNER,
        _ONCE,
        _CONCURRENCY,
        _POLL_SECONDS,
        bucket or "-",
    )

    stop = asyncio.Event()

    def _request_stop(*_a: Any) -> None:
        logger.info("Shutdown requested — finishing in-flight races, no new leases")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: _request_stop())

    sem = asyncio.Semaphore(_CONCURRENCY)
    in_flight: Set[asyncio.Task] = set()
    last_heartbeat = 0.0
    # WORKER_ONCE (the Cloud Run Job path) already has stdout auto-shipped to Cloud
    # Logging and a per-item lease heartbeat; the Cloud Logging heartbeat below is
    # only meaningful for the long-lived local worker this alert targets.
    emit_heartbeats = not _ONCE

    while not stop.is_set():
        if emit_heartbeats and (time.monotonic() - last_heartbeat) >= _HEARTBEAT_SECONDS:
            _emit_heartbeat()
            last_heartbeat = time.monotonic()
        try:
            capacity = _CONCURRENCY - len(in_flight)
            queue_item_id = os.getenv("QUEUE_ITEM_ID", "").strip()
            if _ONCE and queue_item_id:
                doc = db.collection("pipeline_queue").document(queue_item_id).get()
                data = doc.to_dict() if getattr(doc, "exists", False) else None
                items = [(queue_item_id, data)] if isinstance(data, dict) else []
            else:
                items = _pending_items(db, _RUNNER, limit=max(capacity, 1)) if capacity > 0 else []
        except Exception:  # noqa: BLE001
            logger.exception("Failed to poll pipeline_queue")
            items = []

        started = False
        seen_ids = {t.get_name() for t in in_flight}
        for item_id, item_data in items:
            if len(in_flight) >= _CONCURRENCY:
                break
            if item_id in seen_ids:
                continue
            task = asyncio.create_task(_process_one(db, gcs, bucket, item_id, item_data, sem, _RUNNER), name=item_id)
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
            started = True

        if not started:
            if _ONCE:
                break
            try:
                await asyncio.wait_for(stop.wait(), timeout=_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass

        if _ONCE and in_flight:
            await asyncio.gather(*in_flight, return_exceptions=True)
            in_flight.clear()
            break

    if in_flight:
        logger.info("Waiting for %d in-flight race(s) to finish...", len(in_flight))
        await asyncio.gather(*in_flight, return_exceptions=True)
    logger.info("Local pipeline worker stopped")


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
