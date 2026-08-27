"""Update run (existing race): roster sync -> meta update -> shared phases."""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.pipeline_config import FreshnessConfig
from shared.race_titles import apply_canonical_race_title

from ..handlers import _make_editing_handlers
from ..prompts import (
    ROSTER_SYNC_SYSTEM,
    ROSTER_SYNC_USER,
    ROSTER_VERIFY_SYSTEM,
    ROSTER_VERIFY_USER,
    UPDATE_META_SYSTEM,
    UPDATE_META_USER,
    cycle_kwargs,
)
from ..roster_adjudicator import format_contest_label
from ..run_budget import RunBudget, RunBudgetExceeded
from ..selection import _scale_iterations, _select_target_candidates
from ..tools import (
    CANDIDATE_TOOLS,
    DESCRIPTION_TOOLS,
    FINALIZE_METADATA_TOOL,
    FINALIZE_ROSTER_TOOL,
    READ_PROFILE_TOOL,
    RECORD_TOOLS,
    REMOVE_CANDIDATE_TOOL,
    ROSTER_TOOLS,
    SET_RACE_IDENTITY_TOOL,
)
from ..utils import make_logger
from ._common import (
    RunFailureReason,
    _await_advisory_with_run_budget,
    _candidate_name,
    _mark_pipeline_unit_complete,
    _pipeline_completed_units,
    _record_step_failure,
)
from .context import PhaseContext
from .discovery import _backfill_source_timestamps, _record_provisional_roster, _sanitize_roster
from .fresh_run import _run_fresh
from .shared_runner import _run_shared_phases

_ROSTER_UNITS = {"discovery.roster_sync", "discovery.roster_verify"}
_DISCOVERY_UNITS = _ROSTER_UNITS | {"discovery.metadata"}
_FAST_NO_CHANGE_INSTRUCTION = (
    "\n\nFAST MAINTENANCE PATH: Begin with exactly one broad, current web_search for material changes to this exact "
    "race. If that search shows the stored roster and facts still look correct, call finish_no_changes with a "
    "result URL and stop. If it reveals a change, uncertainty, a stage transition, or a missing candidate, do not "
    "use the fast path; continue the normal evidence and editing workflow."
)


def _audit_age_seconds(value: Any, *, now: datetime | None = None) -> float | None:
    try:
        finalized_at = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if finalized_at.tzinfo is None:
        finalized_at = finalized_at.replace(tzinfo=timezone.utc)
    age_seconds = ((now or datetime.now(timezone.utc)) - finalized_at).total_seconds()
    return age_seconds if age_seconds >= 0 else None


def _fast_probe_baseline_reason(
    race_json: Dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> str | None:
    """Explain why a prior finalized roster is safe input to a fast probe.

    This only permits a current one-search change check; it never skips work
    from age alone.
    """
    stage = str(race_json.get("contest_stage") or "unknown").strip().lower()
    if stage == "unknown":
        return None
    pipeline_state = race_json.get("pipeline_state")
    if not isinstance(pipeline_state, dict) or pipeline_state.get("roster_finalization_pending") is True:
        return None
    audit = pipeline_state.get("roster_research")
    if not isinstance(audit, dict) or audit.get("completeness_status") == "unproven":
        return None
    if str(audit.get("contest_stage") or "unknown").strip().lower() != stage:
        return None
    candidates = [candidate for candidate in race_json.get("candidates") or [] if isinstance(candidate, dict)]
    try:
        audited_candidate_count = int(audit.get("active_candidate_count") or 0)
    except (TypeError, ValueError):
        return None
    if not candidates or audited_candidate_count != len(candidates):
        return None
    current_names = {str(candidate.get("name") or "").strip().casefold() for candidate in candidates}
    audited_names = {str(name).strip().casefold() for name in audit.get("candidate_names") or []}
    if not current_names or audited_names != current_names:
        return None
    if not any(isinstance(source, dict) and source.get("url") for source in audit.get("completeness_sources") or []):
        return None
    run_health = race_json.get("run_health")
    reasons = run_health.get("reasons") if isinstance(run_health, dict) else []
    if "roster_completeness_unproven" in {str(reason) for reason in reasons or []}:
        return None
    allowed_days = FreshnessConfig.from_env().refresh_probe_max_baseline_days if max_age_days is None else max(1, max_age_days)
    age_seconds = _audit_age_seconds(audit.get("finalized_at"), now=now)
    if age_seconds is None or age_seconds > allowed_days * 86400:
        return None
    return f"evidence-backed baseline finalized {int(age_seconds // 86400)}d ago at contest_stage={stage}"


def _metadata_fast_probe_allowed(
    race_json: Dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> bool:
    """Require a complete prior metadata finalization before probing for no change."""
    candidates = [candidate for candidate in race_json.get("candidates") or [] if isinstance(candidate, dict)]
    state = race_json.get("pipeline_state")
    audit = state.get("metadata_research") if isinstance(state, dict) else None
    if not candidates or not isinstance(audit, dict):
        return False
    try:
        if int(audit.get("active_candidate_count") or 0) != len(candidates):
            return False
    except (TypeError, ValueError):
        return False
    allowed_days = FreshnessConfig.from_env().refresh_probe_max_baseline_days if max_age_days is None else max(1, max_age_days)
    age_seconds = _audit_age_seconds(audit.get("finalized_at"), now=now)
    if age_seconds is None or age_seconds > allowed_days * 86400:
        return False
    source_names = {str(name).strip().casefold() for name in (audit.get("candidate_sources") or {})}
    candidate_names = {str(candidate.get("name") or "").strip().casefold() for candidate in candidates}
    return bool(audit.get("description_sources")) and source_names == candidate_names


def _clear_recovered_roster_verification_failure(race_json: Dict[str, Any]) -> None:
    """Remove an initial roster-sync error after strict recovery succeeds."""
    pipeline_state = race_json.get("pipeline_state")
    if not isinstance(pipeline_state, dict):
        return
    failures = pipeline_state.get("step_failures")
    if not isinstance(failures, list):
        return
    pipeline_state["step_failures"] = [
        failure
        for failure in failures
        if not (
            isinstance(failure, dict)
            and failure.get("step") == "discovery"
            and failure.get("reason") == RunFailureReason.ROSTER_VERIFICATION_FAILED.value
        )
    ]


async def _run_update(
    race_id: str,
    existing: Dict[str, Any],
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
    allow_fast_no_change: bool = False,
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

    # Keep the handler's checkpoint holder on this same object. A deepcopy here
    # meant a timeout before the first progress callback checkpointed the
    # untouched baseline; its old completed-unit markers then made the
    # continuation skip discovery and report a false zero-cost success.
    race_json: Dict[str, Any] = existing
    _backfill_source_timestamps(race_json)
    _sanitize_roster(race_json, log)
    fast_probe_reason = _fast_probe_baseline_reason(race_json) if allow_fast_no_change and not resume_partial else None
    await _await_advisory_with_run_budget(
        _sync_ballotpedia_roster(race_json, race_id, log),
        run_budget=run_budget,
        requested_timeout=20.0,
        operation="Ballotpedia advisory roster lookup",
        log=log,
        continuation="continuing with roster research",
    )
    _sanitize_roster(race_json, log)

    existing_candidates = race_json.get("candidates", [])
    all_candidate_names = [_candidate_name(c) for c in existing_candidates if _candidate_name(c)]
    candidate_names = list(all_candidate_names)
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
            image_vision_model=image_vision_model,
            roster_model=roster_model,
            on_log=on_log,
            max_iterations=max_iterations,
            step_enabled=step_enabled,
            track=track,
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            target_candidate_names=target_candidate_names,
            goal=goal,
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
            skipped_units = set(race_json["pipeline_state"].get("skipped_units") or [])
            skipped_units.difference_update(_DISCOVERY_UNITS)
            race_json["pipeline_state"]["completed_units"] = sorted(completed_units)
            race_json["pipeline_state"]["skipped_units"] = sorted(skipped_units)
            race_json["pipeline_state"].pop("roster_finalization_pending", None)
            race_json["pipeline_state"].pop("roster_sync_original_names", None)

        stored_original_names = race_json["pipeline_state"].get("roster_sync_original_names")
        pre_sync_names = (
            [str(name) for name in stored_original_names if str(name).strip()]
            if isinstance(stored_original_names, list)
            else list(all_candidate_names)
        )
        if "discovery.roster_verify" not in completed_units:
            race_json["pipeline_state"]["roster_sync_original_names"] = list(pre_sync_names)
        else:
            race_json["pipeline_state"].pop("roster_sync_original_names", None)
        # This survives a continuation between roster-sync and roster-verify.
        # The recovery decision is pipeline state, never wording in a queue goal.
        roster_sync_succeeded: bool | None = (
            False if race_json["pipeline_state"].get("roster_finalization_pending") is True else None
        )
        roster_no_change_confirmed = False
        if "discovery.roster_sync" not in completed_units:
            log("info", "Update Phase 0: Verifying candidate roster...")
            roster_sync_succeeded = False
            try:
                roster_result = await _agent_loop(
                    ROSTER_SYNC_SYSTEM,
                    (f"## Run Goal\n{goal}\n\n" if goal else "")
                    + ROSTER_SYNC_USER.format(
                        **cycle_kwargs(race_id),
                        race_id=race_id,
                        last_updated=last_updated,
                        current_date=as_of_date,
                        candidate_names=", ".join(candidate_names),
                        race_description=race_json.get("description", ""),
                    )
                    + (_FAST_NO_CHANGE_INSTRUCTION if fast_probe_reason else ""),
                    model=roster_model or model,
                    on_log=on_log,
                    race_id=race_id,
                    contest_label=format_contest_label(race_json, race_id),
                    # Roster sync spends iterations per candidate: identity, a
                    # fetch or two, one set_candidate_roster_sources per name,
                    # then finalize. Twelve ran out mid-roster on a three-way
                    # race and the run failed having already gathered the
                    # evidence it needed, so scale the ceiling with the roster.
                    max_iterations=min(max_iterations, max(12, 8 + 2 * len(candidate_names))),
                    phase_name="roster-sync",
                    max_tokens=8192,
                    extra_tools=ROSTER_TOOLS + [READ_PROFILE_TOOL],
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                    escalate_on_tool_errors=True,
                    required_final_tool_name="finalize_roster",
                    required_final_instruction=(
                        "Do not stop yet. Finish the authoritative exact-contest roster, ensure every active "
                        "candidate has durable qualifying roster_sources, and provide retrieved completeness_sources "
                        "that quote the full qualified/certified/ballot list (including the exact date for a special "
                        "election). Call finalize_roster once with the entire final candidates array and the exact "
                        "source_candidate_names; it atomically applies all remaining roster edits."
                    ),
                    return_tool_trace=True,
                    allow_no_change_after_search=bool(fast_probe_reason),
                )
                roster_trace = roster_result.get("_tool_trace") or {}
                roster_no_change_confirmed = bool(roster_trace.get("no_change_confirmed"))
                roster_sync_succeeded = bool(roster_trace.get("required_final_tool_succeeded") or roster_no_change_confirmed)
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Roster sync failed: {exc} — keeping existing roster")
                _record_step_failure(race_json, "discovery", RunFailureReason.ROSTER_VERIFICATION_FAILED, str(exc))

            _sanitize_roster(race_json, log)
            if roster_sync_succeeded:
                race_json["pipeline_state"].pop("roster_finalization_pending", None)
            else:
                race_json["pipeline_state"]["roster_finalization_pending"] = True
            if roster_no_change_confirmed:
                completed_units.add("discovery.roster_verify")
                _mark_pipeline_unit_complete(race_json, "discovery.roster_verify")
                skipped_units = set(race_json["pipeline_state"].get("skipped_units") or [])
                skipped_units.update(_ROSTER_UNITS)
                race_json["pipeline_state"]["skipped_units"] = sorted(skipped_units)
                log("info", f"Discovery roster fast path accepted: {fast_probe_reason}")
            else:
                await _await_advisory_with_run_budget(
                    _sync_ballotpedia_roster(race_json, race_id, log),
                    run_budget=run_budget,
                    requested_timeout=20.0,
                    operation="Ballotpedia advisory roster lookup",
                    log=log,
                    continuation="continuing with roster verification",
                )
                _sanitize_roster(race_json, log)
            if not roster_sync_succeeded:
                # Completeness could not be proven — routinely because no
                # qualified-candidate list exists yet for a pre-primary contest.
                # Bailing out here used to skip images, polling, forecast and
                # voter resources too, so the race stayed stale AND said nothing
                # about why. Keep the per-candidate-evidenced roster we hold,
                # say plainly that it may be incomplete, point at the sources we
                # did find, and let the rest of the refresh run.
                # Deliberately does NOT re-queue discovery in remaining_steps.
                # Discovery ran, reached a defensible conclusion, and recorded it;
                # "still to do" would be a lie about what happened. Leaving it
                # there also made the race unpublishable — the publish gate allows
                # a pending `review` but nothing else, so fl-house-10-2026 (a
                # decided, uncontested race whose roster is correct) was blocked
                # by bookkeeping rather than by any doubt about its data. The
                # provisional status is recorded below on roster_research and as a
                # step failure, and every refresh re-runs discovery anyway.
                track(
                    "progress",
                    "discovery",
                    pct=30,
                    message="Discovery: roster kept as provisional (complete field unconfirmed)",
                    race_json=race_json,
                )
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
                recover_completeness = roster_sync_succeeded is False
                pre_sync_keys = {name.casefold() for name in pre_sync_names}
                added_names = [name for name in post_sync_names if name.casefold() not in pre_sync_keys]
                finalization_instruction = (
                    "The earlier roster-sync phase did not prove completeness. After removing any verified "
                    "inactive candidates, fetch an authoritative exact-contest source or the exact Ballotpedia "
                    "race page that names the entire current field. Call set_race_identity with the verified "
                    "office and current contest stage before finalization. Then you MUST call finalize_roster with the "
                    "remaining complete candidates array, matching source_candidate_names, and the retrieved "
                    "completeness source. Do not finalize from search snippets or candidate-by-candidate sources."
                    if recover_completeness
                    else "Roster completeness was already finalized. Do not call finalize_roster again."
                )
                verify_result = await _agent_loop(
                    ROSTER_VERIFY_SYSTEM.format(**cycle_kwargs(race_id)),
                    ROSTER_VERIFY_USER.format(
                        **cycle_kwargs(race_id),
                        race_id=race_id,
                        current_date=as_of_date,
                        candidate_names=", ".join(post_sync_names),
                        original_names=", ".join(pre_sync_names),
                        added_names=", ".join(added_names) or "(none)",
                        finalization_instruction=finalization_instruction,
                    ),
                    model=roster_model or model,
                    on_log=on_log,
                    race_id=race_id,
                    contest_label=format_contest_label(race_json, race_id),
                    max_iterations=(min(max_iterations, max(10, 6 + len(post_sync_names))) if recover_completeness else 8),
                    phase_name="roster-verify",
                    max_tokens=4096,
                    extra_tools=[REMOVE_CANDIDATE_TOOL, READ_PROFILE_TOOL]
                    + ([SET_RACE_IDENTITY_TOOL, FINALIZE_ROSTER_TOOL] if recover_completeness else []),
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                    required_final_tool_name="finalize_roster" if recover_completeness else None,
                    required_final_instruction=finalization_instruction if recover_completeness else None,
                    return_tool_trace=recover_completeness,
                )
                if recover_completeness:
                    roster_sync_succeeded = bool((verify_result.get("_tool_trace") or {}).get("required_final_tool_succeeded"))
                    if roster_sync_succeeded:
                        race_json["pipeline_state"].pop("roster_finalization_pending", None)
                        _clear_recovered_roster_verification_failure(race_json)
                _sanitize_roster(race_json, log)
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Roster verify failed: {exc} — keeping post-sync roster")
                _record_step_failure(race_json, "discovery", RunFailureReason.ROSTER_VERIFICATION_FAILED, str(exc))
            _mark_pipeline_unit_complete(race_json, "discovery.roster_verify")
            completed_units.add("discovery.roster_verify")
            race_json["pipeline_state"].pop("roster_sync_original_names", None)
            track(
                "progress",
                "discovery",
                pct=50,
                message="Discovery: roster verification complete",
                race_json=race_json,
            )
        else:
            log("info", "  Roster verify restored from checkpoint")

        if roster_sync_succeeded is False:
            # Roster verification can remove stale or ineligible candidates, so
            # finalize the provisional audit only after that phase has settled
            # the active roster and its count.
            race_json.setdefault("pipeline_state", {})["complete"] = False
            race_json["pipeline_state"].pop("roster_finalization_pending", None)
            _record_provisional_roster(race_json, log)

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
                image_vision_model=image_vision_model,
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
            metadata_fast_probe = bool(
                allow_fast_no_change
                and not resume_partial
                and _fast_probe_baseline_reason(race_json)
                and _metadata_fast_probe_allowed(race_json)
            )

            # Metadata refresh is one broad race task. Candidate count must not
            # multiply its loop budget; candidate-specific work has later phases.
            meta_iters = min(max_iterations, 12)
            log("info", "Update Phase 1: Searching for new summaries, race developments, and voting records...")
            try:
                metadata_result = await _agent_loop(
                    UPDATE_META_SYSTEM,
                    UPDATE_META_USER.format(
                        race_id=race_id,
                        last_updated=last_updated,
                        current_date=as_of_date,
                        candidate_names=", ".join(candidate_names),
                    )
                    + (_FAST_NO_CHANGE_INSTRUCTION if metadata_fast_probe else ""),
                    model=model,
                    on_log=on_log,
                    race_id=race_id,
                    max_iterations=meta_iters,
                    phase_name="update-meta",
                    max_tokens=16384,
                    extra_tools=DESCRIPTION_TOOLS
                    + CANDIDATE_TOOLS
                    + RECORD_TOOLS
                    + [READ_PROFILE_TOOL, FINALIZE_METADATA_TOOL],
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                    escalate_on_tool_errors=True,
                    required_final_tool_name="finalize_metadata",
                    required_final_instruction=(
                        "Research is over. Synthesize the evidence already collected into a substantive race "
                        "description and a factual 2-3 sentence biography for EVERY active candidate. Call "
                        "finalize_metadata once with the complete candidate array and only source URLs you actually "
                        "searched or fetched. Do not leave findings only in prose and do not perform more research."
                    ),
                    return_tool_trace=True,
                    allow_no_change_after_search=metadata_fast_probe,
                )
                if (metadata_result.get("_tool_trace") or {}).get("no_change_confirmed"):
                    skipped_units = set(race_json["pipeline_state"].get("skipped_units") or [])
                    skipped_units.add("discovery.metadata")
                    race_json["pipeline_state"]["skipped_units"] = sorted(skipped_units)
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
            is_update=True,
            candidate_names=candidate_names,
            selected_name_set=selected_name_set,
            last_updated=last_updated,
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
