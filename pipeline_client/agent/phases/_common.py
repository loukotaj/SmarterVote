"""Shared constants and helpers used across the phase modules.

Kept separate from any single phase so ``discovery``, ``issues``,
``finance``, ``refinement``, ``polling``, ``forecast``, ``voter_resources``,
and ``iteration`` can all depend on it without depending on each other.
"""

import asyncio
import logging
from typing import Any, Dict, List

# Unused in this module but re-exported on purpose: the phase modules import all four
# from ``._common`` rather than from ``shared.run_health``, so dropping them here breaks
# finance, forecast, issues, iteration, polling, refinement and update_run at import time.
from shared.run_health import RunFailureReason  # noqa: F401
from shared.run_health import classify_exception as _classify_exception  # noqa: F401
from shared.run_health import detect_empty_finance_output as _detect_empty_finance_output  # noqa: F401
from shared.run_health import record_step_failure as _record_step_failure  # noqa: F401

from .. import phase_state, roster
from ..run_budget import RunBudget, RunBudgetExceeded

logger = logging.getLogger("pipeline")

_CONTROL_FLOW_EXCEPTION_NAMES = {
    "AgentCancelled",
    "HandoffFailed",
    "HandoffTriggered",
    "PipelineWorkRemaining",
    "RunBudgetExceeded",
}


class PipelineWorkRemaining(RuntimeError):
    """Signal that durable work units remain and a continuation is required."""


def _is_control_flow_exception(exc: Exception) -> bool:
    return exc.__class__.__name__ in _CONTROL_FLOW_EXCEPTION_NAMES


async def _await_with_run_budget(
    awaitable: Any,
    *,
    run_budget: RunBudget | None,
    requested_timeout: float,
    operation: str,
) -> Any:
    """Bound phase-level network helpers that do not receive RunBudget directly."""
    if not run_budget:
        return await awaitable
    timeout = run_budget.bounded_timeout(requested_timeout, minimum_seconds=2.0, operation=operation)
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise RunBudgetExceeded(f"{operation} exceeded the remaining run budget") from exc


async def _await_advisory_with_run_budget(
    awaitable: Any,
    *,
    run_budget: RunBudget | None,
    requested_timeout: float,
    operation: str,
    log: Any,
    continuation: str,
) -> Any | None:
    """Run best-effort enrichment without treating its own timeout as deadline exhaustion."""
    try:
        return await _await_with_run_budget(
            awaitable,
            run_budget=run_budget,
            requested_timeout=requested_timeout,
            operation=operation,
        )
    except RunBudgetExceeded:
        if run_budget is None or run_budget.usable_seconds() < 30.0:
            raise
        log("warning", f"  {operation} timed out; {continuation}")
        return None


def _candidate_name(candidate: Any) -> str:
    return roster.candidate_name(candidate)


def _pipeline_completed_units(race_json: Dict[str, Any]) -> set[str]:
    return phase_state.completed_units(race_json)


def _mark_pipeline_unit_complete(race_json: Dict[str, Any], unit: str) -> None:
    phase_state.mark_unit_complete(race_json, unit)


def _issue_stance_is_complete(value: Any) -> bool:
    """True for a substantive stance or a terminal no-position verdict.

    Literal placeholders remain incomplete so a continuation retries them.
    """
    return phase_state.issue_stance_is_complete(value)


def _pipeline_issue_attempts(race_json: Dict[str, Any]) -> Dict[str, int]:
    return phase_state.issue_attempts(race_json)


def _build_handoff_context(
    handoffs: List[Dict[str, Any]],
    cached_info: Dict[str, Any] | None,
) -> str:
    """Build a handoff context string for the issue sub-agent."""
    return phase_state.build_handoff_context(handoffs, cached_info)


def _race_identity_context(race_json: Dict[str, Any]) -> str:
    """Render the locked race-identity brief for downstream prompt injection."""
    return phase_state.race_identity_context(race_json)
