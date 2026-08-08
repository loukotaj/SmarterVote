"""Phase 2b: dedicated donor & voting-record research."""

import time
from typing import Any, Dict, List

from ..patches import _apply_finance_patch  # noqa: F401 — re-exported for backward compat
from ..prompts import FINANCE_VOTING_SYSTEM, FINANCE_VOTING_USER, cycle_kwargs
from ..run_budget import RunBudget, RunBudgetExceeded
from ..selection import _scale_iterations
from ._common import (
    RunFailureReason,
    _classify_exception,
    _detect_empty_finance_output,
    _race_identity_context,
    _record_step_failure,
)
from .context import PhaseContext


async def run_finance_phase(ctx: PhaseContext) -> None:
    """Research donors & voting records for all candidates in one pass."""
    race_json = ctx.race_json
    race_id = ctx.race_id
    candidate_names = ctx.candidate_names
    model = ctx.model
    on_log = ctx.on_log
    max_iterations = ctx.max_iterations
    step_enabled = ctx.step_enabled
    track = ctx.track
    is_update = ctx.is_update
    log = ctx.log
    prefix = ctx.prefix
    run_budget = ctx.run_budget
    from . import _agent_loop

    if not step_enabled("finance"):
        log("info", f"{prefix} 2b: Finance & voting — SKIPPED")
        track("skip", "finance")
        return

    track("start", "finance")
    fin_t0 = time.perf_counter()
    n = len(candidate_names)
    finance_iters = _scale_iterations(max_iterations, n, per_candidate=4, minimum=15)
    log("info", f"{prefix} 2b: Researching donors & voting records for {n} candidates...")
    try:
        finance_result = await _agent_loop(
            FINANCE_VOTING_SYSTEM,
            FINANCE_VOTING_USER.format(
                **cycle_kwargs(race_id),
                race_id=race_id,
                candidate_names=", ".join(candidate_names),
                race_identity_context=_race_identity_context(race_json),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=finance_iters,
            phase_name=f"{'update-' if is_update else ''}finance-voting",
            max_tokens=16384,
            run_budget=run_budget,
        )
        if isinstance(finance_result, dict):
            _apply_finance_patch(race_json, finance_result, log)
        else:
            log("warning", "  Finance/voting phase returned non-dict — skipping")
            _record_step_failure(
                race_json, "finance", RunFailureReason.STEP_NO_DATA, "finance phase returned a non-dict response"
            )
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  Finance/voting phase failed: {exc} — continuing without")
        _record_step_failure(race_json, "finance", _classify_exception(exc), str(exc))
    if _detect_empty_finance_output(race_json, candidate_names):
        # The step ran (or was attempted) without a hard error, but every
        # target candidate still has no donor_summary/voting_summary — the
        # silent-failure pattern this exists to catch (CLAUDE.md rule 7).
        log("warning", "  Finance/voting phase produced no donor/voting data for any candidate")
        _record_step_failure(
            race_json,
            "finance",
            RunFailureReason.STEP_NO_DATA,
            "no candidate has donor_summary or voting_summary after the finance step",
        )
    track("complete", "finance", duration_ms=int((time.perf_counter() - fin_t0) * 1000), race_json=race_json)
