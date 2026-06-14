"""Local pipeline logging manager.

The admin UI now polls run status and logs from REST endpoints. This module
keeps the structured logging/status API used by the local runner without
maintaining persistent socket connections.
"""

import asyncio
import logging
import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from pipeline_client.logging_utils import sanitize_log_data, sanitize_log_message

logger = logging.getLogger("pipeline")


@dataclass
class LogEntry:
    """Structured log entry with metadata."""

    timestamp: str
    level: str
    message: str
    step: Optional[str] = None
    run_id: Optional[str] = None
    race_id: Optional[str] = None
    duration_ms: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PipelineLoggingHandler(logging.Handler):
    """Logging handler that stores structured logs in a local buffer."""

    def __init__(self, manager: "LoggingManager"):
        super().__init__()
        self.manager = manager

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created).isoformat(),
                level=record.levelname.lower(),
                message=sanitize_log_message(record.getMessage()),
                step=getattr(record, "step", None),
                run_id=getattr(record, "run_id", None),
                race_id=getattr(record, "race_id", None),
                duration_ms=getattr(record, "duration_ms", None),
                extra=sanitize_log_data(getattr(record, "extra", None)),
            )
            self.manager.add_log_to_queue(log_entry)
        except Exception:
            # Logging must never break the pipeline.
            pass


class LoggingManager:
    """Stores local log/status events and exposes async broadcast-compatible helpers."""

    def __init__(self, buffer_size: int = 1000):
        self.log_buffer: deque[LogEntry] = deque(maxlen=buffer_size)
        self.status_buffer: deque[dict[str, Any]] = deque(maxlen=buffer_size)
        self.lock = threading.Lock()
        self._main_loop = None

        self.handler = PipelineLoggingHandler(self)
        self.handler.setLevel(logging.DEBUG)
        self.handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    def set_main_loop(self, loop) -> None:
        """Set reference to the main event loop for cross-thread scheduling."""
        self._main_loop = loop

    def setup_logger(self, logger_name: str = "pipeline") -> logging.Logger:
        """Attach the local structured handler without removing per-run handlers."""
        target = logging.getLogger(logger_name)
        target.setLevel(logging.DEBUG)
        if self.handler not in target.handlers:
            target.addHandler(self.handler)
        return target

    def add_log_to_queue(self, log_entry: LogEntry) -> None:
        """Add a log entry to the local buffer."""
        with self.lock:
            self.log_buffer.append(log_entry)

        try:
            main_loop = getattr(self, "_main_loop", None)
            if main_loop and not main_loop.is_closed():

                def schedule_broadcast() -> None:
                    asyncio.create_task(self.broadcast_log(log_entry))

                main_loop.call_soon_threadsafe(schedule_broadcast)
                return

            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    asyncio.create_task(self.broadcast_log(log_entry))
            except RuntimeError:
                pass
        except Exception:
            pass

    async def broadcast_log(self, log_entry: LogEntry) -> None:
        """Compatibility hook for callers that used to stream log events."""
        return None

    async def broadcast_message(self, message_data: dict) -> None:
        """Store a structured status/log event for local debugging."""
        with self.lock:
            self.status_buffer.append(sanitize_log_data(message_data))

    async def send_run_status(self, run_id: str, status: str, **kwargs) -> None:
        """Store a structured run status event for local debugging."""
        await self.broadcast_message({"type": "run_status", "data": {"run_id": run_id, "status": status, **kwargs}})


logging_manager = LoggingManager()
