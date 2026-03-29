"""Server-side persistent queue for pipeline runs.

Races are added to the queue and processed sequentially. Queue state is
persisted to a JSON file so it survives server restarts. The processing
loop automatically picks up the next pending item when the current one
completes or fails.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class QueueItemOptions(BaseModel):
    cheap_mode: bool = True
    enable_review: bool = True
    save_artifact: bool = True
    research_model: Optional[str] = None
    claude_model: Optional[str] = None
    gemini_model: Optional[str] = None
    grok_model: Optional[str] = None


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
    """Persistent queue that auto-processes pipeline runs sequentially."""

    def __init__(self, storage_path: str = "pipeline_client/queue.json"):
        self._storage_path = Path(storage_path)
        self._items: List[QueueItem] = []
        self._processing = False
        self._load()

    # -- Persistence --------------------------------------------------------

    def _load(self):
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
            logging.exception("Failed to load queue state")
            self._items = []

    def _save(self):
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
        self._save()
        return item

    def remove(self, item_id: str) -> bool:
        """Remove a pending item from the queue."""
        for i, item in enumerate(self._items):
            if item.id == item_id and item.status == "pending":
                self._items.pop(i)
                self._save()
                return True
        return False

    def cancel(self, item_id: str) -> bool:
        """Cancel a pending or running item."""
        for item in self._items:
            if item.id == item_id and item.status in ("pending", "running"):
                item.status = "cancelled"
                item.completed_at = datetime.now(timezone.utc).isoformat()
                self._save()
                return True
        return False

    def clear_finished(self) -> int:
        """Remove completed/failed/cancelled items. Returns count removed."""
        before = len(self._items)
        self._items = [i for i in self._items if i.status in ("pending", "running")]
        self._save()
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
                self._save()
                return

    def mark_completed(self, item_id: str):
        for item in self._items:
            if item.id == item_id:
                item.status = "completed"
                item.completed_at = datetime.now(timezone.utc).isoformat()
                self._save()
                return

    def mark_failed(self, item_id: str, error: str):
        for item in self._items:
            if item.id == item_id:
                item.status = "failed"
                item.error = error
                item.completed_at = datetime.now(timezone.utc).isoformat()
                self._save()
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
        from .run_manager import run_manager

        logger = logging.getLogger("pipeline")
        logger.info(f"Queue: starting {item.race_id} (queue_id={item.id})")

        request = RunRequest(
            payload={"race_id": item.race_id},
            options=RunOptions(**item.options.model_dump()),
        )
        run_info = run_manager.create_run(["agent"], request)
        self.mark_running(item.id, run_info.run_id)

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
