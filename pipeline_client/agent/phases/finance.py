"""Phase 2b: dedicated donor & voting-record research."""

import time
from typing import Any, Dict, List

from ..patches import _apply_finance_patch  # noqa: F401 — re-exported for backward compat
from ..prompts import FINANCE_VOTING_SYSTEM, FINANCE_VOTING_USER
from ..run_budget import RunBudget, RunBudgetExceeded
from ..selection import _scale_iterations


async def run_finance_phase(
    race_json: Dict[str, Any],
    race_id: str,
    *,
    candidate_names: List[str],
    model: str,
    on_log: Any,
    max_iterations: int,
    step_enabled: Any,
    track: Any,
    is_update: bool,
    log: Any,
    prefix: str,
    run_budget: RunBudget | None,
) -> None:
    """Research donors & voting records for all candidates in one pass."""
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
                race_id=race_id,
                candidate_names=", ".join(candidate_names),
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
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  Finance/voting phase failed: {exc} — continuing without")
    track("complete", "finance", duration_ms=int((time.perf_counter() - fin_t0) * 1000), race_json=race_json)
