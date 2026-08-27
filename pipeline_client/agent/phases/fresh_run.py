"""Fresh run (new race): Discovery -> Issue research -> Refinement -> ..."""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.race_titles import apply_canonical_race_title

from ..llm import _ensure_dict
from ..prompts import DISCOVERY_SYSTEM, DISCOVERY_USER, cycle_kwargs
from ..run_budget import RunBudget
from ..selection import _scale_iterations, _select_target_candidates
from ..utils import make_logger
from ._common import _await_advisory_with_run_budget, _candidate_name
from .context import PhaseContext
from .discovery import _sanitize_roster
from .shared_runner import _run_shared_phases


async def _run_fresh(
    race_id: str,
    *,
    model: str,
    small_model: str,
    image_vision_model: str = "",
    roster_model: str | None = None,
    on_log: Any | None = None,
    max_iterations: int = 15,
    step_enabled: Any = None,
    track: Any = None,
    max_candidates: Optional[int] = None,
    target_no_info: bool = False,
    target_candidate_names: Optional[List[str]] = None,
    goal: Optional[str] = None,
    resume_partial: bool = False,
    continue_incomplete_work: bool = False,
    run_budget: RunBudget | None = None,
) -> Dict[str, Any]:
    """Phase 1 → 2 → 3: Discovery → Issue research → Refinement."""
    from . import _agent_loop, _sync_ballotpedia_roster

    log = make_logger(on_log)
    if step_enabled is None:
        step_enabled = lambda s: True
    if track is None:
        track = lambda a, s, **kw: None

    # --- Phase 1: Discovery ---
    track("start", "discovery")
    disc_t0 = time.perf_counter()
    log("info", "Phase 1/3: Discovering race and candidates...")
    race_json = _ensure_dict(
        await _agent_loop(
            DISCOVERY_SYSTEM,
            (f"## Run Goal\n{goal}\n\n" if goal else "")
            + DISCOVERY_USER.format(
                **cycle_kwargs(race_id),
                race_id=race_id,
                current_date=datetime.now(timezone.utc).date().isoformat(),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
            phase_name="discovery",
            max_tokens=16384,
            run_budget=run_budget,
        ),
        "discovery",
        log,
    )
    _sanitize_roster(race_json, log)
    apply_canonical_race_title(race_json, race_id)
    await _await_advisory_with_run_budget(
        _sync_ballotpedia_roster(race_json, race_id, log),
        run_budget=run_budget,
        requested_timeout=20.0,
        operation="Ballotpedia advisory roster lookup",
        log=log,
        continuation="continuing with discovered roster",
    )
    _sanitize_roster(race_json, log)

    candidate_names = [_candidate_name(c) for c in race_json.get("candidates", []) if _candidate_name(c)]
    candidate_names = _select_target_candidates(candidate_names, target_candidate_names, log)
    selected_name_set = set(candidate_names)
    n = len(candidate_names)
    if not candidate_names:
        log("warning", "No candidates found in discovery phase")
        track("complete", "discovery", duration_ms=int((time.perf_counter() - disc_t0) * 1000), race_json=race_json)
        return race_json

    refine_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=12)
    log("info", f"  Iteration budgets — refine:{refine_iters}  (n={n} candidates)")
    track("complete", "discovery", duration_ms=int((time.perf_counter() - disc_t0) * 1000), race_json=race_json)

    await _run_shared_phases(
        PhaseContext(
            race_json=race_json,
            race_id=race_id,
            model=model,
            small_model=small_model,
            image_vision_model=image_vision_model,
            on_log=on_log,
            log=log,
            max_iterations=max_iterations,
            step_enabled=step_enabled,
            track=track,
            run_budget=run_budget,
            is_update=False,
            candidate_names=candidate_names,
            selected_name_set=selected_name_set,
            last_updated="",
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            refine_iters=refine_iters,
            resume_partial=resume_partial,
            continue_incomplete_work=continue_incomplete_work,
        )
    )
    _sanitize_roster(race_json, log)
    apply_canonical_race_title(race_json, race_id)

    return race_json
