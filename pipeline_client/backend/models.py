from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunOptions(BaseModel):
    cheap_mode: bool = True  # Use mini models by default for cost-effective processing
    save_artifact: bool = True
    enable_review: bool = False  # Send to Claude/Gemini for fact-checking
    note: Optional[str] = None


class RunRequest(BaseModel):
    payload: Dict[str, Any] = {}
    options: Optional[RunOptions] = None


class RunResponse(BaseModel):
    step: str
    ok: bool
    output: Any
    error: Optional[str] = None
    artifact_id: Optional[str] = None
    duration_ms: Optional[int] = None
    meta: Dict[str, Any] = {}


class RunStep(BaseModel):
    """Information about a single step within a run."""

    name: str
    status: RunStatus = RunStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    artifact_id: Optional[str] = None
    error: Optional[str] = None


class RunInfo(BaseModel):
    """Information about a pipeline run."""

    run_id: str
    status: RunStatus
    payload: Dict[str, Any]
    options: Dict[str, Any]
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    artifact_id: Optional[str] = None
    error: Optional[str] = None
    steps: List[RunStep] = []
    logs: Optional[List[Dict]] = []


class LogEntry(BaseModel):
    """Structured log entry."""

    timestamp: str
    level: str
    message: str
    step: Optional[str] = None
    run_id: Optional[str] = None
    race_id: Optional[str] = None
    duration_ms: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None
