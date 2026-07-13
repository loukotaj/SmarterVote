from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from shared.pipeline_config import PIPELINE_STEP_LABELS, PIPELINE_STEP_ORDER, PIPELINE_STEP_WEIGHTS
from shared.pipeline_options import ResolvedPipelineRunOptions


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CONTINUED = "continued"
    SKIPPED = "skipped"


class PipelineStep(str, Enum):
    """Canonical pipeline step identifiers.

    Fresh runs execute: discovery → images → issues → finance → refinement → review → iteration.
    Update runs execute the same steps in the same order: 'discovery' maps to roster sync +
    meta update, and 'images' runs right after discovery (same position as fresh runs).
    """

    DISCOVERY = "discovery"
    IMAGES = "images"
    ISSUES = "issues"
    FINANCE = "finance"
    REFINEMENT = "refinement"
    POLLING = "polling"
    FORECAST = "forecast"
    VOTER_RESOURCES = "voter_resources"
    REVIEW = "review"
    ITERATION = "iteration"


# Ordered lists for run creation
ALL_STEPS: List[str] = list(PIPELINE_STEP_ORDER)

# Human-readable labels for each step
STEP_LABELS: Dict[str, str] = dict(PIPELINE_STEP_LABELS)

# Weights for progress computation (must sum to 100)
STEP_WEIGHTS: Dict[str, int] = dict(PIPELINE_STEP_WEIGHTS)


class RunOptions(ResolvedPipelineRunOptions):
    """Resolved options used by the local pipeline runner."""


class RunRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[RunOptions] = None


class RunResponse(BaseModel):
    step: str
    ok: bool
    output: Any
    error: Optional[str] = None
    artifact_id: Optional[str] = None
    duration_ms: Optional[int] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class RunStep(BaseModel):
    """Information about a single step within a run."""

    name: str
    label: Optional[str] = None  # Human-readable label
    status: RunStatus = RunStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    progress_pct: Optional[int] = None  # 0-100 progress within this step
    weight: Optional[int] = None  # Weight for overall progress calculation
    artifact_id: Optional[str] = None
    error: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    estimated_usd: Optional[float] = None


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
    steps: List[RunStep] = Field(default_factory=list)
    logs: Optional[List[Dict]] = Field(default_factory=list)
    serper_calls: Optional[int] = None


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
