"""Server-side persistent queue for pipeline runs.

Races are added to the queue and processed sequentially. Queue state is
persisted to Firestore on Cloud Run (durable across restarts), or to a
local JSON file in dev mode. The processing loop automatically picks up
the next pending item when the current one completes or fails.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class QueueItemOptions(BaseModel):
    cheap_mode: bool = True
    save_artifact: bool = True
    force_fresh: bool = False
    research_model: Optional[str] = None
    claude_model: Optional[str] = None
    gemini_model: Optional[str] = None
    grok_model: Optional[str] = None
    enabled_steps: Optional[List[str]] = None
    max_candidates: Optional[int] = None
    target_no_info: bool = False
    candidate_names: Optional[List[str]] = None
    candidate_names: Optional[List[str]] = None


class QueueItem(BaseModel):
    id: str
    race_id: str
    status: str = "pending"  # pending | running | completed | failed | cancelled
    options: QueueItemOptions = QueueItemOptions()
    run_id: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class QueueManager:
    """Persistent queue that auto-processes pipeline runs sequentially.

    On Cloud Run: uses Firestore (persists across restarts)
    In local dev: uses local JSON file (ephemeral, but fast)
    """

    def __init__(self, storage_path: str = "pipeline_client/queue.json"):
        self._storage_path = Path(storage_path)
        self._items: List[QueueItem] = []
        self._processing = False
        self._db: Optional[Any] = None  # Firestore client if available
        self._use_firestore = False
        self._init_storage()
        self._load()

    def _init_storage(self) -> None:
        """Initialize Firestore if FIRESTORE_PROJECT is set, otherwise use JSON file.

        On Cloud Run: FIRESTORE_PROJECT is required. Fail fast if missing.
        """
        project = os.getenv("FIRESTORE_PROJECT")

        # Check if running on Cloud Run
        is_cloud_run = bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_SERVICE"))

        if not project:
            if is_cloud_run:
                raise RuntimeError(
                    "Cloud Run detected but FIRESTORE_PROJECT is not set. "
                    "Queue requires Firestore for durability across restarts. "
                    "Set FIRESTORE_PROJECT via Terraform/deployment scripts."
                )
            logging.getLogger(__name__).debug("QueueManager: FIRESTORE_PROJECT not set — using local JSON file (dev mode)")
            return

        try:
            from google.cloud import firestore  # type: ignore
            self._db = firestore.Client(project=project)
            self._use_firestore = True
            logging.getLogger(__name__).info(f"QueueManager: using Firestore project={project} collection=pipeline_queue")
        except ImportError:
            if is_cloud_run:
                raise RuntimeError("Cloud Run detected but google-cloud-firestore not installed. Install with: pip install google-cloud-firestore")
            logging.getLogger(__name__).warning("google-cloud-firestore not installed; using local JSON file")
        except Exception as e:
            if is_cloud_run:
                raise RuntimeError(f"Cloud Run detected but failed to initialize Firestore: {e}")
            logging.getLogger(__name__).exception("Firestore init failed; falling back to local JSON file")

    # -- Persistence --------------------------------------------------------

    def _load(self):
        """Load queue state from Firestore or local JSON file."""
        if self._use_firestore:
            self._load_from_firestore()
        else:
            self._load_from_json()

    def _get_collection(self):
        if self._db is None:
            raise RuntimeError("Firestore client unavailable")
        return self._db.collection("pipeline_queue")

    def _persist_item_firestore(self, item: QueueItem) -> None:
        self._get_collection().document(item.id).set(item.model_dump(mode="json"))

    def _delete_item_firestore(self, item_id: str) -> None:
        self._get_collection().document(item_id).delete()

    def _load_from_firestore(self):
        """Load all queue items from Firestore."""
        try:
            collection = self._get_collection()
            docs = collection.stream()
            self._items = []
            for doc in docs:
                data = doc.to_dict()
                self._items.append(QueueItem(**data))

            # Mark interrupted runs as failed on restart
            for item in self._items:
                if item.status == "running":
                    item.status = "failed"
                    item.error = "Server restarted during processing"
                    item.completed_at = datetime.now(timezone.utc).isoformat()
                    # Save the failed state back to Firestore
                    collection.document(item.id).set(item.model_dump(mode="json"))

            logging.getLogger(__name__).info(f"QueueManager: loaded {len(self._items)} items from Firestore")
        except Exception:
            logging.getLogger(__name__).exception("Failed to load queue from Firestore; starting with empty queue")
            self._items = []

    def _load_from_json(self):
        """Load all queue items from local JSON file."""
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            self._items = [QueueItem(**item) for item in data]
            # Mark interrupted runs as failed on restart
            for item in self._items:
                if item.status == "running":
                    item.status = "failed"
                    item.error = "Server restarted during processing"
                    item.completed_at = datetime.now(timezone.utc).isoformat()
            self._save()
        except Exception:
            logging.getLogger(__name__).exception("Failed to load queue state from JSON")
            self._items = []

    def _save(self):
        """Save queue state to Firestore or JSON file."""
        if self._use_firestore:
            self._save_to_firestore()
        else:
            self._save_to_json()

    def _save_to_firestore(self):
        """Persist queue items to Firestore."""
        try:
            collection = self._get_collection()
            # Write all items
            for item in self._items:
                collection.document(item.id).set(item.model_dump(mode="json"))
        except Exception:
            logging.getLogger(__name__).exception("Failed to save queue to Firestore; data may be lost on restart")

    def _save_to_json(self):
        """Persist queue items to local JSON file."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [item.model_dump(mode="json") for item in self._items]
        self._storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # -- Queue Operations ---------------------------------------------------

    def add(self, race_id: str, options: Optional[Dict[str, Any]] = None) -> QueueItem:
        """Add a race to the queue. Raises ValueError if already queued."""
        active = [i for i in self._items if i.race_id == race_id and i.status in ("pending", "running")]
        if active:
            raise ValueError(f"Race '{race_id}' is already queued")

        item = QueueItem(
            id=uuid.uuid4().hex[:8],
            race_id=race_id,
            options=QueueItemOptions(**(options or {})),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._items.append(item)
        if self._use_firestore:
            self._persist_item_firestore(item)
        else:
            self._save_to_json()
        return item

    def remove(self, item_id: str) -> bool:
        """Remove a pending item from the queue."""
        for i, item in enumerate(self._items):
            if item.id == item_id and item.status == "pending":
                self._items.pop(i)
                if self._use_firestore:
                    try:
                        self._delete_item_firestore(item_id)
                    except Exception:
                        logging.getLogger(__name__).exception(f"Failed to delete queue item {item_id} from Firestore")
                else:
                    self._save_to_json()
                return True
        return False

    def cancel(self, item_id: str) -> bool:
        """Cancel a pending or running item.

        If the item is running (has an active run), also cancel the run via run_manager.
        """
        for item in self._items:
            if item.id == item_id and item.status in ("pending", "running"):
                was_running = item.status == "running"
                run_id = item.run_id if was_running else None

                item.status = "cancelled"
                item.completed_at = datetime.now(timezone.utc).isoformat()
                if self._use_firestore:
                    self._persist_item_firestore(item)
                else:
                    self._save_to_json()

                # If the item had an active run, cancel it too
                if was_running and run_id:
                    try:
                        from .run_manager import run_manager
                        run_manager.cancel_run(run_id)
                        logger = logging.getLogger(__name__)
                        logger.info(f"Queue: cancelled queue item {item_id}, also cancelled run {run_id}")
                    except Exception:
                        logger = logging.getLogger(__name__)
                        logger.exception(f"Queue: failed to cancel run {run_id} for queue item {item_id}")

                return True
        return False

    def clear_finished(self) -> int:
        """Remove completed/failed/cancelled items. Returns count removed."""
        before = len(self._items)
        finished_ids = [i.id for i in self._items if i.status in ("completed", "failed", "cancelled")]
        self._items = [i for i in self._items if i.status in ("pending", "running")]
        if not self._use_firestore:
            self._save_to_json()

        # Clean up Firestore documents for removed items
        if self._use_firestore:
            try:
                for item_id in finished_ids:
                    self._delete_item_firestore(item_id)
            except Exception:
                logging.getLogger(__name__).exception("Failed to delete finished items from Firestore")

        return before - len(self._items)

    def get_all(self) -> List[QueueItem]:
        return list(self._items)

    def get_item(self, item_id: str) -> Optional[QueueItem]:
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def get_next_pending(self) -> Optional[QueueItem]:
        for item in self._items:
            if item.status == "pending":
                return item
        return None

    def has_running(self) -> bool:
        return any(item.status == "running" for item in self._items)

    def pending_count(self) -> int:
        return sum(1 for i in self._items if i.status == "pending")

    def mark_running(self, item_id: str, run_id: str):
        for item in self._items:
            if item.id == item_id:
                item.status = "running"
                item.run_id = run_id
                item.started_at = datetime.now(timezone.utc).isoformat()
                if self._use_firestore:
                    self._persist_item_firestore(item)
                else:
                    self._save_to_json()
                return

    def mark_completed(self, item_id: str):
        for item in self._items:
            if item.id == item_id:
                item.status = "completed"
                item.completed_at = datetime.now(timezone.utc).isoformat()
                if self._use_firestore:
                    self._persist_item_firestore(item)
                else:
                    self._save_to_json()
                return

    def mark_failed(self, item_id: str, error: str):
        for item in self._items:
            if item.id == item_id:
                item.status = "failed"
                item.error = error
                item.completed_at = datetime.now(timezone.utc).isoformat()
                if self._use_firestore:
                    self._persist_item_firestore(item)
                else:
                    self._save_to_json()
                return

    # -- Processing ---------------------------------------------------------

    async def process_next(self):
        """Process the next pending item if nothing is currently running."""
        if self._processing or self.has_running():
            return

        next_item = self.get_next_pending()
        if not next_item:
            return

        self._processing = True
        try:
            await self._process_item(next_item)
        finally:
            self._processing = False
            # Schedule next item if any remain
            if self.get_next_pending():
                asyncio.create_task(self.process_next())

    async def _process_item(self, item: QueueItem):
        """Process a single queue item using the existing pipeline runner."""
        from .models import RunOptions, RunRequest
        from .pipeline_runner import run_step_async
        from .race_manager import race_manager
        from .run_manager import run_manager

        logger = logging.getLogger("pipeline")
        logger.info(f"Queue: starting {item.race_id} (queue_id={item.id})")

        request = RunRequest(
            payload={"race_id": item.race_id},
            options=RunOptions(**item.options.model_dump()),
        )
        run_info = run_manager.create_run(["agent"], request)
        self.mark_running(item.id, run_info.run_id)

        # Update race record
        race_manager.start_run(item.race_id, run_info.run_id)
        race_manager.save_run(item.race_id, run_info)

        try:
            result = await run_step_async("agent", request, run_info.run_id)
            if result.ok:
                self.mark_completed(item.id)
                logger.info(f"Queue: completed {item.race_id}")
            else:
                self.mark_failed(item.id, result.error or "Unknown error")
                logger.error(f"Queue: failed {item.race_id}: {result.error}")
        except Exception as e:
            self.mark_failed(item.id, str(e))
            logger.exception(f"Queue: error processing {item.race_id}")


# Global instance
queue_manager = QueueManager()
