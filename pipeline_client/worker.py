"""Long-lived local pipeline worker.

Leases ``runner == "local"`` items from the Firestore ``pipeline_queue`` and runs
them to completion in-process with a far-future deadline — so no Cloud Function
handoff/continuation churn (see ``pipeline_client/backend/queue_processor.py``).
Runs alongside the Cloud Function: the CF skips ``runner=="local"`` items and the
worker only picks those up, so the two never fight over the same work.

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
import uuid
from pathlib import Path
from typing import Any, Set

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("pipeline_worker")

_CONCURRENCY = max(1, int(os.getenv("WORKER_CONCURRENCY", "2")))
_POLL_SECONDS = max(1, int(os.getenv("WORKER_POLL_SECONDS", "3")))


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


def _pending_local_items(db: Any, limit: int = 50):
    """Yield (item_id, item_data) for pending runner==local items, oldest first.

    Uses a single-field equality filter (no composite index needed); status +
    ordering are applied client-side since the local queue is small.
    """
    from google.cloud.firestore_v1 import FieldFilter  # type: ignore

    docs = list(db.collection("pipeline_queue").where(filter=FieldFilter("runner", "==", "local")).limit(limit).stream())
    items = []
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("status") == "pending":
            items.append((doc.id, data))
    items.sort(key=lambda pair: str(pair[1].get("created_at") or ""))
    return items


async def _process_one(db: Any, gcs: Any, bucket: str, item_id: str, item_data: dict, sem: asyncio.Semaphore) -> None:
    from pipeline_client.backend.queue_processor import claim_local_item, process_claimed_item

    async with sem:
        lease_owner = f"{os.getenv('HOSTNAME', 'local-worker')}:{uuid.uuid4()}"
        item_ref = db.collection("pipeline_queue").document(item_id)
        claimed = await asyncio.to_thread(claim_local_item, db, item_ref, lease_owner)
        if not claimed:
            return  # lost the race / already terminal
        race_id = claimed.get("race_id", "?")
        logger.info("Worker leased %s (race %s)", item_id, race_id)
        try:
            await process_claimed_item(db, gcs, bucket, item_id, claimed, lease_owner)
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
        "Local pipeline worker started (concurrency=%d, poll=%ds, bucket=%s)", _CONCURRENCY, _POLL_SECONDS, bucket or "-"
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

    while not stop.is_set():
        try:
            capacity = _CONCURRENCY - len(in_flight)
            items = _pending_local_items(db, limit=max(capacity, 1)) if capacity > 0 else []
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
            task = asyncio.create_task(_process_one(db, gcs, bucket, item_id, item_data, sem), name=item_id)
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
            started = True

        if not started:
            try:
                await asyncio.wait_for(stop.wait(), timeout=_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass

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
