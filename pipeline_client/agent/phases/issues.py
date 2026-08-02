"""Per-candidate, per-issue research (canonical issue stances).

Contains the sequential per-candidate issue runner (``_run_issue_research_for_candidate``,
currently unused by any caller but preserved verbatim), the isolated per-unit
researcher used by the concurrent issues phase (``_research_issue_unit``), and
the issues-phase runner (``run_issues_phase``) invoked from ``shared_runner.py``.
"""

import asyncio
import copy
import json
import time
from typing import Any, Dict, List, Optional

from shared.pipeline_config import PipelineRuntimeConfig

from ..errors import PermanentProviderError, RetryableProviderError
from ..handlers import _make_editing_handlers
from ..prompts import (
    CANONICAL_ISSUES,
    ISSUE_SUBAGENT_SYSTEM,
    ISSUE_SUBAGENT_USER,
    UPDATE_ISSUE_SUBAGENT_SYSTEM,
    UPDATE_ISSUE_SUBAGENT_USER,
)
from ..run_budget import RunBudget, RunBudgetExceeded
from ..selection import plan_candidate_work
from ..tools import ISSUE_TOOLS, READ_PROFILE_TOOL
from ..utils import make_logger
from ..web_tools import _get_search_cache
from ._common import (
    PipelineWorkRemaining,
    RunFailureReason,
    _await_with_run_budget,
    _build_handoff_context,
    _is_control_flow_exception,
    _issue_stance_is_complete,
    _mark_pipeline_unit_complete,
    _pipeline_completed_units,
    _pipeline_issue_attempts,
    _race_identity_context,
    _record_step_failure,
    logger,
)


async def _run_issue_research_for_candidate(
    candidate_name: str,
    race_json: Dict[str, Any],
    *,
    race_id: str,
    model: str,
    on_log: Any | None = None,
    max_iterations: int = 12,
    is_update: bool = False,
    last_updated: str = "",
    on_issue_progress: Any | None = None,
    on_issue_checkpoint: Any | None = None,
    resume_partial: bool = False,
    run_budget: RunBudget | None = None,
) -> None:
    """Run per-issue research for one candidate, mutating race_json in place."""
    from . import _agent_loop, _candidate_source_hints

    log = make_logger(on_log)
    handlers = _make_editing_handlers(race_json, log)
    cache = _get_search_cache()
    cached_info = cache.list_cached_for_race(race_id) if cache else None
    candidate_website, candidate_issue_urls = await _await_with_run_budget(
        _candidate_source_hints(race_json, candidate_name),
        run_budget=run_budget,
        requested_timeout=20.0,
        operation="candidate source hint crawl",
    )
    issue_hint_text = ", ".join(candidate_issue_urls) if candidate_issue_urls else "(none found)"
    identity_context = _race_identity_context(race_json)

    handoffs: List[Dict[str, Any]] = []
    total_issues = len(CANONICAL_ISSUES)

    for issue_idx, issue in enumerate(CANONICAL_ISSUES):
        existing_issue_data: Dict[str, Any] | None = None
        for c in race_json.get("candidates", []):
            if isinstance(c, dict) and c.get("name") == candidate_name:
                sd = c.get("issues", {}).get(issue)
                if isinstance(sd, dict) and sd.get("stance"):
                    existing_issue_data = sd
                break

        if resume_partial and existing_issue_data is not None:
            log("info", f"    Issue {issue_idx + 1}/{total_issues}: {issue} already present; skipping")
            handoffs.append(
                {
                    "issue": issue,
                    "stance": existing_issue_data.get("stance", "(not set)"),
                    "confidence": existing_issue_data.get("confidence", "?"),
                }
            )
            if on_issue_checkpoint:
                try:
                    on_issue_checkpoint(issue_idx, issue)
                except Exception as _e:
                    if _is_control_flow_exception(_e):
                        raise
                    logger.debug("Issue checkpoint callback failed: %s", _e)
            continue

        if on_issue_progress:
            try:
                on_issue_progress(issue_idx, issue)
            except Exception as _e:
                if _is_control_flow_exception(_e):
                    raise
                logger.debug("Issue progress callback failed: %s", _e)

        handoff_ctx = _build_handoff_context(handoffs, cached_info)

        existing_stance = ""
        if is_update:
            for c in race_json.get("candidates", []):
                if isinstance(c, dict) and c.get("name") == candidate_name:
                    sd = c.get("issues", {}).get(issue)
                    if isinstance(sd, dict):
                        existing_stance = (
                            f"  Stance: {sd.get('stance', '?')}\n"
                            f"  Confidence: {sd.get('confidence', '?')}\n"
                            f"  Sources: {json.dumps(sd.get('sources', []))}"
                        )
                    else:
                        existing_stance = "  MISSING — no existing stance"
                    break

        if is_update:
            sys_prompt = UPDATE_ISSUE_SUBAGENT_SYSTEM
            usr_prompt = UPDATE_ISSUE_SUBAGENT_USER.format(
                candidate_name=candidate_name,
                race_id=race_id,
                issue=issue,
                last_updated=last_updated,
                existing_stance=existing_stance or "  MISSING",
                handoff_context=handoff_ctx,
                candidate_website=candidate_website,
                candidate_issue_urls=issue_hint_text,
                race_identity_context=identity_context,
            )
        else:
            sys_prompt = ISSUE_SUBAGENT_SYSTEM
            usr_prompt = ISSUE_SUBAGENT_USER.format(
                candidate_name=candidate_name,
                race_id=race_id,
                issue=issue,
                handoff_context=handoff_ctx,
                candidate_website=candidate_website,
                candidate_issue_urls=issue_hint_text,
                race_identity_context=identity_context,
            )

        log("info", f"    Issue {issue_idx + 1}/{total_issues}: {issue}")

        try:
            await _agent_loop(
                sys_prompt,
                usr_prompt,
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=min(max_iterations, 10),
                phase_name=f"issue-{candidate_name[:15]}-{issue[:15]}",
                max_tokens=4096,
                extra_tools=ISSUE_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
            )
        except RetryableProviderError:
            # Do not convert a transient provider outage into twelve missing
            # stances. Let the durable runner checkpoint and retry later.
            raise
        except PermanentProviderError as exc:
            if _is_control_flow_exception(exc):
                raise
            if exc.code == "policy_violation":
                log(
                    "error",
                    f"    Issue sub-agent skipped for {candidate_name}/{issue} "
                    f"due to OpenRouter policy violation — setting low-confidence placeholder",
                )
                # Set a low-confidence placeholder so the gap is visible and
                # fixable in later phases (refinement / iteration).
                handlers["set_issue_stance"](
                    {
                        "candidate_name": candidate_name,
                        "issue": issue,
                        "stance": "No public position found (research blocked by content policy)",
                        "confidence": "low",
                        "sources": [],
                    }
                )
            else:
                log("warning", f"    Issue sub-agent failed for {candidate_name}/{issue}: {exc}")
        except Exception as exc:
            if _is_control_flow_exception(exc):
                raise
            log("warning", f"    Issue sub-agent failed for {candidate_name}/{issue}: {exc}")

        for c in race_json.get("candidates", []):
            if isinstance(c, dict) and c.get("name") == candidate_name:
                sd = c.get("issues", {}).get(issue, {})
                handoffs.append(
                    {
                        "issue": issue,
                        "stance": sd.get("stance", "(not set)") if isinstance(sd, dict) else "(not set)",
                        "confidence": sd.get("confidence", "?") if isinstance(sd, dict) else "?",
                    }
                )
                break

        if cache:
            cached_info = cache.list_cached_for_race(race_id)

        if on_issue_checkpoint:
            try:
                on_issue_checkpoint(issue_idx, issue)
            except Exception as _e:
                if _is_control_flow_exception(_e):
                    raise
                logger.debug("Issue checkpoint callback failed: %s", _e)


async def _research_issue_unit(
    candidate_name: str,
    issue: str,
    candidate_snapshot: Dict[str, Any],
    *,
    race_id: str,
    model: str,
    on_log: Any,
    max_iterations: int,
    is_update: bool,
    last_updated: str,
    candidate_website: str,
    candidate_issue_urls: List[str],
    run_budget: RunBudget | None,
    race_identity_context: str = "",
) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
    """Research one issue against an isolated candidate copy and return its patch."""
    from . import _agent_loop

    local_race = {"candidates": [copy.deepcopy(candidate_snapshot)]}
    log = make_logger(on_log)
    handlers = _make_editing_handlers(local_race, log)
    existing_issue_data = candidate_snapshot.get("issues", {}).get(issue)
    existing_stance = "  MISSING — no existing stance"
    if isinstance(existing_issue_data, dict):
        existing_stance = (
            f"  Stance: {existing_issue_data.get('stance', '?')}\n"
            f"  Confidence: {existing_issue_data.get('confidence', '?')}\n"
            f"  Sources: {json.dumps(existing_issue_data.get('sources', []))}"
        )
    prior_stances = [
        {
            "issue": prior_issue,
            "stance": data.get("stance", "(not set)"),
            "confidence": data.get("confidence", "?"),
        }
        for prior_issue, data in candidate_snapshot.get("issues", {}).items()
        if prior_issue != issue and isinstance(data, dict)
    ]
    handoff_context = _build_handoff_context(prior_stances, None)
    issue_hint_text = ", ".join(candidate_issue_urls) if candidate_issue_urls else "(none found)"
    identity_context = race_identity_context or _race_identity_context({})

    if is_update:
        system_prompt = UPDATE_ISSUE_SUBAGENT_SYSTEM
        user_prompt = UPDATE_ISSUE_SUBAGENT_USER.format(
            candidate_name=candidate_name,
            race_id=race_id,
            issue=issue,
            last_updated=last_updated,
            existing_stance=existing_stance,
            handoff_context=handoff_context,
            candidate_website=candidate_website,
            candidate_issue_urls=issue_hint_text,
            race_identity_context=identity_context,
        )
    else:
        system_prompt = ISSUE_SUBAGENT_SYSTEM
        user_prompt = ISSUE_SUBAGENT_USER.format(
            candidate_name=candidate_name,
            race_id=race_id,
            issue=issue,
            handoff_context=handoff_context,
            candidate_website=candidate_website,
            candidate_issue_urls=issue_hint_text,
            race_identity_context=identity_context,
        )

    loop_result: Dict[str, Any] = {}
    try:
        loop_result = await _agent_loop(
            system_prompt,
            user_prompt,
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=min(max_iterations, 10),
            phase_name=f"issue-{candidate_name[:15]}-{issue[:15]}",
            max_tokens=4096,
            extra_tools=ISSUE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
            return_tool_trace=True,
            required_final_tool_name="set_issue_stance",
            required_final_instruction=(
                "Stop searching and synthesize all evidence already collected. You MUST call set_issue_stance now. "
                "Record a concise factual stance with every supporting source you found. If and only if the research "
                "found no attributable position, set stance to exactly 'No public position found', confidence to "
                "'low', and sources to []. Do not infer or invent a position."
            ),
            run_budget=run_budget,
        )
    except RunBudgetExceeded:
        raise
    except RetryableProviderError:
        raise
    except PermanentProviderError as exc:
        if _is_control_flow_exception(exc):
            raise
        if exc.code == "policy_violation":
            return None, {"status": "blocked_policy", "search_calls": 0, "page_fetches": 0}
        log("warning", f"    Issue sub-agent failed for {candidate_name}/{issue}: {exc}")
    except Exception as exc:
        if _is_control_flow_exception(exc):
            raise
        log("warning", f"    Issue sub-agent failed for {candidate_name}/{issue}: {exc}")

    candidate = local_race["candidates"][0]
    result = candidate.get("issues", {}).get(issue)
    trace = loop_result.get("_tool_trace", {}) if isinstance(loop_result, dict) else {}
    if not isinstance(result, dict):
        return None, trace
    if result == existing_issue_data:
        # set_issue_stance was never called this attempt (crash, timeout, ran out
        # of iterations) — this is a genuine failure, not a conclusion, so signal
        # "nothing happened" rather than echoing back stale pre-existing data
        # (which could otherwise be mistaken for a fresh verdict by the caller).
        research_actions = int(trace.get("search_calls", 0) or 0) + int(trace.get("page_fetches", 0) or 0)
        if is_update and research_actions > 0 and str(result.get("stance") or "").strip():
            trace["confirmed_existing"] = True
            return copy.deepcopy(result), trace
        return None, trace
    return copy.deepcopy(result), trace


async def run_issues_phase(
    race_json: Dict[str, Any],
    race_id: str,
    *,
    candidate_names: List[str],
    small_model: str,
    on_log: Any,
    max_iterations: int,
    step_enabled: Any,
    track: Any,
    max_candidates: Optional[int],
    target_no_info: bool,
    is_update: bool,
    last_updated: str,
    log: Any,
    prefix: str,
    resume_partial: bool,
    continue_incomplete_work: bool,
    run_budget: RunBudget | None,
) -> None:
    """Phase 2: per-candidate, per-issue research (tools mode). Mutates race_json."""
    from . import _candidate_source_hints

    if not step_enabled("issues"):
        log("info", f"{prefix} 2: Issue research — SKIPPED")
        track("skip", "issues")
        return

    track("start", "issues")
    iss_t0 = time.perf_counter()
    completed_units = _pipeline_completed_units(race_json)
    issue_attempts = _pipeline_issue_attempts(race_json)
    issue_research = race_json.setdefault("pipeline_state", {}).setdefault("issue_research", {})
    if not isinstance(issue_research, dict):
        issue_research = {}
        race_json["pipeline_state"]["issue_research"] = issue_research
    if not resume_partial:
        # Reset only the candidates this run will actually research. Clearing
        # race-wide destroyed the research audit for everyone else, and review
        # flags a "No public position found" stance whose audit is missing — so a
        # targeted candidate_names repair re-broke every candidate it skipped and
        # no sequence of targeted runs could ever converge.
        scoped_names = {str(name) for name in candidate_names}

        def _belongs_to_scope(unit: str) -> bool:
            parts = unit.split(":")
            return len(parts) >= 2 and parts[1] in scoped_names

        completed_units = {unit for unit in completed_units if not (unit.startswith("issues:") and _belongs_to_scope(unit))}
        race_json["pipeline_state"]["completed_units"] = sorted(completed_units)
        for tracker in (issue_attempts, issue_research):
            for unit_id in [key for key in tracker if key.startswith("issues:") and _belongs_to_scope(key)]:
                del tracker[unit_id]
    else:
        candidates_by_name = {
            str(candidate.get("name")): candidate
            for candidate in race_json.get("candidates", [])
            if isinstance(candidate, dict) and candidate.get("name")
        }
        for name in candidate_names:
            issues = candidates_by_name.get(name, {}).get("issues", {})
            for issue in CANONICAL_ISSUES:
                unit_id = f"issues:{name}:{issue}"
                if unit_id in completed_units and not _issue_stance_is_complete(issues.get(issue)):
                    completed_units.discard(unit_id)
        race_json["pipeline_state"]["completed_units"] = sorted(completed_units)
    pending_candidate_names = [
        name for name in candidate_names if not all(f"issues:{name}:{issue}" in completed_units for issue in CANONICAL_ISSUES)
    ]
    work_plan = plan_candidate_work(
        pending_candidate_names,
        race_json,
        max_candidates=max_candidates,
        target_no_info=target_no_info,
        log=log,
    )
    research_names = work_plan.selected
    pipeline_state = race_json.setdefault("pipeline_state", {})
    pipeline_state["remaining_candidates"] = work_plan.deferred
    pipeline_state["remaining_steps"] = ["issues"] if work_plan.deferred else []
    pipeline_state["complete"] = not work_plan.deferred
    rn = len(research_names)
    n_issues = len(CANONICAL_ISSUES)
    total_units = max(rn * n_issues, 1)
    runtime_config = PipelineRuntimeConfig.from_env()
    issue_concurrency = runtime_config.issue_concurrency
    max_issue_attempts = runtime_config.issue_max_attempts
    semaphore = asyncio.Semaphore(issue_concurrency)
    candidates_by_name = {
        str(candidate.get("name")): candidate
        for candidate in race_json.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("name")
    }
    completed_count = 0
    tasks: List[asyncio.Task] = []
    log("info", f"{prefix} 2: Researching issues for {rn} candidates ({n_issues} issues each)...")

    for ci, cand_name in enumerate(research_names):
        candidate = candidates_by_name.get(cand_name)
        if not candidate:
            continue
        candidate_website, candidate_issue_urls = await _await_with_run_budget(
            _candidate_source_hints(race_json, cand_name),
            run_budget=run_budget,
            requested_timeout=20.0,
            operation="candidate source hint crawl",
        )
        for issue_idx, issue in enumerate(CANONICAL_ISSUES):
            unit_id = f"issues:{cand_name}:{issue}"
            existing_issue = candidate.get("issues", {}).get(issue)
            if unit_id in completed_units or (resume_partial and _issue_stance_is_complete(existing_issue)):
                _mark_pipeline_unit_complete(race_json, unit_id)
                completed_units.add(unit_id)
                completed_count += 1
                track(
                    "progress",
                    "issues",
                    pct=int(completed_count / total_units * 100),
                    message=(f"Issues checkpoint - {cand_name} ({ci + 1}/{rn}) - " f"{issue} ({issue_idx + 1}/{n_issues})"),
                    race_json=race_json,
                )
                continue

            if issue_attempts.get(unit_id, 0) >= max_issue_attempts:
                log(
                    "warning",
                    f"    Issue retry limit reached for {cand_name}/{issue}; leaving the unit incomplete for explicit retry",
                )
                prior_audit = issue_research.get(unit_id)
                issue_research[unit_id] = {
                    **(prior_audit if isinstance(prior_audit, dict) else {}),
                    "status": "retry_limit",
                    "attempts": issue_attempts.get(unit_id, 0),
                }
                _record_step_failure(
                    race_json,
                    "issues",
                    RunFailureReason.STEP_NO_DATA,
                    f"{cand_name}/{issue}: retry limit reached without a research verdict",
                )
                continue

            async def _run_unit(
                candidate_name: str = cand_name,
                issue_name: str = issue,
                candidate_index: int = ci,
                canonical_issue_index: int = issue_idx,
                candidate_data: Dict[str, Any] = copy.deepcopy(candidate),
                website: str = candidate_website,
                issue_urls: List[str] = list(candidate_issue_urls),
            ) -> tuple[str, str, int, int, Dict[str, Any] | None]:
                nonlocal completed_count
                prior_attempts = issue_attempts.get(f"issues:{candidate_name}:{issue_name}", 0)
                if prior_attempts:
                    await asyncio.sleep(prior_attempts * 0.01)
                async with semaphore:
                    unit_id = f"issues:{candidate_name}:{issue_name}"
                    issue_attempts[unit_id] = issue_attempts.get(unit_id, 0) + 1
                    track(
                        "progress",
                        "issues",
                        pct=int(completed_count / total_units * 100),
                        message=(
                            f"Issues · {candidate_name} ({candidate_index + 1}/{rn}) · "
                            f"{issue_name} ({canonical_issue_index + 1}/{n_issues})"
                        ),
                        race_json=race_json,
                    )
                    log(
                        "info",
                        f"    Issue {canonical_issue_index + 1}/{n_issues}: " f"{candidate_name} / {issue_name}",
                    )
                    patch, trace = await _research_issue_unit(
                        candidate_name,
                        issue_name,
                        candidate_data,
                        race_id=race_id,
                        model=small_model,
                        on_log=on_log,
                        max_iterations=max_iterations,
                        is_update=is_update,
                        last_updated=last_updated,
                        candidate_website=website,
                        candidate_issue_urls=issue_urls,
                        run_budget=run_budget,
                        race_identity_context=_race_identity_context(race_json),
                    )
                    sources = patch.get("sources", []) if isinstance(patch, dict) else []
                    stance = str(patch.get("stance") or "") if isinstance(patch, dict) else ""
                    prior_audit = issue_research.get(unit_id)
                    prior_audit = prior_audit if isinstance(prior_audit, dict) else {}
                    search_calls = int(prior_audit.get("search_calls", 0) or 0) + int(trace.get("search_calls", 0) or 0)
                    page_fetches = int(prior_audit.get("page_fetches", 0) or 0) + int(trace.get("page_fetches", 0) or 0)
                    research_actions = search_calls + page_fetches
                    if "no public position found" in stance.lower() and research_actions < 2:
                        log(
                            "warning",
                            f"    Rejecting unsupported no-position result for {candidate_name}/{issue_name}: "
                            f"only {research_actions} research action(s) were recorded",
                        )
                        patch = None
                        audit_status = "insufficient_research"
                    else:
                        audit_status = (
                            "completed"
                            if patch is not None
                            else trace.get("status")
                            if trace.get("status") == "blocked_policy"
                            else "no_verdict"
                        )
                    issue_research[unit_id] = {
                        "status": audit_status,
                        "attempts": issue_attempts.get(unit_id, 0),
                        "search_calls": search_calls,
                        "page_fetches": page_fetches,
                        "source_count": len(sources) if isinstance(sources, list) else 0,
                        "token_budget_reached": bool(trace.get("token_budget_reached", False)),
                        "max_iterations_reached": bool(trace.get("max_iterations_reached", False)),
                    }
                    # A non-None patch means the sub-agent successfully called
                    # set_issue_stance — either with a real stance, or (the only
                    # other way past that handler's validation) a deliberate
                    # "no public position found" conclusion after investigating.
                    # Either way the model reached a reasoned verdict, so accept
                    # it as final for this run instead of burning another full
                    # attempt re-researching something already concluded absent.
                    # Only a truly empty patch (crash/timeout/no tool call at
                    # all) is a genuine failure worth retrying.
                    if patch is not None and str(patch.get("stance") or "").strip():
                        candidate = candidates_by_name[candidate_name]
                        candidate.setdefault("issues", {})[issue_name] = patch
                        _mark_pipeline_unit_complete(race_json, unit_id)
                        completed_units.add(unit_id)
                        completed_count += 1
                        track(
                            "progress",
                            "issues",
                            pct=int(completed_count / total_units * 100),
                            message=(
                                f"Issues checkpoint - {candidate_name} ({candidate_index + 1}/{rn}) - "
                                f"{issue_name} ({canonical_issue_index + 1}/{n_issues})"
                            ),
                            race_json=race_json,
                        )
                    elif patch is None:
                        # A truly empty patch: the sub-agent crashed, timed out, or
                        # made no tool call at all — a genuine failure, not a
                        # deliberate "no position found" conclusion.
                        _record_step_failure(
                            race_json,
                            "issues",
                            RunFailureReason.STEP_NO_DATA,
                            f"{candidate_name}/{issue_name}: issue sub-agent produced no verdict",
                        )
                    return candidate_name, issue_name, candidate_index, canonical_issue_index, patch

            tasks.append(asyncio.create_task(_run_unit()))

    try:
        for completed_task in asyncio.as_completed(tasks):
            await completed_task
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    remaining_candidates = [
        name for name in candidate_names if not all(f"issues:{name}:{issue}" in completed_units for issue in CANONICAL_ISSUES)
    ]
    pipeline_state["remaining_candidates"] = remaining_candidates
    pipeline_state["remaining_steps"] = ["issues"] if remaining_candidates else []
    pipeline_state["complete"] = not remaining_candidates
    if remaining_candidates and continue_incomplete_work and tasks:
        track(
            "progress",
            "issues",
            pct=int(completed_count / total_units * 100),
            message=f"Issues: {len(remaining_candidates)} candidate(s) remain for continuation",
            race_json=race_json,
        )
        raise PipelineWorkRemaining("Issue research work units remain")
    track("complete", "issues", duration_ms=int((time.perf_counter() - iss_t0) * 1000), race_json=race_json)
