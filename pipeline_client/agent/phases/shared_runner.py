"""Shared phase runner — images -> issues -> finance -> refinement -> polling ->
forecast -> voter_resources.

This is the sequence common to both a fresh discovery run (``fresh_run.py``)
and an update run (``update_run.py``); each phase's implementation lives in
its own module and is invoked here in order.
"""

from typing import Any, Dict, List, Optional

from ..run_budget import RunBudget
from .finance import run_finance_phase
from .forecast import run_forecast_phase
from .image_resolution import run_image_resolution_phase
from .issues import run_issues_phase
from .polling import run_polling_phase
from .refinement import run_refinement_phase
from .voter_resources import run_voter_resources_phase


async def _run_shared_phases(
    race_json: Dict[str, Any],
    race_id: str,
    *,
    candidate_names: List[str],
    selected_name_set: set,
    model: str,
    small_model: str,
    on_log: Any,
    max_iterations: int,
    step_enabled: Any,
    track: Any,
    max_candidates: Optional[int],
    target_no_info: bool,
    is_update: bool,
    last_updated: str,
    refine_iters: int,
    log: Any,
    resume_partial: bool = False,
    continue_incomplete_work: bool = False,
    run_budget: RunBudget | None = None,
) -> None:
    """Run candidate research, polling, and voter-resource phases.

    Mutates *race_json* in place.
    """
    prefix = "Update Phase" if is_update else "Phase"

    # --- Phase 1b: Image URL verification & resolution (parallel) ---
    await run_image_resolution_phase(
        race_json,
        race_id,
        selected_name_set=selected_name_set,
        small_model=small_model,
        on_log=on_log,
        max_iterations=max_iterations,
        step_enabled=step_enabled,
        track=track,
        log=log,
        prefix=prefix,
        run_budget=run_budget,
    )

    # --- Phase 2: Per-candidate, per-issue research (tools mode) ---
    await run_issues_phase(
        race_json,
        race_id,
        candidate_names=candidate_names,
        small_model=small_model,
        on_log=on_log,
        max_iterations=max_iterations,
        step_enabled=step_enabled,
        track=track,
        max_candidates=max_candidates,
        target_no_info=target_no_info,
        is_update=is_update,
        last_updated=last_updated,
        log=log,
        prefix=prefix,
        resume_partial=resume_partial,
        continue_incomplete_work=continue_incomplete_work,
        run_budget=run_budget,
    )

    # --- Phase 2b: Dedicated finance & voting record research ---
    await run_finance_phase(
        race_json,
        race_id,
        candidate_names=candidate_names,
        model=model,
        on_log=on_log,
        max_iterations=max_iterations,
        step_enabled=step_enabled,
        track=track,
        is_update=is_update,
        log=log,
        prefix=prefix,
        run_budget=run_budget,
    )

    # --- Phase 3: Refinement (tools mode — per-candidate + meta) ---
    await run_refinement_phase(
        race_json,
        race_id,
        selected_name_set=selected_name_set,
        model=model,
        on_log=on_log,
        max_iterations=max_iterations,
        step_enabled=step_enabled,
        track=track,
        is_update=is_update,
        refine_iters=refine_iters,
        log=log,
        prefix=prefix,
        resume_partial=resume_partial,
        run_budget=run_budget,
    )

    # --- Phase 4: Polling refresh ---
    await run_polling_phase(
        race_json,
        race_id,
        candidate_names=candidate_names,
        small_model=small_model,
        on_log=on_log,
        max_iterations=max_iterations,
        step_enabled=step_enabled,
        track=track,
        is_update=is_update,
        log=log,
        prefix=prefix,
        run_budget=run_budget,
    )

    # --- Phase 4b: Forecast generation ---
    await run_forecast_phase(
        race_json,
        race_id,
        model=model,
        on_log=on_log,
        max_iterations=max_iterations,
        step_enabled=step_enabled,
        track=track,
        is_update=is_update,
        log=log,
        prefix=prefix,
        run_budget=run_budget,
    )

    # --- Phase 5: Voter resources verification ---
    await run_voter_resources_phase(
        race_json,
        race_id,
        small_model=small_model,
        on_log=on_log,
        max_iterations=max_iterations,
        step_enabled=step_enabled,
        track=track,
        is_update=is_update,
        log=log,
        prefix=prefix,
        run_budget=run_budget,
    )
