from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
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
    REVIEW = "review"
    ITERATION = "iteration"


# Ordered lists for run creation
ALL_STEPS: List[str] = [s.value for s in PipelineStep]

# Human-readable labels for each step
STEP_LABELS: Dict[str, str] = {
    PipelineStep.DISCOVERY: "Discovery",
    PipelineStep.IMAGES: "Image Resolution",
    PipelineStep.ISSUES: "Issue Research",
    PipelineStep.FINANCE: "Finance & Voting",
    PipelineStep.REFINEMENT: "Refinement",
    PipelineStep.REVIEW: "AI Review",
    PipelineStep.ITERATION: "Review Iteration",
}

# Weights for progress computation (must sum to 100)
STEP_WEIGHTS: Dict[str, int] = {
    PipelineStep.DISCOVERY: 15,
    PipelineStep.IMAGES: 5,
    PipelineStep.ISSUES: 35,
    PipelineStep.FINANCE: 10,
    PipelineStep.REFINEMENT: 15,
    PipelineStep.REVIEW: 12,
    PipelineStep.ITERATION: 8,
}


class RunOptions(BaseModel):
    cheap_mode: bool = True  # Use cheaper/faster model variants
    save_artifact: bool = True
    note: Optional[str] = None
    force_fresh: bool = False  # Ignore existing data and start from scratch
    # Model overrides (None = use default based on cheap_mode)
    research_model: Optional[str] = None   # OpenAI model for research phases
    claude_model: Optional[str] = None     # Claude model for review
    gemini_model: Optional[str] = None     # Gemini model for review
    grok_model: Optional[str] = None       # Grok model for review
    # Step-level configuration: list of step names to run.
    # None/empty = all steps (backward compatible). Steps not listed are SKIPPED.
    enabled_steps: Optional[List[str]] = None
    # Candidate analysis limits
    max_candidates: Optional[int] = None  # Max candidates to research (None = all)
    target_no_info: bool = False  # Prioritise candidates with least existing info
    candidate_names: Optional[List[str]] = None  # Restrict update/research to named candidates

    @field_validator("enabled_steps")
    @classmethod
    def validate_enabled_steps(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized = [step.strip() for step in value if isinstance(step, str) and step.strip()]
        if not normalized:
            raise ValueError("enabled_steps cannot be empty when provided")
        deduped = list(dict.fromkeys(normalized))
        invalid = [step for step in deduped if step not in ALL_STEPS]
        if invalid:
            raise ValueError(f"Unknown enabled_steps: {', '.join(invalid)}")
        return deduped

    @field_validator("candidate_names")
    @classmethod
    def normalize_candidate_names(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized = [name.strip() for name in value if isinstance(name, str) and name.strip()]
        return list(dict.fromkeys(normalized)) or None

    @model_validator(mode="after")
    def validate_step_dependencies(self) -> "RunOptions":
        if self.enabled_steps and "iteration" in self.enabled_steps and "review" not in self.enabled_steps:
            raise ValueError("'iteration' requires 'review' in enabled_steps")
        return self
    candidate_names: Optional[List[str]] = None  # Exact candidate names to target


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
    label: Optional[str] = None  # Human-readable label
    status: RunStatus = RunStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    progress_pct: Optional[int] = None  # 0-100 progress within this step
    weight: Optional[int] = None  # Weight for overall progress calculation
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
