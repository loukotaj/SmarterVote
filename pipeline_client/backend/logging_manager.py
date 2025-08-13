"""
WebSocket-based logging manager for real-time log streaming.
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket


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


class WebSocketLoggingHandler(logging.Handler):
    """Custom logging handler that streams logs via WebSocket."""

    def __init__(self, manager: "LoggingManager"):
        super().__init__()
        self.manager = manager

    def emit(self, record: logging.LogRecord):
        try:
            # Extract structured data from log record
            log_entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created).isoformat(),
                level=record.levelname.lower(),
                message=record.getMessage(),
                step=getattr(record, "step", None),
                run_id=getattr(record, "run_id", None),
                race_id=getattr(record, "race_id", None),
                duration_ms=getattr(record, "duration_ms", None),
                extra=getattr(record, "extra", None),
            )

            # Add to queue for async processing (non-blocking)
            if self.manager:
                self.manager.add_log_to_queue(log_entry)
        except Exception:
            # Don't let logging errors break the application
            pass


class LoggingManager:
    """Manages WebSocket connections and log broadcasting."""

    def __init__(self, buffer_size: int = 1000):
        self.connections: Dict[str, WebSocket] = {}
        self.run_connections: Dict[str, Set[str]] = {}  # run_id -> connection_ids
        self.log_buffer: deque = deque(maxlen=buffer_size)
        self.lock = threading.Lock()
        self._main_loop = None

        # Setup WebSocket logging handler
        self.handler = WebSocketLoggingHandler(self)
        self.handler.setLevel(logging.DEBUG)

        # Create formatter for structured logs
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.handler.setFormatter(formatter)

    def set_main_loop(self, loop):
        """Set reference to the main event loop for cross-thread communication."""
        self._main_loop = loop

    def setup_logger(self, logger_name: str = "pipeline") -> logging.Logger:
        """Setup a logger with WebSocket streaming."""
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplication
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        logger.addHandler(self.handler)
        return logger

    def add_log_to_queue(self, log_entry: LogEntry):
        """Add log entry to queue for async processing."""
        # Always add to buffer first
        with self.lock:
            self.log_buffer.append(log_entry)

        try:
            # Try to get the main event loop and schedule the broadcast
            main_loop = getattr(self, "_main_loop", None)
            if main_loop and not main_loop.is_closed():
                # Schedule broadcast on main loop (thread-safe)
                def schedule_broadcast():
                    import asyncio

                    asyncio.create_task(self.broadcast_log(log_entry))

                main_loop.call_soon_threadsafe(schedule_broadcast)
            else:
                # Try to get current loop (might be main loop)
                try:
                    import asyncio

                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        asyncio.create_task(self.broadcast_log(log_entry))
                except RuntimeError:
                    # No loop available, logs will be sent when clients connect
                    pass
        except Exception:
            # Fail silently - logs will be available in buffer for new connections
            pass

    async def connect_websocket(self, websocket: WebSocket, connection_id: str, run_id: Optional[str] = None):
        """Register a new WebSocket connection."""
        await websocket.accept()

        with self.lock:
            self.connections[connection_id] = websocket

            if run_id:
                if run_id not in self.run_connections:
                    self.run_connections[run_id] = set()
                self.run_connections[run_id].add(connection_id)

        # Send buffered logs to new connection
        if run_id:
            await self._send_buffered_logs(websocket, run_id)
        else:
            await self._send_buffered_logs(websocket)

    def disconnect_websocket(self, connection_id: str):
        """Unregister a WebSocket connection."""
        with self.lock:
            self.connections.pop(connection_id, None)

            # Remove from run connections
            for run_id, conn_ids in self.run_connections.items():
                conn_ids.discard(connection_id)

    async def broadcast_log(self, log_entry: LogEntry):
        """Broadcast a log entry to relevant WebSocket connections."""
        # Add to buffer
        with self.lock:
            self.log_buffer.append(log_entry)

        # Determine which connections should receive this log
        target_connections = set()

        if log_entry.run_id:
            # Send to connections listening to this specific run
            run_connections = self.run_connections.get(log_entry.run_id, set())
            target_connections.update(run_connections)

        # Send to all general connections (not run-specific)
        general_connections = {
            conn_id
            for conn_id, _ in self.connections.items()
            if not any(conn_id in run_conns for run_conns in self.run_connections.values())
        }
        target_connections.update(general_connections)

        # Broadcast to target connections
        if target_connections:
            message = json.dumps(
                {
                    "type": "log",
                    "level": log_entry.level,
                    "message": log_entry.message,
                    "timestamp": log_entry.timestamp,
                    "run_id": log_entry.run_id,
                }
            )

            disconnected = []
            for conn_id in target_connections:
                websocket = self.connections.get(conn_id)
                if websocket:
                    try:
                        await websocket.send_text(message)
                    except Exception as e:
                        print(f"WebSocket send failed for {conn_id}: {e}")
                        disconnected.append(conn_id)

            # Clean up disconnected connections
            for conn_id in disconnected:
                self.disconnect_websocket(conn_id)

    async def _send_buffered_logs(self, websocket: WebSocket, run_id: Optional[str] = None):
        """Send buffered logs to a newly connected client."""
        try:
            with self.lock:
                logs_to_send = []
                for log_entry in self.log_buffer:
                    if run_id is None or log_entry.run_id == run_id:
                        logs_to_send.append(log_entry)

            if logs_to_send:
                message = json.dumps({"type": "buffered_logs", "data": [log.to_dict() for log in logs_to_send]})
                await websocket.send_text(message)
        except Exception:
            pass

    async def broadcast_message(self, message_data: Dict[str, Any]):
        """Broadcast a structured message to all WebSocket connections."""
        if not self.connections:
            return

        message = json.dumps(message_data)
        disconnected = []

        for conn_id, websocket in self.connections.items():
            try:
                await websocket.send_text(message)
            except Exception as e:
                print(f"WebSocket send failed for {conn_id}: {e}")
                disconnected.append(conn_id)

        # Clean up disconnected connections
        for conn_id in disconnected:
            self.disconnect_websocket(conn_id)

    async def send_run_status(self, run_id: str, status: str, **kwargs):
        """Send run status update to relevant connections."""
        target_connections = self.run_connections.get(run_id, set())

        if target_connections:
            message = json.dumps({"type": "run_status", "data": {"run_id": run_id, "status": status, **kwargs}})

            disconnected = []
            for conn_id in target_connections:
                websocket = self.connections.get(conn_id)
                if websocket:
                    try:
                        await websocket.send_text(message)
                    except Exception:
                        disconnected.append(conn_id)

            # Clean up disconnected connections
            for conn_id in disconnected:
                self.disconnect_websocket(conn_id)


# Global logging manager instance
logging_manager = LoggingManager()
