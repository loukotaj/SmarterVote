"""Phase orchestration — discovery, issues, finance, refinement, iteration.

Contains the per-candidate issue sub-agent, shared phase runner, fresh and
update flow runners, and review-iteration logic. Selection helpers live in
``selection.py``; patch/merge helpers in ``patches.py``; deterministic roster
rules in ``roster.py``; and durable unit bookkeeping in ``phase_state.py``.
"""

import asyncio
import copy
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.pipeline_config import PipelineRuntimeConfig
from shared.run_health import RunFailureReason
from shared.run_health import classify_exception as _classify_exception
from shared.run_health import detect_empty_finance_output as _detect_empty_finance_output
from shared.run_health import record_step_failure as _record_step_failure

logger = logging.getLogger("pipeline")

from . import phase_state, roster
from .ballotpedia import lookup_election_page as _ballotpedia_election_lookup
from .errors import PermanentProviderError, RetryableProviderError
from .handlers import _make_editing_handlers
from .images import resolve_candidate_images
from .llm import _agent_loop, _ensure_dict, _normalize_candidate
from .market_data.kalshi import fetch_kalshi_market_signals
from .model_registry import CHEAP_MODEL, DEFAULT_MODEL, NANO_MODEL
from .patches import (  # noqa: F401 — re-exported for backward compat
    _apply_candidate_patch,
    _apply_finance_patch,
    _apply_issue_patch,
    _apply_meta_patch,
    _apply_refine_patch,
    _deduplicate_donors,
    _summarize_existing_stances,
)
from .prompts import (
    CANONICAL_ISSUES,
    DISCOVERY_SYSTEM,
    DISCOVERY_USER,
    FINANCE_VOTING_SYSTEM,
    FINANCE_VOTING_USER,
    FORECAST_SYSTEM,
    FORECAST_USER,
    ISSUE_SUBAGENT_SYSTEM,
    ISSUE_SUBAGENT_USER,
    ITERATE_META_USER,
    ITERATE_SYSTEM,
    ITERATE_USER,
    POLLING_SYSTEM,
    POLLING_USER,
    REFINE_META_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    ROSTER_SYNC_SYSTEM,
    ROSTER_SYNC_USER,
    ROSTER_VERIFY_SYSTEM,
    ROSTER_VERIFY_USER,
    UPDATE_ISSUE_SUBAGENT_SYSTEM,
    UPDATE_ISSUE_SUBAGENT_USER,
    UPDATE_META_SYSTEM,
    UPDATE_META_USER,
    VOTER_RESOURCES_SYSTEM,
    VOTER_RESOURCES_USER,
)
from .review_flags import format_review_flags as _format_review_flags
from .review_flags import has_actionable_flags as _has_actionable_flags
from .run_budget import RunBudget, RunBudgetExceeded
from .selection import (  # noqa: F401 — re-exported for backward compat
    _candidate_info_score,
    _candidate_source_hints,
    _scale_iterations,
    _select_target_candidates,
    plan_candidate_work,
)
from .tools import (
    BACKGROUND_TOOLS,
    CANDIDATE_TOOLS,
    DESCRIPTION_TOOLS,
    FORECAST_TOOLS,
    ISSUE_TOOLS,
    POLLING_TOOLS,
    RACE_TOOLS,
    READ_PROFILE_TOOL,
    RECORD_TOOLS,
    REMOVE_CANDIDATE_TOOL,
    ROSTER_TOOLS,
    VOTER_RESOURCE_TOOLS,
)
from .utils import make_logger
from .web_tools import _get_search_cache

# ---------------------------------------------------------------------------
# Per-candidate, per-issue sub-agent
# ---------------------------------------------------------------------------

_TERM_LIMITED_NON_CANDIDATE_RE = re.compile(
    r"\b(term[- ]limited|cannot run|can't run|cannot seek|not seeking re-?election|"
    r"not running|ineligible|not eligible|from running again)\b",
    re.IGNORECASE,
)
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


def _candidate_name(candidate: Any) -> str:
    return roster.candidate_name(candidate)


def _normalize_candidate_entries(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop malformed candidate entries before phase fan-out touches them."""
    roster.normalize_candidate_entries(race_json, log)


def _candidate_roster_text(candidate: Dict[str, Any]) -> str:
    """Return searchable text from candidate fields used for roster sanity checks."""
    pieces: List[str] = []
    for field in ("name", "summary"):
        value = candidate.get(field)
        if isinstance(value, str):
            pieces.append(value)
    for source in candidate.get("summary_sources") or []:
        if isinstance(source, dict):
            title = source.get("title")
            if isinstance(title, str):
                pieces.append(title)
    return " ".join(pieces)


def _remove_ineligible_officeholders(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop current officeholders the discovery output says cannot run in this race."""
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return

    kept: List[Any] = []
    removed: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            kept.append(candidate)
            continue
        text = _candidate_roster_text(candidate)
        if candidate.get("incumbent") is True and _TERM_LIMITED_NON_CANDIDATE_RE.search(text):
            removed.append(str(candidate.get("name") or "unknown"))
            continue
        kept.append(candidate)

    if removed:
        race_json["candidates"] = kept
        if log:
            log(
                "warning",
                "Removed ineligible incumbent/non-candidate entries from discovery roster: " + ", ".join(removed),
            )


def _remove_inactive_candidates(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop candidates explicitly marked withdrawn by the roster tools.

    Do not infer inactive status from free-text summaries here. Roster repair
    agents sometimes mention historical primary losses or stale Ballotpedia
    snippets in candidate text; pruning on that text can delete valid current
    candidates. Exit decisions must go through ``remove_candidate`` guards.
    """
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return

    kept: List[Any] = []
    removed: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            kept.append(candidate)
            continue

        if candidate.get("withdrawn") is True:
            removed.append(str(candidate.get("name") or "unknown"))
            continue

        kept.append(candidate)

    if removed:
        race_json["candidates"] = kept
        if log:
            log("warning", "Removed inactive candidates from discovery roster: " + ", ".join(removed))


def _norm_name_for_match(name: str) -> str:
    return roster.normalize_name(name)


def _names_likely_same(left: str, right: str) -> bool:
    return roster.names_likely_same(left, right)


def _candidate_matches_any(name: str, roster: List[Dict[str, Any]]) -> bool:
    return any(_names_likely_same(name, str(candidate.get("name") or "")) for candidate in roster)


def _party_tag(party: Any) -> str:
    """Normalize a party value to a simple tag for balance checks."""
    return roster.party_tag(party)


def _reconcile_candidates_with_authoritative_roster(
    race_json: Dict[str, Any],
    authoritative_candidates: List[Dict[str, Any]],
    log: Any | None = None,
) -> None:
    """Remove stale candidates missing from Ballotpedia's current election roster.

    Candidates whose party is NOT represented in the authoritative roster at all are
    preserved — this prevents removing an incumbent of one party when Ballotpedia
    returned only the other party's primary page (a common pre-primary lookup pattern).
    """
    if not authoritative_candidates:
        return
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return

    # Collect the set of party tags present in the Ballotpedia roster.
    authoritative_party_tags: set = {_party_tag(c.get("party")) for c in authoritative_candidates if isinstance(c, dict)}

    kept: List[Any] = []
    removed: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            kept.append(candidate)
            continue
        name = _candidate_name(candidate)
        if not name or _candidate_matches_any(name, authoritative_candidates):
            kept.append(candidate)
            continue

        # If the candidate's party has NO representatives in the BP roster, the BP
        # page is likely a single-party primary page, not the full general election
        # roster.  Keep candidates of the missing party to avoid stripping the other
        # side of the ballot.
        tag = _party_tag(candidate.get("party"))
        if tag not in authoritative_party_tags:
            if log:
                log(
                    "debug",
                    f"  Kept {name} ({tag}) — party absent from BP roster (possible primary-only page)",
                )
            kept.append(candidate)
            continue

        removed.append(name)

    if removed:
        if not any(isinstance(candidate, dict) and _candidate_name(candidate) for candidate in kept):
            if log:
                log(
                    "warning",
                    "Skipped authoritative roster removal because it would leave the race with no candidates: "
                    + ", ".join(removed),
                )
            return
        race_json["candidates"] = kept
        if log:
            log(
                "warning",
                "Removed candidates absent from current Ballotpedia election roster: " + ", ".join(removed),
            )


def _add_candidates_from_authoritative_roster(
    race_json: Dict[str, Any],
    authoritative_candidates: List[Dict[str, Any]],
    log: Any | None = None,
) -> None:
    """Add missing candidates from an authoritative election roster."""
    if not authoritative_candidates:
        return
    candidates = race_json.setdefault("candidates", [])
    if not isinstance(candidates, list):
        race_json["candidates"] = []
        candidates = race_json["candidates"]

    added: List[str] = []
    current_candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
    for authoritative in authoritative_candidates:
        name = _candidate_name(authoritative)
        if not name or _candidate_matches_any(name, current_candidates):
            continue
        candidate = {
            "name": name,
            "party": authoritative.get("party") or "Unknown",
            "incumbent": bool(authoritative.get("incumbent")),
            "summary": "",
            "summary_sources": [],
            "image_url": authoritative.get("image_url"),
            "website": None,
            "social_media": {},
            "career_history": [],
            "education": [],
            "donor_summary": None,
            "donor_source_url": None,
            "donor_sources": [],
            "voting_summary": None,
            "voting_source_url": None,
            "voting_sources": [],
            "links": [],
            "issues": {},
        }
        candidates.append(candidate)
        current_candidates.append(candidate)
        added.append(name)

    if added and log:
        log("info", "Added candidates from current Ballotpedia election roster: " + ", ".join(added))


async def _sync_ballotpedia_roster(race_json: Dict[str, Any], race_id: str, log: Any | None = None) -> None:
    """Fetch Ballotpedia roster data as advisory evidence only.

    Election and district pages can contain stale primary tables or unrelated
    navigation tables.  The model-backed roster phase can inspect this result
    alongside official sources, but an unreviewed scrape must never add or
    remove candidates from an existing researched profile.
    """
    try:
        bp_result = await _ballotpedia_election_lookup(race_id)
    except Exception as exc:
        if log:
            log("debug", f"  Ballotpedia roster sync failed: {exc}")
        return

    if not isinstance(bp_result, dict) or not bp_result.get("found"):
        return
    bp_candidates = bp_result.get("candidates")
    if isinstance(bp_candidates, list) and log:
        names = [_candidate_name(candidate) for candidate in bp_candidates if _candidate_name(candidate)]
        if names:
            log("debug", f"  Ballotpedia roster lookup returned {len(names)} advisory candidate(s); no automatic edits")


def _backfill_source_timestamps(race_json: Dict[str, Any]) -> None:
    """Backfill missing last_accessed on legacy source objects loaded from checkpoints.

    Old data saved before the last_accessed field was made required will fail schema
    validation.  This sets a fallback ISO-8601 timestamp so validation passes.
    """
    roster.backfill_source_timestamps(race_json)


_ROSTER_CAP = roster.ROSTER_CAP


def _cap_roster(race_json: Dict[str, Any], log: Any | None = None, limit: int = _ROSTER_CAP) -> None:
    """Hard-cap the roster to *limit* candidates, balanced across major parties.

    The roster-sync prompt asks the model to keep the field tight, but the
    economy model and the Ballotpedia/search paths can still balloon a roster to
    dozens of entries. This deterministic trim keeps incumbents and the
    highest-signal major-party contenders (up to 4 Democratic + 4 Republican),
    filling any remaining slots with the next best candidates.
    """
    roster.cap_roster(race_json, log, limit)


def _remove_known_ineligible_candidates(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop candidates the model itself recorded as ineligible / not running.

    The discovery and roster-sync prompts populate
    ``pipeline_state.race_identity.known_ineligible_or_not_running`` with people
    who are term-limited, retiring, the state's off-cycle senator, or prior-cycle
    candidates. The economy model is decent at *listing* them there but often
    fails to *remove* them from ``candidates``; enforce the removal here.
    """
    state = race_json.get("pipeline_state")
    identity = state.get("race_identity") if isinstance(state, dict) else None
    if not isinstance(identity, dict):
        return
    banned = identity.get("known_ineligible_or_not_running")
    if not isinstance(banned, list) or not banned:
        return
    banned_norm = {str(name).strip().lower() for name in banned if isinstance(name, str) and str(name).strip()}
    if not banned_norm:
        return
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return
    kept: List[Dict[str, Any]] = []
    removed: List[str] = []
    for candidate in candidates:
        name = _candidate_name(candidate) if isinstance(candidate, dict) else ""
        if name and name.strip().lower() in banned_norm:
            removed.append(name)
        else:
            kept.append(candidate)
    if removed:
        race_json["candidates"] = kept
        if log:
            log("info", f"    Removed known-ineligible/not-running candidate(s): {', '.join(removed)}")


def _sanitize_roster(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Apply deterministic roster constraints before downstream fan-out."""
    _normalize_candidate_entries(race_json, log)
    _remove_ineligible_officeholders(race_json, log)
    _remove_inactive_candidates(race_json, log)
    _remove_known_ineligible_candidates(race_json, log)
    _cap_roster(race_json, log)
    race_json.pop("candidate_limit_note", None)


def _pipeline_completed_units(race_json: Dict[str, Any]) -> set[str]:
    return phase_state.completed_units(race_json)


def _mark_pipeline_unit_complete(race_json: Dict[str, Any], unit: str) -> None:
    phase_state.mark_unit_complete(race_json, unit)


def _issue_stance_is_complete(value: Any) -> bool:
    """True if *value* holds a real stance — not empty and not a placeholder.

    A plain non-empty check let literal placeholder text (e.g. "To be determined
    after review") count as "done", so a fresh issues-step pass would skip it
    forever as already-complete rather than retry it. Lazy import avoids a
    circular dependency (agent.py imports from this module).
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
) -> Dict[str, Any] | None:
    """Research one issue against an isolated candidate copy and return its patch."""
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
        )

    try:
        await _agent_loop(
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
            return {
                "stance": "No public position found (research blocked by content policy)",
                "confidence": "low",
                "sources": [],
            }
        log("warning", f"    Issue sub-agent failed for {candidate_name}/{issue}: {exc}")
    except Exception as exc:
        if _is_control_flow_exception(exc):
            raise
        log("warning", f"    Issue sub-agent failed for {candidate_name}/{issue}: {exc}")

    candidate = local_race["candidates"][0]
    result = candidate.get("issues", {}).get(issue)
    if not isinstance(result, dict):
        return None
    if result == existing_issue_data:
        # set_issue_stance was never called this attempt (crash, timeout, ran out
        # of iterations) — this is a genuine failure, not a conclusion, so signal
        # "nothing happened" rather than echoing back stale pre-existing data
        # (which could otherwise be mistaken for a fresh verdict by the caller).
        return None
    return copy.deepcopy(result)


# ---------------------------------------------------------------------------
# Shared phase runner — images → issues → finance → refinement
# ---------------------------------------------------------------------------


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
    n = len(candidate_names)

    # --- Phase 1b: Image URL verification & resolution (parallel) ---
    if step_enabled("images"):
        track("start", "images")
        img_t0 = time.perf_counter()
        log("info", f"{prefix} 1b: Verifying and resolving candidate image URLs...")

        def _on_image_progress(pct: int, cand_name: str) -> None:
            track("progress", "images", pct=pct, message=f"Image Resolution: {cand_name}")

        await resolve_candidate_images(
            {
                "candidates": [
                    c for c in race_json.get("candidates", []) if isinstance(c, dict) and c.get("name") in selected_name_set
                ],
                "office": race_json.get("office", ""),
                "jurisdiction": race_json.get("jurisdiction", ""),
            },
            agent_loop_fn=_agent_loop,
            model=small_model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=min(max_iterations, 10),
            on_progress=_on_image_progress,
            run_budget=run_budget,
        )
        track("complete", "images", duration_ms=int((time.perf_counter() - img_t0) * 1000), race_json=race_json)
    else:
        log("info", f"{prefix} 1b: Image resolution — SKIPPED")
        track("skip", "images")

    # --- Phase 2: Per-candidate, per-issue research (tools mode) ---
    if step_enabled("issues"):
        track("start", "issues")
        iss_t0 = time.perf_counter()
        completed_units = _pipeline_completed_units(race_json)
        issue_attempts = _pipeline_issue_attempts(race_json)
        if not resume_partial:
            completed_units = {unit for unit in completed_units if not unit.startswith("issues:")}
            race_json["pipeline_state"]["completed_units"] = sorted(completed_units)
            issue_attempts.clear()
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
            name
            for name in candidate_names
            if not all(f"issues:{name}:{issue}" in completed_units for issue in CANONICAL_ISSUES)
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
                        message=(
                            f"Issues checkpoint - {cand_name} ({ci + 1}/{rn}) - " f"{issue} ({issue_idx + 1}/{n_issues})"
                        ),
                        race_json=race_json,
                    )
                    continue

                if issue_attempts.get(unit_id, 0) >= max_issue_attempts:
                    log(
                        "warning",
                        f"    Issue retry limit reached for {cand_name}/{issue}; "
                        "recording a low-confidence no-position result",
                    )
                    candidate.setdefault("issues", {})[issue] = {
                        "issue": issue,
                        "stance": "No public position found after repeated research attempts.",
                        "confidence": "low",
                        "sources": [],
                    }
                    _mark_pipeline_unit_complete(race_json, unit_id)
                    completed_units.add(unit_id)
                    completed_count += 1
                    track(
                        "progress",
                        "issues",
                        pct=int(completed_count / total_units * 100),
                        message=(
                            f"Issues checkpoint - {cand_name} ({ci + 1}/{rn}) - " f"{issue} ({issue_idx + 1}/{n_issues})"
                        ),
                        race_json=race_json,
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
                        patch = await _research_issue_unit(
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
                        )
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
            name
            for name in candidate_names
            if not all(f"issues:{name}:{issue}" in completed_units for issue in CANONICAL_ISSUES)
        ]
        pipeline_state["remaining_candidates"] = remaining_candidates
        pipeline_state["remaining_steps"] = ["issues"] if remaining_candidates else []
        pipeline_state["complete"] = not remaining_candidates
        if remaining_candidates and continue_incomplete_work:
            track(
                "progress",
                "issues",
                pct=int(completed_count / total_units * 100),
                message=f"Issues: {len(remaining_candidates)} candidate(s) remain for continuation",
                race_json=race_json,
            )
            raise PipelineWorkRemaining("Issue research work units remain")
        track("complete", "issues", duration_ms=int((time.perf_counter() - iss_t0) * 1000), race_json=race_json)
    else:
        log("info", f"{prefix} 2: Issue research — SKIPPED")
        track("skip", "issues")

    # --- Phase 2b: Dedicated finance & voting record research ---
    if step_enabled("finance"):
        track("start", "finance")
        fin_t0 = time.perf_counter()
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
    else:
        log("info", f"{prefix} 2b: Finance & voting — SKIPPED")
        track("skip", "finance")

    # --- Phase 3: Refinement (tools mode — per-candidate + meta) ---
    if step_enabled("refinement"):
        track("start", "refinement")
        ref_t0 = time.perf_counter()
        handlers = _make_editing_handlers(race_json, log)
        cand_list = [c for c in race_json.get("candidates", []) if isinstance(c, dict) and c.get("name") in selected_name_set]
        cand_names_in_json = [c["name"] for c in cand_list]
        n_cands = len(cand_list)
        refinement_units = _pipeline_completed_units(race_json)
        log("info", f"{prefix} 3: Refining profile (one candidate at a time, tools mode)...")
        for ci, candidate in enumerate(cand_list):
            cname = candidate["name"]
            unit_id = f"refinement:{cname}"
            if resume_partial and unit_id in refinement_units:
                track(
                    "progress",
                    "refinement",
                    pct=int(((ci + 1) / max(n_cands, 1)) * 100),
                    message=f"Refinement checkpoint: {cname} ({ci + 1}/{n_cands})",
                    race_json=race_json,
                )
                continue
            candidate_website, candidate_issue_urls = await _await_with_run_budget(
                _candidate_source_hints(race_json, cname),
                run_budget=run_budget,
                requested_timeout=20.0,
                operation="candidate source hint crawl",
            )
            issue_hint_text = ", ".join(candidate_issue_urls) if candidate_issue_urls else "(none found)"
            log("info", f"  Refining {cname}...")
            track(
                "progress",
                "refinement",
                pct=int((ci / max(n_cands, 1)) * 100),
                message=f"Refinement: {cname} ({ci + 1}/{n_cands})",
                race_json=race_json,
            )
            try:
                refine_prefix = "upd-refine" if is_update else "refine"
                await _agent_loop(
                    REFINE_SYSTEM,
                    REFINE_USER.format(
                        race_id=race_id,
                        candidate_name=cname,
                        candidate_website=candidate_website,
                        candidate_issue_urls=issue_hint_text,
                        candidate_json=json.dumps(candidate, indent=2, default=str),
                        race_description=race_json.get("description", ""),
                        other_candidates=", ".join(cn for cn in cand_names_in_json if cn != cname),
                        all_issues=", ".join(CANONICAL_ISSUES),
                    ),
                    model=model,
                    on_log=on_log,
                    race_id=race_id,
                    max_iterations=max(8, refine_iters // max(n_cands, 1)),
                    phase_name=f"{refine_prefix}-{cname[:20]}",
                    max_tokens=8192,
                    extra_tools=CANDIDATE_TOOLS + ISSUE_TOOLS + RECORD_TOOLS + BACKGROUND_TOOLS + [READ_PROFILE_TOOL],
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                )
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Refine failed for {cname}: {exc} — keeping existing")
                _record_step_failure(race_json, "refinement", _classify_exception(exc), f"{cname}: {exc}")
            _mark_pipeline_unit_complete(race_json, unit_id)
            refinement_units.add(unit_id)
            track(
                "progress",
                "refinement",
                pct=int(((ci + 1) / max(n_cands, 1)) * 100),
                message=f"Refinement checkpoint: {cname} ({ci + 1}/{n_cands})",
                race_json=race_json,
            )

        # Meta refinement (description only) — tools mode
        meta_unit_id = "refinement:meta"
        if not (resume_partial and meta_unit_id in refinement_units):
            log("info", "  Refining race metadata...")
            try:
                await _agent_loop(
                    REFINE_SYSTEM,
                    REFINE_META_USER.format(
                        race_id=race_id,
                        race_description=race_json.get("description", ""),
                    ),
                    model=model,
                    on_log=on_log,
                    race_id=race_id,
                    max_iterations=max(6, refine_iters // 3),
                    phase_name=f"{'upd-' if is_update else ''}refine-meta",
                    max_tokens=4096,
                    extra_tools=DESCRIPTION_TOOLS + [READ_PROFILE_TOOL],
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                )
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Refine meta failed: {exc} — keeping existing meta")
                _record_step_failure(race_json, "refinement", _classify_exception(exc), f"meta: {exc}")
            _mark_pipeline_unit_complete(race_json, meta_unit_id)
            refinement_units.add(meta_unit_id)
            track(
                "progress",
                "refinement",
                pct=100,
                message="Refinement checkpoint: race metadata",
                race_json=race_json,
            )
        track("complete", "refinement", duration_ms=int((time.perf_counter() - ref_t0) * 1000), race_json=race_json)
    else:
        log("info", f"{prefix} 3: Refinement — SKIPPED")
        track("skip", "refinement")

    handlers = _make_editing_handlers(race_json, log)
    if step_enabled("polling"):
        track("start", "polling")
        polling_t0 = time.perf_counter()
        log("info", f"{prefix} 4: Refreshing public polling...")
        try:
            await _agent_loop(
                POLLING_SYSTEM,
                POLLING_USER.format(
                    race_id=race_id,
                    current_date=datetime.now(timezone.utc).date().isoformat(),
                    candidate_names=", ".join(candidate_names),
                    polling_json=json.dumps(race_json.get("polling", []), indent=2, default=str),
                ),
                model=small_model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=min(max_iterations, 10),
                phase_name=f"{'update-' if is_update else ''}polling",
                max_tokens=8192,
                extra_tools=POLLING_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
            )
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Polling phase failed: {exc}")
            _record_step_failure(race_json, "polling", _classify_exception(exc), str(exc))
        track("complete", "polling", duration_ms=int((time.perf_counter() - polling_t0) * 1000), race_json=race_json)
    else:
        track("skip", "polling")

    if step_enabled("forecast"):
        track("start", "forecast")
        forecast_t0 = time.perf_counter()
        log("info", f"{prefix} 4b: Generating race forecast...")
        try:
            compact_candidates = [
                {
                    "name": candidate.get("name"),
                    "party": candidate.get("party"),
                    "incumbent": candidate.get("incumbent", False),
                    "withdrawn": candidate.get("withdrawn", False),
                    "summary": candidate.get("summary", ""),
                    "donor_summary": candidate.get("donor_summary"),
                    "voting_summary": candidate.get("voting_summary"),
                }
                for candidate in race_json.get("candidates", [])
                if isinstance(candidate, dict)
            ]
            market_signals: list[dict[str, Any]] = []
            try:
                market_signals = await _await_with_run_budget(
                    fetch_kalshi_market_signals(race_id),
                    run_budget=run_budget,
                    requested_timeout=10.0,
                    operation="Kalshi market data fetch",
                )
                if market_signals:
                    log("info", f"  Forecast: loaded {len(market_signals)} Kalshi market signal(s)")
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Forecast: Kalshi market signals unavailable: {exc}")

            await _agent_loop(
                FORECAST_SYSTEM,
                FORECAST_USER.format(
                    race_id=race_id,
                    current_date=datetime.now(timezone.utc).date().isoformat(),
                    office=race_json.get("office") or "",
                    jurisdiction=race_json.get("jurisdiction") or "",
                    state=race_json.get("state") or "",
                    district=race_json.get("district") or "",
                    description=race_json.get("description") or "",
                    candidates_json=json.dumps(compact_candidates, indent=2, default=str),
                    polling_note=race_json.get("polling_note") or "",
                    polling_json=json.dumps(race_json.get("polling", []), indent=2, default=str),
                    market_signals_json=json.dumps(market_signals, indent=2, default=str),
                    forecast_json=json.dumps(race_json.get("forecast"), indent=2, default=str),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=min(max_iterations, 4),
                phase_name=f"{'update-' if is_update else ''}forecast",
                max_tokens=4096,
                extra_tools=FORECAST_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
                allow_search_tools=False,
            )
            if isinstance(race_json.get("forecast"), dict):
                race_json["forecast"]["model"] = model
                race_json["forecast"]["market_signals"] = market_signals
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Forecast phase failed: {exc}")
            _record_step_failure(race_json, "forecast", _classify_exception(exc), str(exc))
        track("complete", "forecast", duration_ms=int((time.perf_counter() - forecast_t0) * 1000), race_json=race_json)
    else:
        track("skip", "forecast")

    if step_enabled("voter_resources"):
        track("start", "voter_resources")
        resources_t0 = time.perf_counter()
        log("info", f"{prefix} 5: Verifying voter resources...")
        try:
            await _agent_loop(
                VOTER_RESOURCES_SYSTEM,
                VOTER_RESOURCES_USER.format(
                    race_id=race_id,
                    office=race_json.get("office") or "",
                    jurisdiction=race_json.get("jurisdiction") or "",
                    state=race_json.get("state") or "",
                ),
                model=small_model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=min(max_iterations, 8),
                phase_name=f"{'update-' if is_update else ''}voter-resources",
                max_tokens=4096,
                extra_tools=VOTER_RESOURCE_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
            )
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Voter resources phase failed: {exc}")
            _record_step_failure(race_json, "voter_resources", _classify_exception(exc), str(exc))
        track(
            "complete",
            "voter_resources",
            duration_ms=int((time.perf_counter() - resources_t0) * 1000),
            race_json=race_json,
        )
    else:
        track("skip", "voter_resources")


# ---------------------------------------------------------------------------
# Fresh run (new race)
# ---------------------------------------------------------------------------


async def _run_fresh(
    race_id: str,
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
    """Phase 1 → 2 → 3: Discovery → Issue research → Refinement."""
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
            + DISCOVERY_USER.format(race_id=race_id, current_date=datetime.now(timezone.utc).date().isoformat()),
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
    await _await_with_run_budget(
        _sync_ballotpedia_roster(race_json, race_id, log),
        run_budget=run_budget,
        requested_timeout=20.0,
        operation="Ballotpedia roster sync",
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
        is_update=False,
        last_updated="",
        refine_iters=refine_iters,
        log=log,
        resume_partial=resume_partial,
        continue_incomplete_work=continue_incomplete_work,
        run_budget=run_budget,
    )
    _sanitize_roster(race_json, log)

    return race_json


# ---------------------------------------------------------------------------
# Update run (existing race)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Review iteration
# ---------------------------------------------------------------------------


async def _run_iteration_pass(
    race_id: str,
    race_json: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    *,
    model: str,
    on_log: Any | None = None,
    on_progress: Any | None = None,
    max_iterations: int = 20,
    resume_partial: bool = False,
    unit_prefix: str = "iteration:1",
    run_budget: RunBudget | None = None,
) -> Optional[Dict[str, Any]]:
    """Run a single iteration pass addressing review flags (tools mode)."""
    log = make_logger(on_log)

    candidates = race_json.get("candidates", [])
    n = len(candidates)
    iterate_iters = _scale_iterations(max_iterations, n, per_candidate=5, minimum=15)
    iters_per_cand = max(10, iterate_iters // max(n, 1))

    log("info", f"  Iteration: addressing review flags for {n} candidates (tools mode)")

    working = copy.deepcopy(race_json)
    completed_units = _pipeline_completed_units(working)
    if not resume_partial:
        completed_units = {unit for unit in completed_units if not unit.startswith(f"{unit_prefix}:")}
        working["pipeline_state"]["completed_units"] = sorted(completed_units)

    candidate_units = [
        (index, candidate, f"{unit_prefix}:{_candidate_name(candidate)}")
        for index, candidate in enumerate(working.get("candidates", []))
        if isinstance(candidate, dict) and _candidate_name(candidate)
    ]
    expected_units = {unit for _, _, unit in candidate_units}

    def checkpoint_progress(label: str) -> None:
        if on_progress is None:
            return
        completed = len(expected_units & _pipeline_completed_units(working))
        pct = int(completed / max(len(expected_units), 1) * 100)
        on_progress(pct, label, working)

    all_tools = (
        ROSTER_TOOLS + CANDIDATE_TOOLS + ISSUE_TOOLS + RECORD_TOOLS + BACKGROUND_TOOLS + RACE_TOOLS + [READ_PROFILE_TOOL]
    )
    any_success = False

    for candidate_index, candidate, unit_id in candidate_units:
        if unit_id in completed_units:
            log("info", f"  Iteration checkpoint already complete for {_candidate_name(candidate)}; skipping")
            continue
        cname = _candidate_name(candidate)
        # Scoped to this candidate only: a mistaken candidate_name in a tool call during
        # this turn is rejected instead of silently corrupting a different candidate's data.
        handlers = _make_editing_handlers(working, log, restrict_to_candidate=cname)
        candidate_website, candidate_issue_urls = await _await_with_run_budget(
            _candidate_source_hints(working, cname),
            run_budget=run_budget,
            requested_timeout=20.0,
            operation="candidate source hint crawl",
        )
        issue_hint_text = ", ".join(candidate_issue_urls) if candidate_issue_urls else "(none found)"
        log("info", f"  Iterating on {cname}...")
        try:
            await _agent_loop(
                ITERATE_SYSTEM,
                ITERATE_USER.format(
                    race_id=race_id,
                    candidate_name=cname,
                    candidate_website=candidate_website,
                    candidate_issue_urls=issue_hint_text,
                    candidate_json=json.dumps(candidate, indent=2, default=str),
                    review_flags=_format_review_flags(
                        reviews,
                        candidate_index=candidate_index,
                        candidate_name=cname,
                        include_global=False,
                    ),
                    all_issues=", ".join(CANONICAL_ISSUES),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=iters_per_cand,
                phase_name=f"iterate-{cname[:20]}",
                max_tokens=8192,
                extra_tools=all_tools,
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
            )
            any_success = True
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Iteration failed for {cname}: {exc} — keeping existing")

        _mark_pipeline_unit_complete(working, unit_id)
        completed_units.add(unit_id)
        checkpoint_progress(f"Review iteration checkpoint: {cname}")

    log("info", "  Iterating on race metadata...")
    try:
        # Race-wide pass (not scoped to any single candidate) — RACE_TOOLS has no
        # candidate_name-taking tools, so an unrestricted handler set is correct here.
        meta_handlers = _make_editing_handlers(working, log)
        await _agent_loop(
            ITERATE_SYSTEM,
            ITERATE_META_USER.format(
                race_id=race_id,
                race_description=working.get("description", ""),
                polling_json=json.dumps(working.get("polling", []), indent=2, default=str),
                review_flags=_format_review_flags(reviews, include_global=True),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max(5, iters_per_cand // 2),
            phase_name="iterate-meta",
            max_tokens=4096,
            extra_tools=RACE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=meta_handlers,
            tools_mode=True,
            run_budget=run_budget,
        )
        any_success = True
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  Iteration meta failed: {exc} — keeping existing meta")

    if not any_success and not expected_units.issubset(_pipeline_completed_units(working)):
        log("warning", "  All iteration calls failed — keeping original")
        return None

    working.setdefault("id", race_id)
    return working
