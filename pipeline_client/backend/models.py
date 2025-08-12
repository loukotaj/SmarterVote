from pydantic import BaseModel
from typing import Any, Dict, Optional, List
from datetime import datetime
from enum import Enum


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunOptions(BaseModel):
    skip_llm_apis: Optional[bool] = None
    skip_external_apis: Optional[bool] = None
    skip_network_calls: Optional[bool] = None
    skip_cloud_services: Optional[bool] = None
    save_artifact: bool = True
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


class RunInfo(BaseModel):
    """Information about a pipeline run."""

    run_id: str
    step: str
    status: RunStatus
    payload: Dict[str, Any]
    options: Dict[str, Any]
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    artifact_id: Optional[str] = None
    error: Optional[str] = None


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


class BatchRunRequest(BaseModel):
    """Request to run multiple race IDs."""

    step: str
    race_ids: List[str]
    options: Optional[RunOptions] = None


class BatchRunResponse(BaseModel):
    """Response for batch run."""

    batch_id: str
    total_runs: int
    runs: List[RunInfo]
