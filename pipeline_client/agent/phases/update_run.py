"""Update run (existing race): roster sync -> meta update -> shared phases."""

import copy
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..handlers import _make_editing_handlers
from ..model_registry import NEMOTRON_ULTRA_MODEL
from ..prompts import (
    ROSTER_SYNC_SYSTEM,
    ROSTER_SYNC_USER,
    ROSTER_VERIFY_SYSTEM,
    ROSTER_VERIFY_USER,
    UPDATE_META_SYSTEM,
    UPDATE_META_USER,
)
from ..run_budget import RunBudget, RunBudgetExceeded
from ..selection import _scale_iterations, _select_target_candidates
from ..tools import CANDIDATE_TOOLS, DESCRIPTION_TOOLS, READ_PROFILE_TOOL, RECORD_TOOLS, REMOVE_CANDIDATE_TOOL, ROSTER_TOOLS
from ..utils import make_logger
from ._common import (
    RunFailureReason,
    _await_with_run_budget,
    _candidate_name,
    _mark_pipeline_unit_complete,
    _pipeline_completed_units,
    _record_step_failure,
)
from .discovery import _backfill_source_timestamps, _sanitize_roster
from .fresh_run import _run_fresh
from .shared_runner import _run_shared_phases


async def _run_update(
    race_id: str,
    existing: Dict[str, Any],
    *,
    model: str,
    small_model: str,
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
    """Phase-based update mirroring _run_fresh but starting from existing data."""
    from . import _agent_loop, _sync_ballotpedia_roster

    log = make_logger(on_log)
    if step_enabled is None:
        step_enabled = lambda s: True
    if track is None:
        track = lambda a, s, **kw: None

    race_json: Dict[str, Any] = copy.deepcopy(existing)
    _backfill_source_timestamps(race_json)
    _sanitize_roster(race_json, log)
    await _await_with_run_budget(
        _sync_ballotpedia_roster(race_json, race_id, log),
        run_budget=run_budget,
        requested_timeout=20.0,
        operation="Ballotpedia roster sync",
    )
    _sanitize_roster(race_json, log)

    existing_candidates = race_json.get("candidates", [])
    candidate_names = [_candidate_name(c) for c in existing_candidates if _candidate_name(c)]
    candidate_names = _select_target_candidates(candidate_names, target_candidate_names, log)
    selected_name_set = set(candidate_names)
    n = len(candidate_names)
    last_updated = existing.get("updated_utc", "unknown")

    if not candidate_names:
        log("warning", "No candidates in existing data — falling back to fresh run")
        return await _run_fresh(
            race_id,
            model=model,
            small_model=small_model,
            roster_model=roster_model,
            on_log=on_log,
            max_iterations=max_iterations,
            step_enabled=step_enabled,
            track=track,
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            target_candidate_names=target_candidate_names,
            resume_partial=resume_partial,
            continue_incomplete_work=continue_incomplete_work,
            run_budget=run_budget,
        )

    refine_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=12)
    handlers = _make_editing_handlers(race_json, log)

    # --- Phase 0+1: Discovery (roster sync + meta update) ---
    if step_enabled("discovery"):
        track("start", "discovery")
        disc_t0 = time.perf_counter()
        as_of_date = datetime.now(timezone.utc).date().isoformat()
        completed_units = _pipeline_completed_units(race_json)
        if not resume_partial:
            completed_units.difference_update({"discovery.roster_sync", "discovery.roster_verify", "discovery.metadata"})
            race_json["pipeline_state"]["completed_units"] = sorted(completed_units)

        pre_sync_names = list(candidate_names)
        if "discovery.roster_sync" not in completed_units:
            log("info", "Update Phase 0: Verifying candidate roster...")
            try:
                await _agent_loop(
                    ROSTER_SYNC_SYSTEM,
                    ROSTER_SYNC_USER.format(
                        race_id=race_id,
                        last_updated=last_updated,
                        current_date=as_of_date,
                        candidate_names=", ".join(candidate_names),
                        race_description=race_json.get("description", ""),
                    ),
                    model=roster_model or model,
                    on_log=on_log,
                    race_id=race_id,
                    max_iterations=min(max_iterations, 12),
                    phase_name="roster-sync",
                    max_tokens=8192,
                    extra_tools=ROSTER_TOOLS + [READ_PROFILE_TOOL],
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                    tool_error_escalation_model=NEMOTRON_ULTRA_MODEL,
                )
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Roster sync failed: {exc} — keeping existing roster")
                _record_step_failure(race_json, "discovery", RunFailureReason.ROSTER_VERIFICATION_FAILED, str(exc))

            _sanitize_roster(race_json, log)
            await _await_with_run_budget(
                _sync_ballotpedia_roster(race_json, race_id, log),
                run_budget=run_budget,
                requested_timeout=20.0,
                operation="Ballotpedia roster sync",
            )
            _sanitize_roster(race_json, log)
            _mark_pipeline_unit_complete(race_json, "discovery.roster_sync")
            completed_units.add("discovery.roster_sync")
            track(
                "progress",
                "discovery",
                pct=30,
                message="Discovery: roster sync complete",
                race_json=race_json,
            )
        else:
            log("info", "Update Phase 0: Roster sync restored from checkpoint")

        # Roster verify uses the primary model to re-check inactive/non-general
        # candidates after roster-sync edits.
        post_sync_names = [_candidate_name(c) for c in race_json.get("candidates", []) if _candidate_name(c)]
        if "discovery.roster_verify" not in completed_units:
            log("info", f"  Roster verify: checking {len(post_sync_names)} candidate(s)")
            try:
                await _agent_loop(
                    ROSTER_VERIFY_SYSTEM,
                    ROSTER_VERIFY_USER.format(
                        race_id=race_id,
                        current_date=as_of_date,
                        candidate_names=", ".join(post_sync_names),
                        original_names=", ".join(pre_sync_names),
                        added_names=", ".join(post_sync_names),
                    ),
                    model=roster_model or model,
                    on_log=on_log,
                    race_id=race_id,
                    max_iterations=8,
                    phase_name="roster-verify",
                    max_tokens=4096,
                    extra_tools=[REMOVE_CANDIDATE_TOOL, READ_PROFILE_TOOL],
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                )
                _sanitize_roster(race_json, log)
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Roster verify failed: {exc} — keeping post-sync roster")
                _record_step_failure(race_json, "discovery", RunFailureReason.ROSTER_VERIFICATION_FAILED, str(exc))
            _mark_pipeline_unit_complete(race_json, "discovery.roster_verify")
            completed_units.add("discovery.roster_verify")
            track(
                "progress",
                "discovery",
                pct=50,
                message="Discovery: roster verification complete",
                race_json=race_json,
            )
        else:
            log("info", "  Roster verify restored from checkpoint")

        candidate_names = [_candidate_name(c) for c in race_json.get("candidates", []) if _candidate_name(c)]
        candidate_names = _select_target_candidates(candidate_names, target_candidate_names, log)
        selected_name_set = set(candidate_names)
        n = len(candidate_names)

        if not candidate_names:
            log("warning", "No candidates after roster sync — falling back to fresh run")
            track("skip", "discovery")
            return await _run_fresh(
                race_id,
                model=model,
                small_model=small_model,
                on_log=on_log,
                max_iterations=max_iterations,
                step_enabled=step_enabled,
                track=track,
                max_candidates=max_candidates,
                target_no_info=target_no_info,
                target_candidate_names=target_candidate_names,
                resume_partial=resume_partial,
                continue_incomplete_work=continue_incomplete_work,
                run_budget=run_budget,
            )

        if "discovery.metadata" not in completed_units:
            track("progress", "discovery", pct=55, message="Discovery: updating race metadata", race_json=race_json)

            # Metadata refresh is one broad race task. Candidate count must not
            # multiply its loop budget; candidate-specific work has later phases.
            meta_iters = min(max_iterations, 12)
            log("info", "Update Phase 1: Searching for new summaries, race developments, and voting records...")
            try:
                await _agent_loop(
                    UPDATE_META_SYSTEM,
                    UPDATE_META_USER.format(
                        race_id=race_id,
                        last_updated=last_updated,
                        current_date=as_of_date,
                        candidate_names=", ".join(candidate_names),
                    ),
                    model=model,
                    on_log=on_log,
                    race_id=race_id,
                    max_iterations=meta_iters,
                    phase_name="update-meta",
                    max_tokens=16384,
                    extra_tools=DESCRIPTION_TOOLS + CANDIDATE_TOOLS + RECORD_TOOLS + [READ_PROFILE_TOOL],
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                )
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Update meta phase failed: {exc} — keeping existing meta")
            _mark_pipeline_unit_complete(race_json, "discovery.metadata")
        else:
            log("info", "Update Phase 1: Metadata refresh restored from checkpoint")

        track("complete", "discovery", duration_ms=int((time.perf_counter() - disc_t0) * 1000), race_json=race_json)
    else:
        log("info", "Update Phase 0+1: Discovery — SKIPPED")
        track("skip", "discovery")
        _sanitize_roster(race_json, log)
        candidate_names = [_candidate_name(c) for c in race_json.get("candidates", []) if _candidate_name(c)]
        candidate_names = _select_target_candidates(candidate_names, target_candidate_names, log)
        selected_name_set = set(candidate_names)
        n = len(candidate_names)

    await _run_shared_phases(
        race_json,
        race_id,
        candidate_names=candidate_names,
        selected_name_set=selected_name_set,
        model=model,
        small_model=small_model,
        on_log=on_log,
        max_iterations=max_iterations,
        step_enabled=step_enabled,
        track=track,
        max_candidates=max_candidates,
        target_no_info=target_no_info,
        is_update=True,
        last_updated=last_updated,
        refine_iters=refine_iters,
        log=log,
        resume_partial=resume_partial,
        continue_incomplete_work=continue_incomplete_work,
        run_budget=run_budget,
    )
    _sanitize_roster(race_json, log)

    return race_json
