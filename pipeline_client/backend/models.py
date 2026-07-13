from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from shared.pipeline_config import (
    PIPELINE_STEP_LABELS,
    PIPELINE_STEP_ORDER,
    PIPELINE_STEP_WEIGHTS,
    normalize_model_profile,
    normalize_pipeline_steps,
    normalize_review_providers,
    validate_model_override_keys,
)


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


class RunOptions(BaseModel):
    cheap_mode: bool = True  # Use cheaper/faster model variants
    save_artifact: bool = True
    note: Optional[str] = None
    goal: Optional[str] = None  # Short description of why this run is being triggered (shown in Runs tab)
    force_fresh: bool = False  # Ignore existing data and start from scratch
    baseline_source: Literal["latest", "published"] = "latest"  # Existing-data source for targeted updates
    # Model overrides (None = use default based on cheap_mode)
    research_model: Optional[str] = None  # OpenRouter model for research phases
    claude_model: Optional[str] = None  # OpenRouter Claude reviewer model
    gemini_model: Optional[str] = None  # OpenRouter Gemini reviewer model
    grok_model: Optional[str] = None  # OpenRouter Grok reviewer model
    model_profile: Optional[str] = None  # economy | balanced | quality | custom
    model_overrides: Optional[Dict[str, str]] = None  # Role-specific OpenRouter model overrides
    review_providers: Optional[List[str]] = None  # Enabled reviewer roles: claude | gemini | grok
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
        return normalize_pipeline_steps(value)

    @field_validator("max_candidates")
    @classmethod
    def validate_max_candidates(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 1:
            raise ValueError("max_candidates must be at least 1 when provided")
        return value

    @field_validator("model_overrides")
    @classmethod
    def validate_model_overrides(cls, value: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        return validate_model_override_keys(value)

    @field_validator("candidate_names")
    @classmethod
    def normalize_candidate_names(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized = [name.strip() for name in value if isinstance(name, str) and name.strip()]
        return list(dict.fromkeys(normalized)) or None

    @field_validator("model_profile")
    @classmethod
    def validate_model_profile(cls, value: Optional[str]) -> Optional[str]:
        return normalize_model_profile(value)

    @field_validator("review_providers")
    @classmethod
    def validate_review_providers(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return normalize_review_providers(value)

    @model_validator(mode="after")
    def validate_step_dependencies(self) -> "RunOptions":
        if self.enabled_steps and "iteration" in self.enabled_steps and "review" not in self.enabled_steps:
            raise ValueError("'iteration' requires 'review' in enabled_steps")
        return self


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
