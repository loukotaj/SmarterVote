"""Phase orchestration — discovery, issues, finance, refinement, iteration.

Contains the per-candidate issue sub-agent, shared phase runner, fresh and
update flow runners, and review-iteration logic.  Selection helpers live in
``selection.py``; patch/merge helpers live in ``patches.py``.
"""

import asyncio
import copy
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("pipeline")

from .ballotpedia import lookup_election_page as _ballotpedia_election_lookup
from .handlers import _make_editing_handlers
from .images import resolve_candidate_images
from .llm import _agent_loop, _ensure_dict, _normalize_candidate
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
    ISSUE_SUBAGENT_SYSTEM,
    ISSUE_SUBAGENT_USER,
    ITERATE_META_USER,
    ITERATE_SYSTEM,
    ITERATE_USER,
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
)
from .run_budget import RunBudget, RunBudgetExceeded
from .selection import (  # noqa: F401 — re-exported for backward compat
    _candidate_info_score,
    _candidate_source_hints,
    _scale_iterations,
    _select_candidates_for_research,
    _select_target_candidates,
)
from .tools import (
    BACKGROUND_TOOLS,
    CANDIDATE_TOOLS,
    ISSUE_TOOLS,
    RACE_TOOLS,
    READ_PROFILE_TOOL,
    RECORD_TOOLS,
    REMOVE_CANDIDATE_TOOL,
    ROSTER_TOOLS,
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
_INACTIVE_CANDIDATE_RE = re.compile(
    r"\b(withdrew|withdrawn|dropped out|suspended campaign|ended campaign|"
    r"disqualified|removed from the ballot|removed from ballot|"
    r"lost (?:the )?(?:democratic|republican|gop)? ?primary|"
    r"was defeated in (?:the )?(?:democratic|republican|gop)? ?primary|"
    r"did not advance from (?:the )?(?:democratic|republican|gop)? ?primary|"
    r"eliminated in (?:the )?(?:democratic|republican|gop)? ?primary)\b",
    re.IGNORECASE,
)
_GENERAL_ELECTION_SIGNAL_RE = re.compile(
    r"\b(nominee|won (?:the )?(?:democratic|republican|gop)? ?primary|"
    r"advanced to (?:the )?general(?: election)?|general election)\b",
    re.IGNORECASE,
)
MAX_RACE_CANDIDATES = 8
_MAJOR_PARTY_KEYS = ("democratic", "republican")
_CONTROL_FLOW_EXCEPTION_NAMES = {"AgentCancelled", "HandoffFailed", "HandoffTriggered", "RunBudgetExceeded"}


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
    if not isinstance(candidate, dict):
        return ""
    return str(candidate.get("name") or "").strip()


def _normalize_candidate_entries(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop malformed candidate entries before phase fan-out touches them."""
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return

    kept: List[Dict[str, Any]] = []
    dropped = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            dropped += 1
            continue
        name = _candidate_name(candidate)
        if not name:
            dropped += 1
            continue
        candidate["name"] = name
        kept.append(candidate)

    if dropped:
        race_json["candidates"] = kept
        if log:
            log("warning", f"Dropped {dropped} malformed candidate entr{'y' if dropped == 1 else 'ies'} before processing")


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
    """Drop candidates marked withdrawn or clearly described as primary-defeated/inactive."""
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

        text = _candidate_roster_text(candidate)
        if _INACTIVE_CANDIDATE_RE.search(text):
            removed.append(str(candidate.get("name") or "unknown"))
            continue

        kept.append(candidate)

    if removed:
        race_json["candidates"] = kept
        if log:
            log("warning", "Removed inactive candidates from discovery roster: " + ", ".join(removed))


def _candidate_party_key(candidate: Dict[str, Any]) -> str:
    """Normalize common party labels for roster balancing."""
    party = str(candidate.get("party") or "").lower()
    if "democrat" in party:
        return "democratic"
    if "republican" in party or party == "gop":
        return "republican"
    return "other"


def _candidate_cap_priority(candidate: Any) -> int:
    """Rank likely general-election candidates ahead of low-signal entries."""
    if not isinstance(candidate, dict):
        return 0

    score = 0
    if candidate.get("incumbent") is True:
        score += 40

    text = _candidate_roster_text(candidate)
    if _GENERAL_ELECTION_SIGNAL_RE.search(text):
        score += 30

    if isinstance(candidate.get("summary"), str) and candidate.get("summary", "").strip():
        score += 10

    issues = candidate.get("issues")
    if isinstance(issues, dict):
        populated_issues = sum(
            1
            for issue in issues.values()
            if isinstance(issue, dict)
            and str(issue.get("stance") or "").strip() not in {"", "MISSING", "No public position found"}
        )
        score += min(populated_issues, 5)

    links = candidate.get("links")
    if isinstance(links, list):
        score += min(len(links), 5)

    return score


def _rank_candidates_for_cap(candidates: List[Any]) -> List[Any]:
    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda item: (-_candidate_cap_priority(item[1]), item[0]))
    return [candidate for _, candidate in indexed]


def _norm_name_for_match(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _names_likely_same(left: str, right: str) -> bool:
    left_norm = _norm_name_for_match(left)
    right_norm = _norm_name_for_match(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    left_parts = left_norm.split()
    right_parts = right_norm.split()
    if len(left_parts) < 2 or len(right_parts) < 2:
        return False
    if left_parts[-1] != right_parts[-1]:
        return False
    return left_parts[0].startswith(right_parts[0]) or right_parts[0].startswith(left_parts[0])


def _candidate_matches_any(name: str, roster: List[Dict[str, Any]]) -> bool:
    return any(_names_likely_same(name, str(candidate.get("name") or "")) for candidate in roster)


def _reconcile_candidates_with_authoritative_roster(
    race_json: Dict[str, Any],
    authoritative_candidates: List[Dict[str, Any]],
    log: Any | None = None,
) -> None:
    """Remove stale candidates missing from Ballotpedia's current election roster."""
    if not authoritative_candidates:
        return
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return

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
        removed.append(name)

    if removed:
        race_json["candidates"] = kept
        if log:
            log(
                "warning",
                "Removed candidates absent from current Ballotpedia election roster: " + ", ".join(removed),
            )


async def _sync_ballotpedia_roster(race_json: Dict[str, Any], race_id: str, log: Any | None = None) -> None:
    """Apply Ballotpedia election-page roster data when available."""
    try:
        bp_result = await _ballotpedia_election_lookup(race_id)
    except Exception as exc:
        if log:
            log("debug", f"  Ballotpedia roster sync failed: {exc}")
        return

    if not isinstance(bp_result, dict) or not bp_result.get("found"):
        return
    page_url = bp_result.get("page_url")
    if page_url and not race_json.get("ballotpedia_url"):
        race_json["ballotpedia_url"] = page_url
        if log:
            log("info", f"  Auto-set ballotpedia_url: {page_url}")
    bp_candidates = bp_result.get("candidates")
    if isinstance(bp_candidates, list):
        authoritative = [
            candidate for candidate in bp_candidates if isinstance(candidate, dict) and _candidate_name(candidate)
        ]
        if len(authoritative) >= 2:
            _reconcile_candidates_with_authoritative_roster(race_json, authoritative, log)


def _select_capped_candidates(candidates: List[Any], limit: int) -> List[Any]:
    """Select a bounded roster while avoiding one crowded primary field dominating."""
    if len(candidates) <= limit:
        return candidates

    buckets: Dict[str, List[Any]] = {"democratic": [], "republican": [], "other": []}
    for candidate in candidates:
        if isinstance(candidate, dict):
            buckets[_candidate_party_key(candidate)].append(candidate)
        else:
            buckets["other"].append(candidate)

    if all(buckets[key] for key in _MAJOR_PARTY_KEYS):
        per_major_party = max(1, limit // len(_MAJOR_PARTY_KEYS))
        ranked_democratic = _rank_candidates_for_cap(buckets["democratic"])
        ranked_republican = _rank_candidates_for_cap(buckets["republican"])
        selected = ranked_democratic[:per_major_party] + ranked_republican[:per_major_party]
        selected_ids = {id(candidate) for candidate in selected}
        for candidate in _rank_candidates_for_cap(candidates):
            if len(selected) >= limit:
                break
            if id(candidate) not in selected_ids:
                selected.append(candidate)
                selected_ids.add(id(candidate))
        selected_ids = {id(candidate) for candidate in selected[:limit]}
        return [candidate for candidate in candidates if id(candidate) in selected_ids][:limit]

    selected_ids = {id(candidate) for candidate in _rank_candidates_for_cap(candidates)[:limit]}
    return [candidate for candidate in candidates if id(candidate) in selected_ids][:limit]


def _enforce_candidate_cap(race_json: Dict[str, Any], log: Any | None = None, *, limit: int = MAX_RACE_CANDIDATES) -> None:
    """Keep race profiles bounded until primary-specific race modeling exists."""
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list) or len(candidates) <= limit:
        return

    kept = _select_capped_candidates(candidates, limit)
    kept_ids = {id(candidate) for candidate in kept}
    dropped = [candidate for candidate in candidates if id(candidate) not in kept_ids]
    race_json["candidates"] = kept
    dropped_names = [str(c.get("name") or "unknown") for c in dropped if isinstance(c, dict)]
    race_json["candidate_limit_note"] = (
        f"Candidate list capped at {limit} active candidates for this race. "
        "Selection is balanced across major-party fields where possible; future primary-specific race pages should split "
        "large primary fields."
    )
    if log:
        log(
            "warning",
            f"Candidate roster capped at {limit}; skipped {len(dropped)} candidates"
            + (f": {', '.join(dropped_names)}" if dropped_names else ""),
        )


def _backfill_source_timestamps(race_json: Dict[str, Any]) -> None:
    """Backfill missing last_accessed on legacy source objects loaded from checkpoints.

    Old data saved before the last_accessed field was made required will fail schema
    validation.  This sets a fallback ISO-8601 timestamp so validation passes.
    """
    from datetime import datetime, timezone

    fallback = datetime.now(timezone.utc).isoformat()
    source_list_keys = ("summary_sources", "donor_sources", "voting_sources")
    for candidate in race_json.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        for key in source_list_keys:
            for src in candidate.get(key) or []:
                if isinstance(src, dict) and not src.get("last_accessed"):
                    src["last_accessed"] = fallback
        for issue_data in (candidate.get("issues") or {}).values():
            if not isinstance(issue_data, dict):
                continue
            for src in issue_data.get("sources") or []:
                if isinstance(src, dict) and not src.get("last_accessed"):
                    src["last_accessed"] = fallback


def _sanitize_roster(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Apply deterministic roster constraints before downstream fan-out."""
    _normalize_candidate_entries(race_json, log)
    _remove_ineligible_officeholders(race_json, log)
    _remove_inactive_candidates(race_json, log)
    _enforce_candidate_cap(race_json, log)


def _build_handoff_context(
    handoffs: List[Dict[str, Any]],
    cached_info: Dict[str, Any] | None,
) -> str:
    """Build a handoff context string for the issue sub-agent."""
    parts: List[str] = []

    recent = handoffs if handoffs else []
    if recent:
        parts.append("Previous stances already written for this candidate:")
        for h in recent:
            parts.append(f"  - {h['issue']}: {h['stance'][:120]} [{h['confidence']}]")
        parts.append("")

    if cached_info:
        searches = cached_info.get("searches", [])
        if searches:
            parts.append(f"Cached search queries available (results served instantly, {len(searches)} total):")
            for s in searches[:5]:
                parts.append(f"  - \"{s['query']}\"")
            parts.append("")

    return "\n".join(parts) if parts else "No prior context available."


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

    for issue_idx, issue in enumerate(CANONICAL_ISSUES):
        existing_issue_data: Dict[str, Any] | None = None
        for c in race_json.get("candidates", []):
            if isinstance(c, dict) and c.get("name") == candidate_name:
                sd = c.get("issues", {}).get(issue)
                if isinstance(sd, dict) and sd.get("stance"):
                    existing_issue_data = sd
                break

        if resume_partial and existing_issue_data is not None:
            log("info", f"    Issue {issue_idx + 1}/12: {issue} already present; skipping")
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

        log("info", f"    Issue {issue_idx + 1}/12: {issue}")

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
        except RuntimeError as exc:
            if _is_control_flow_exception(exc):
                raise
            error_msg = str(exc)
            if "policy violation" in error_msg.lower():
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
    run_budget: RunBudget | None = None,
) -> None:
    """Run images, issues, finance, and refinement phases.

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
        research_names = _select_candidates_for_research(
            candidate_names,
            race_json,
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            log=log,
        )
        rn = len(research_names)
        n_issues = len(CANONICAL_ISSUES)
        total_units = max(rn * n_issues, 1)
        log("info", f"{prefix} 2: Researching issues for {rn} candidates ({n_issues} issues each)...")
        for ci, cand_name in enumerate(research_names):
            log("info", f"  {'Updating' if is_update else 'Researching'} issues for {cand_name}...")

            def _make_issue_tracker(ci=ci, cand_name=cand_name):
                def _on_issue(issue_idx: int, issue: str) -> None:
                    combined_pct = int((ci * n_issues + issue_idx) / total_units * 100)
                    track(
                        "progress",
                        "issues",
                        pct=combined_pct,
                        message=f"Issues · {cand_name} ({ci + 1}/{rn}) · {issue} ({issue_idx + 1}/{n_issues})",
                    )

                return _on_issue

            def _make_issue_checkpoint(ci=ci, cand_name=cand_name):
                def _on_issue_checkpoint(issue_idx: int, issue: str) -> None:
                    combined_pct = int((ci * n_issues + issue_idx + 1) / total_units * 100)
                    track(
                        "progress",
                        "issues",
                        pct=combined_pct,
                        message=f"Issues checkpoint - {cand_name} ({ci + 1}/{rn}) - {issue} ({issue_idx + 1}/{n_issues})",
                        race_json=race_json,
                    )

                return _on_issue_checkpoint

            await _run_issue_research_for_candidate(
                cand_name,
                race_json,
                race_id=race_id,
                model=small_model,
                on_log=on_log,
                max_iterations=max_iterations,
                is_update=is_update,
                last_updated=last_updated,
                on_issue_progress=_make_issue_tracker(),
                on_issue_checkpoint=_make_issue_checkpoint(),
                resume_partial=resume_partial,
                run_budget=run_budget,
            )
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
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Finance/voting phase failed: {exc} — continuing without")
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
        log("info", f"{prefix} 3: Refining profile (one candidate at a time, tools mode)...")
        for ci, candidate in enumerate(cand_list):
            cname = candidate["name"]
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

        # Meta refinement (description + polling) — tools mode
        log("info", "  Refining race metadata...")
        try:
            await _agent_loop(
                REFINE_SYSTEM,
                REFINE_META_USER.format(
                    race_id=race_id,
                    race_description=race_json.get("description", ""),
                    polling_json=json.dumps(race_json.get("polling", []), indent=2, default=str),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=max(6, refine_iters // 3),
                phase_name=f"{'upd-' if is_update else ''}refine-meta",
                max_tokens=4096,
                extra_tools=RACE_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
                run_budget=run_budget,
            )
        except RunBudgetExceeded:
            raise
        except Exception as exc:
            log("warning", f"  Refine meta failed: {exc} — keeping existing meta")
        track("complete", "refinement", duration_ms=int((time.perf_counter() - ref_t0) * 1000), race_json=race_json)
    else:
        log("info", f"{prefix} 3: Refinement — SKIPPED")
        track("skip", "refinement")


# ---------------------------------------------------------------------------
# Fresh run (new race)
# ---------------------------------------------------------------------------


async def _run_fresh(
    race_id: str,
    *,
    model: str,
    small_model: str,
    on_log: Any | None = None,
    max_iterations: int = 15,
    step_enabled: Any = None,
    track: Any = None,
    max_candidates: Optional[int] = None,
    target_no_info: bool = False,
    target_candidate_names: Optional[List[str]] = None,
    goal: Optional[str] = None,
    resume_partial: bool = False,
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
            (f"## Run Goal\n{goal}\n\n" if goal else "") + DISCOVERY_USER.format(race_id=race_id),
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
    on_log: Any | None = None,
    max_iterations: int = 15,
    step_enabled: Any = None,
    track: Any = None,
    max_candidates: Optional[int] = None,
    target_no_info: bool = False,
    target_candidate_names: Optional[List[str]] = None,
    goal: Optional[str] = None,
    resume_partial: bool = False,
    roster_only: bool = False,
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
            on_log=on_log,
            max_iterations=max_iterations,
            step_enabled=step_enabled,
            track=track,
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            target_candidate_names=target_candidate_names,
            resume_partial=resume_partial,
            run_budget=run_budget,
        )

    refine_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=12)
    handlers = _make_editing_handlers(race_json, log)

    # --- Phase 0+1: Discovery (roster sync + meta update) ---
    if step_enabled("discovery"):
        track("start", "discovery")
        disc_t0 = time.perf_counter()

        log("info", "Update Phase 0: Verifying candidate roster...")
        pre_sync_names = list(candidate_names)
        try:
            await _agent_loop(
                ROSTER_SYNC_SYSTEM,
                ROSTER_SYNC_USER.format(
                    race_id=race_id,
                    last_updated=last_updated,
                    candidate_names=", ".join(candidate_names),
                ),
                model=small_model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=max(12, max_iterations // 2),
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

        _sanitize_roster(race_json, log)
        await _await_with_run_budget(
            _sync_ballotpedia_roster(race_json, race_id, log),
            run_budget=run_budget,
            requested_timeout=20.0,
            operation="Ballotpedia roster sync",
        )
        _sanitize_roster(race_json, log)

        # Roster verify: use the primary model (at least mini) to spot-check any
        # candidates added by the cheaper small_model during sync.
        post_sync_names = [_candidate_name(c) for c in race_json.get("candidates", []) if _candidate_name(c)]
        added_names = [n for n in post_sync_names if n not in pre_sync_names]
        if added_names:
            log("info", f"  Roster verify: checking {len(added_names)} added candidate(s): {', '.join(added_names)}")
            try:
                await _agent_loop(
                    ROSTER_VERIFY_SYSTEM,
                    ROSTER_VERIFY_USER.format(
                        race_id=race_id,
                        candidate_names=", ".join(post_sync_names),
                        original_names=", ".join(pre_sync_names),
                        added_names=", ".join(added_names),
                    ),
                    model=model,
                    on_log=on_log,
                    race_id=race_id,
                    max_iterations=6,
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
        else:
            log("info", "  Roster verify: no candidates added during sync — skipping")

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
                run_budget=run_budget,
            )

        if roster_only:
            log("info", "Update Phase 1: Metadata refresh skipped for discovery-only roster run")
        else:
            track("progress", "discovery", pct=50, message="Discovery: updating race metadata")

            # --- Phase 1: Meta update (tools mode) ---
            meta_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=10)
            log("info", "Update Phase 1: Searching for new summaries, donors, polls, voting records...")
            try:
                await _agent_loop(
                    UPDATE_META_SYSTEM,
                    UPDATE_META_USER.format(
                        race_id=race_id,
                        last_updated=last_updated,
                        candidate_names=", ".join(candidate_names),
                    ),
                    model=model,
                    on_log=on_log,
                    race_id=race_id,
                    max_iterations=meta_iters,
                    phase_name="update-meta",
                    max_tokens=16384,
                    extra_tools=RACE_TOOLS + CANDIDATE_TOOLS + RECORD_TOOLS + [READ_PROFILE_TOOL],
                    extra_tool_handlers=handlers,
                    tools_mode=True,
                    run_budget=run_budget,
                )
            except RunBudgetExceeded:
                raise
            except Exception as exc:
                log("warning", f"  Update meta phase failed: {exc} — keeping existing meta")

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
        run_budget=run_budget,
    )
    _sanitize_roster(race_json, log)

    return race_json


# ---------------------------------------------------------------------------
# Review iteration
# ---------------------------------------------------------------------------


def _format_review_flags(reviews: List[Dict[str, Any]]) -> str:
    """Format review flags into a readable text block for the iteration prompt."""
    lines = []
    for review in reviews:
        model = review.get("model", "unknown")
        verdict = review.get("verdict", "unknown")
        lines.append(f"\n--- Review by {model} (verdict: {verdict}) ---")
        if review.get("summary"):
            lines.append(f"Summary: {review['summary']}")
        for flag in review.get("flags", []):
            severity = flag.get("severity", "info").upper()
            field = flag.get("field", "?")
            concern = flag.get("concern", "")
            suggestion = flag.get("suggestion", "")
            lines.append(f"  [{severity}] {field}: {concern}")
            if suggestion:
                lines.append(f"    Suggestion: {suggestion}")
    return "\n".join(lines) if lines else "  (no specific flags)"


def _has_actionable_flags(
    reviews: List[Dict[str, Any]],
    min_severity: str = "warning",
    exclude_fields: set | None = None,
) -> bool:
    """Return True if any review has actionable flags at or above *min_severity*."""
    severity_rank = {"info": 0, "warning": 1, "error": 2}
    threshold = severity_rank.get(min_severity, 1)
    _excluded = exclude_fields or set()
    for review in reviews:
        for flag in review.get("flags", []):
            rank = severity_rank.get(flag.get("severity", "info"), 0)
            if rank >= threshold and flag.get("field", "") not in _excluded:
                return True
    return False


async def _run_iteration_pass(
    race_id: str,
    race_json: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    *,
    model: str,
    on_log: Any | None = None,
    max_iterations: int = 20,
    run_budget: RunBudget | None = None,
) -> Optional[Dict[str, Any]]:
    """Run a single iteration pass addressing review flags (tools mode)."""
    log = make_logger(on_log)

    flags_text = _format_review_flags(reviews)
    candidates = race_json.get("candidates", [])
    n = len(candidates)
    iterate_iters = _scale_iterations(max_iterations, n, per_candidate=5, minimum=15)
    iters_per_cand = max(10, iterate_iters // max(n, 1))

    log("info", f"  Iteration: addressing review flags for {n} candidates (tools mode)")

    working = copy.deepcopy(race_json)
    handlers = _make_editing_handlers(working, log)
    all_tools = (
        ROSTER_TOOLS + CANDIDATE_TOOLS + ISSUE_TOOLS + RECORD_TOOLS + BACKGROUND_TOOLS + RACE_TOOLS + [READ_PROFILE_TOOL]
    )
    any_success = False

    for candidate in working.get("candidates", []):
        if not isinstance(candidate, dict) or not _candidate_name(candidate):
            continue
        cname = _candidate_name(candidate)
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
                    review_flags=flags_text,
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

    log("info", "  Iterating on race metadata...")
    try:
        await _agent_loop(
            ITERATE_SYSTEM,
            ITERATE_META_USER.format(
                race_id=race_id,
                race_description=working.get("description", ""),
                polling_json=json.dumps(working.get("polling", []), indent=2, default=str),
                review_flags=flags_text,
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max(5, iters_per_cand // 2),
            phase_name="iterate-meta",
            max_tokens=4096,
            extra_tools=RACE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
            run_budget=run_budget,
        )
        any_success = True
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  Iteration meta failed: {exc} — keeping existing meta")

    if not any_success:
        log("warning", "  All iteration calls failed — keeping original")
        return None

    working.setdefault("id", race_id)
    return working
