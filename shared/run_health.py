"""Structured failure taxonomy and health-verdict computation for pipeline runs.

A pipeline run's Firestore ``status`` (``pending``/``running``/``completed``/...)
and a race's ``pipeline_state.complete`` flag both answer "did the run finish
without raising" — neither answers "did the run actually produce trustworthy
data". A run can finish with ``status == "completed"`` and
``pipeline_state.complete == True`` while:

  * review/validation actually failed (``validation_grade.passed`` is False),
  * a step (e.g. ``finance``) silently populated nothing for every candidate,
  * an LLM provider call 403'd on an exhausted/invalid API key,
  * a candidate's stance is literal placeholder junk like ``"DRAFT"``.

This module defines a small, dependency-free taxonomy of failure reasons plus
pure helper functions that classify exceptions and detect the silent-failure
patterns above, and aggregates them into a single :class:`RunHealthVerdict` —
the "did this actually succeed" field referenced throughout the pipeline.

Deliberately has no dependency on ``pipeline_client`` so it can be imported
from ``shared/``, ``services/races-api/``, and ``pipeline_client/`` alike
without introducing a layering cycle. Exception classification is duck-typed
(``getattr(exc, "code", None)`` / ``getattr(exc, "retryable", None)`` /
``exc.__class__.__name__``) rather than importing pipeline_client's error
types directly.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field


class RunFailureReason(str, Enum):
    """Canonical machine-readable reasons a run or step can register a failure."""

    PROVIDER_AUTH_FAILURE = "provider_auth_failure"
    PROVIDER_RATE_LIMIT = "provider_rate_limit"
    PROVIDER_TIMEOUT = "provider_timeout"
    STEP_NO_DATA = "step_no_data"
    VALIDATION_FAILED = "validation_failed"
    PLACEHOLDER_CONTENT = "placeholder_content"
    ROSTER_VERIFICATION_FAILED = "roster_verification_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    UNKNOWN_ERROR = "unknown_error"


class RunHealthStatus(str, Enum):
    """Overall machine-readable health verdict — distinct from run ``status``."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


# Reasons whose mere presence makes the run FAILED rather than merely DEGRADED.
_HARD_FAILURE_REASONS = frozenset(
    {
        RunFailureReason.VALIDATION_FAILED,
        RunFailureReason.ROSTER_VERIFICATION_FAILED,
        RunFailureReason.PROVIDER_AUTH_FAILURE,
        RunFailureReason.BUDGET_EXHAUSTED,
        RunFailureReason.CANCELLED,
        RunFailureReason.UNKNOWN_ERROR,
    }
)


class StepFailure(BaseModel):
    """A single failure registered against one pipeline step."""

    step: str
    reason: RunFailureReason
    detail: Optional[str] = None


class RunHealthVerdict(BaseModel):
    """Definitive machine-readable answer to "did this run actually work".

    This is intentionally a different field from ``status == "completed"`` and
    ``pipeline_state.complete`` — both of those can be true even when this
    verdict is FAILED or DEGRADED.
    """

    status: RunHealthStatus = RunHealthStatus.UNKNOWN
    reasons: List[RunFailureReason] = Field(default_factory=list)
    step_failures: List[StepFailure] = Field(default_factory=list)
    summary: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.status == RunHealthStatus.HEALTHY


# ---------------------------------------------------------------------------
# Placeholder-junk stance detection
# ---------------------------------------------------------------------------

# Deliberately narrower than the pipeline's broader "missing stance" marker
# set (which also matches legitimate deliberate conclusions like "no public
# position found"). This set only matches literal junk artifacts an LLM
# sometimes leaves behind — e.g. a stance that is just the word "DRAFT" —
# which should register as a failure rather than pass through silently.
PLACEHOLDER_JUNK_MARKERS = frozenset(
    {
        "draft",
        "tbd",
        "todo",
        "fixme",
        "wip",
        "n/a",
        "na",
        "none",
        "test",
        "placeholder",
        "xxx",
        "lorem ipsum",
        "sample",
        "example",
        "dummy",
    }
)


def is_placeholder_junk_stance(stance: Any) -> bool:
    """True if *stance* is nothing but a literal placeholder artifact.

    Exact-match only (after trim/casefold) so genuine stances that merely
    contain a marker word (e.g. a real policy position mentioning "testing")
    are never misclassified.
    """
    if not isinstance(stance, str):
        return False
    normalized = stance.strip().strip(".").strip().lower()
    return normalized in PLACEHOLDER_JUNK_MARKERS


# ---------------------------------------------------------------------------
# Per-step failure bookkeeping (persisted on race_json.pipeline_state)
# ---------------------------------------------------------------------------


def record_step_failure(
    race_json: Dict[str, Any],
    step: str,
    reason: RunFailureReason,
    detail: str = "",
) -> None:
    """Append a deduplicated failure record to ``race_json.pipeline_state.step_failures``.

    Storing this directly on the race document (rather than only on the
    ephemeral run record) means the failure survives checkpointing, drafts,
    and eventual publish — the same durability guarantee the rest of
    ``pipeline_state`` already relies on.
    """
    if not isinstance(race_json, dict):
        return
    pipeline_state = race_json.setdefault("pipeline_state", {})
    if not isinstance(pipeline_state, dict):
        return
    failures = pipeline_state.setdefault("step_failures", [])
    if not isinstance(failures, list):
        failures = []
        pipeline_state["step_failures"] = failures
    reason_value = reason.value if isinstance(reason, RunFailureReason) else str(reason)
    entry = {"step": step, "reason": reason_value, "detail": detail or None}
    for existing in failures:
        if isinstance(existing, dict) and existing.get("step") == step and existing.get("reason") == reason_value:
            return  # already recorded; avoid unbounded growth across retries/normalization passes
    failures.append(entry)


def get_step_failures(race_json: Dict[str, Any]) -> List[StepFailure]:
    """Parse the raw step-failure dicts back into typed models, tolerating garbage entries."""
    if not isinstance(race_json, dict):
        return []
    pipeline_state = race_json.get("pipeline_state")
    if not isinstance(pipeline_state, dict):
        return []
    raw = pipeline_state.get("step_failures")
    if not isinstance(raw, list):
        return []
    parsed: List[StepFailure] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            parsed.append(StepFailure.model_validate(entry))
        except Exception:
            continue
    return parsed


# ---------------------------------------------------------------------------
# Silent-failure detectors
# ---------------------------------------------------------------------------


def detect_empty_finance_output(race_json: Dict[str, Any], candidate_names: Optional[Iterable[str]] = None) -> bool:
    """True if the finance step produced no donor/voting data for any target candidate.

    Only fires when there is at least one candidate to check — an empty
    roster is a different failure (STEP_NO_DATA at the discovery/roster
    level), not a finance-specific silent failure.
    """
    if not isinstance(race_json, dict):
        return False
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return False
    names = set(candidate_names) if candidate_names is not None else None
    targeted = [c for c in candidates if isinstance(c, dict) and (names is None or str(c.get("name") or "") in names)]
    if not targeted:
        return False
    return all(not c.get("donor_summary") and not c.get("voting_summary") for c in targeted)


# ---------------------------------------------------------------------------
# Exception classification
# ---------------------------------------------------------------------------

_AUTH_CODES = {"auth_failure", "quota_exceeded", "unauthorized", "forbidden"}
_RATE_LIMIT_CODES = {"rate_limited", "rate_limit"}
_TIMEOUT_CODES = {"provider_unavailable", "connection_failed", "timeout", "request_timeout"}


def classify_exception(exc: BaseException) -> RunFailureReason:
    """Map an arbitrary exception to a taxonomy reason.

    Duck-typed against pipeline_client's ``ProviderError`` family (``.code``,
    ``.retryable``) and a handful of well-known control-flow exception class
    names, so this module never needs to import pipeline_client directly.
    """
    class_name = exc.__class__.__name__
    if class_name in {"RunBudgetExceeded"}:
        return RunFailureReason.BUDGET_EXHAUSTED
    if class_name in {"AgentCancelled"}:
        return RunFailureReason.CANCELLED

    code = getattr(exc, "code", None)
    if isinstance(code, str):
        if code in _AUTH_CODES:
            return RunFailureReason.PROVIDER_AUTH_FAILURE
        if code in _RATE_LIMIT_CODES:
            return RunFailureReason.PROVIDER_RATE_LIMIT
        if code in _TIMEOUT_CODES:
            return RunFailureReason.PROVIDER_TIMEOUT

    message = str(exc).lower()
    if "qualifying" in message and "evidence" in message:
        # e.g. "new candidate(s) lack qualifying current-cycle exact-contest evidence"
        # (see pipeline_client/backend/handlers/agent.py _save_draft)
        return RunFailureReason.ROSTER_VERIFICATION_FAILED
    if "roster" in message and ("evidence" in message or "verif" in message):
        return RunFailureReason.ROSTER_VERIFICATION_FAILED
    if (
        "no candidates" in message
        or "placeholder candidate" in message
        or "no 'candidates'" in message
        or ("'candidates'" in message and ("missing" in message or "empty" in message))
        or "only contains placeholder candidate names" in message
    ):
        return RunFailureReason.STEP_NO_DATA

    if getattr(exc, "retryable", None) is True:
        return RunFailureReason.PROVIDER_TIMEOUT

    return RunFailureReason.UNKNOWN_ERROR


# ---------------------------------------------------------------------------
# Aggregate verdict
# ---------------------------------------------------------------------------


def compute_run_health_verdict(
    race_json: Dict[str, Any],
    *,
    should_review: bool,
    validation_grade: Optional[Dict[str, Any]] = None,
) -> RunHealthVerdict:
    """Aggregate per-step failures plus review/validation outcome into one verdict.

    ``should_review`` mirrors the caller's decision of whether review actually
    ran this pass (see ``run_agent``'s own ``should_review`` gating) — when
    review didn't run there is nothing to validate yet, so a missing/failed
    grade is not (by itself) evidence of failure.
    """
    step_failures = get_step_failures(race_json)
    reasons: List[RunFailureReason] = []
    for failure in step_failures:
        if failure.reason not in reasons:
            reasons.append(failure.reason)

    if should_review:
        passed = isinstance(validation_grade, dict) and validation_grade.get("passed") is True
        if not passed and RunFailureReason.VALIDATION_FAILED not in reasons:
            reasons.append(RunFailureReason.VALIDATION_FAILED)

    if not reasons:
        return RunHealthVerdict(status=RunHealthStatus.HEALTHY, reasons=[], step_failures=step_failures)

    status = RunHealthStatus.FAILED if any(r in _HARD_FAILURE_REASONS for r in reasons) else RunHealthStatus.DEGRADED
    summary = "; ".join(f"{f.step}: {f.reason.value}" + (f" ({f.detail})" if f.detail else "") for f in step_failures)
    if (
        should_review
        and RunFailureReason.VALIDATION_FAILED in reasons
        and not any(f.reason == RunFailureReason.VALIDATION_FAILED for f in step_failures)
    ):
        grade = validation_grade.get("grade") if isinstance(validation_grade, dict) else None
        extra = f"review/validation did not pass (grade={grade})"
        summary = f"{summary}; {extra}" if summary else extra

    return RunHealthVerdict(status=status, reasons=reasons, step_failures=step_failures, summary=summary or None)
