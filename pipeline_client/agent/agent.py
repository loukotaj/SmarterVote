"""Multi-phase candidate research agent with web search & caching.

Phases (fresh run):
1. **Discovery** - identify the race, candidates, career history, images.
1b. **Image resolution** - verify/find direct image URLs per candidate.
2. **Issue research** - 12 per-candidate sub-agent calls (one per canonical issue).
2b. **Finance & voting** - dedicated donor and voting-record research.
3. **Refinement** - tools-mode per-candidate and meta cleanup.
4. **Review** (optional) - send to Claude, Gemini, and Grok for fact-checking.
5. **Iteration** - tools-mode pass to address review flags (up to 2 cycles).

Update run adds Phase 0 (roster sync) before Phase 1 (meta update).

Uses a SQLite search cache (``pipeline_client.agent.search_cache``) to avoid
redundant Serper API calls across runs.  Token usage and estimated USD cost
are attached to the output JSON under ``agent_metrics``.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cost import _cost_ctx, estimate_cost
from .handlers import _make_editing_handlers  # noqa: F401 - re-exported for tests
from .llm import (  # noqa: F401 - re-exported for backward compat
    CHEAP_MODEL,
    DEFAULT_MODEL,
    NANO_MODEL,
    _agent_loop,
    _call_openai,
    _ensure_dict,
    _normalize_candidate,
)
from .phases import (  # noqa: F401 - re-exported for backward compat
    _candidate_source_hints,
    _has_actionable_flags,
    _run_fresh,
    _run_iteration_pass,
    _run_update,
    _scale_iterations,
    _select_target_candidates,
)
from .review import compute_validation_grade, run_reviews
from .tools import (  # noqa: F401 - re-exported for tests
    ADD_CANDIDATE_TOOL,
    ADD_LINK_TOOL,
    ADD_POLL_TOOL,
    BACKGROUND_TOOLS,
    BALLOTPEDIA_ELECTION_TOOL,
    BALLOTPEDIA_TOOL,
    CANDIDATE_TOOLS,
    FETCH_TOOL,
    ISSUE_TOOLS,
    RACE_TOOLS,
    READ_PROFILE_TOOL,
    RECORD_TOOLS,
    REMOVE_CANDIDATE_TOOL,
    RENAME_CANDIDATE_TOOL,
    ROSTER_TOOLS,
    SEARCH_TOOL,
    SET_CANDIDATE_FIELD_TOOL,
    SET_CANDIDATE_SUMMARY_TOOL,
    SET_DONOR_SUMMARY_TOOL,
    SET_ISSUE_STANCE_TOOL,
    SET_VOTING_SUMMARY_TOOL,
    UPDATE_RACE_FIELD_TOOL,
)
from .utils import _extract_json, make_logger  # noqa: F401 - _extract_json re-exported for tests
from .web_tools import (  # noqa: F401 - re-exported for backward compat
    _fetch_page,
    _get_fetch_client,
    _get_search_cache,
    _is_unusable_page_text,
    _page_fetch_log_hint,
    _serper_search,
)

logger = logging.getLogger("pipeline")

_PLACEHOLDER_CANDIDATE_NAMES = {"", "unknown", "tbd", "to be determined", "n/a", "na", "none"}


# ---------------------------------------------------------------------------
# Load existing published data for rerun/update mode
# ---------------------------------------------------------------------------


def _load_existing(race_id: str) -> Optional[Dict[str, Any]]:
    """Load an existing RaceJSON if it exists (drafts first, then published)."""
    base = Path(__file__).resolve().parents[2] / "data"
    for subdir in ("drafts", "published"):
        path = base / subdir / f"{race_id}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    return None


def _candidate_name(candidate: Any) -> str:
    if not isinstance(candidate, dict):
        return ""
    return str(candidate.get("name") or "").strip()


def _is_placeholder_candidate_name(name: str) -> bool:
    return name.strip().lower() in _PLACEHOLDER_CANDIDATE_NAMES


def _sanitize_polling(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Normalize malformed polling entries before validation and draft save."""
    polling = race_json.get("polling")
    if polling is None:
        race_json["polling"] = []
        return
    if not isinstance(polling, list):
        if log:
            log("warning", "Polling field was not a list; dropping malformed polling data")
        race_json["polling"] = []
        return

    for poll_index, poll in enumerate(polling):
        if not isinstance(poll, dict):
            continue
        matchups = poll.get("matchups")
        if matchups is None:
            poll["matchups"] = []
            continue
        if not isinstance(matchups, list):
            if log:
                log("warning", f"Poll {poll_index} matchups was not a list; dropping malformed matchups")
            poll["matchups"] = []
            continue
        for matchup_index, matchup in enumerate(matchups):
            if not isinstance(matchup, dict):
                continue
            percentages = matchup.get("percentages")
            if percentages is None:
                matchup["percentages"] = []
                if log:
                    log(
                        "warning",
                        f"Poll {poll_index} matchup {matchup_index} had null percentages; normalized to an empty list",
                    )
                continue
            if not isinstance(percentages, list):
                matchup["percentages"] = []
                if log:
                    log(
                        "warning",
                        f"Poll {poll_index} matchup {matchup_index} percentages was not a list; normalized to an empty list",
                    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_agent(
    race_id: str,
    *,
    on_log: Any | None = None,
    cheap_mode: bool = True,
    max_iterations: int = 20,
    existing_data: Optional[Dict[str, Any]] = None,
    research_model: Optional[str] = None,
    claude_model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    grok_model: Optional[str] = None,
    enabled_steps: Optional[List[str]] = None,
    step_tracker: Optional[Dict[str, Any]] = None,
    max_candidates: Optional[int] = None,
    target_no_info: bool = False,
    candidate_names: Optional[List[str]] = None,
    goal: Optional[str] = None,
    resume_partial: bool = False,
) -> Dict[str, Any]:
    """Run the multi-phase research agent for a given race_id.

    Parameters
    ----------
    race_id : str
        Race slug, e.g. ``"mo-senate-2024"``.
    on_log : callable, optional
        ``(level, message) -> None`` callback for streaming logs.
    cheap_mode : bool
        When *True*, use cheaper/faster model variants (``gpt-5.4-mini``).
    max_iterations : int
        Safety limit on each phase's tool-call loop.
    existing_data : dict, optional
        An existing RaceJSON to update/improve. When *None* (default),
        the agent checks ``data/published/{race_id}.json`` for a previously
        published profile and enters update mode if found.
        Pass an empty dict to force a fresh research run.
    research_model : str, optional
        Override the OpenAI model for research phases.
    claude_model / gemini_model / grok_model : str, optional
        Override individual review models.
    enabled_steps : list[str], optional
        Step names to run (from PipelineStep enum). None = all steps.
    step_tracker : dict, optional
        Callbacks: ``start(step)``, ``complete(step, duration_ms)``,
        ``skip(step)``, ``progress(step, pct)`` for structured tracking.
    max_candidates : int, optional
        Max number of candidates to research in the issues phase.
        *None* (default) researches all. Candidates are ranked by existing
        info density; the top *max_candidates* are researched.
    target_no_info : bool
        When *True*, prioritise candidates with the least existing info.
    candidate_names : list[str], optional
        Exact candidate names to update/research (case-insensitive exact match).
    resume_partial : bool
        When True, issue research skips candidate/issue stances already present
        in existing_data. Used by Cloud Function continuation handoff.
    """
    from .cost import (
        CHEAP_CLAUDE_MODEL,
        CHEAP_GEMINI_MODEL,
        CHEAP_GROK_MODEL,
        DEFAULT_CLAUDE_MODEL,
        DEFAULT_GEMINI_MODEL,
        DEFAULT_GROK_MODEL,
    )

    model = research_model or (CHEAP_MODEL if cheap_mode else DEFAULT_MODEL)
    # Sub-task model: nano in cheap mode, mini in normal mode (full model reserved for synthesis).
    small_model = NANO_MODEL if cheap_mode else CHEAP_MODEL
    log = make_logger(on_log)
    t0 = time.perf_counter()

    # Step enablement check - None means all enabled
    _all_steps = {"discovery", "images", "issues", "finance", "refinement", "review", "iteration"}
    _enabled = set(enabled_steps) if enabled_steps else _all_steps

    def _step_enabled(step: str) -> bool:
        return step in _enabled

    def _track(action: str, step: str, **kwargs):
        if step_tracker and action in step_tracker:
            try:
                step_tracker[action](step, **kwargs)
            except Exception as _e:
                logger.debug("Step tracker callback '%s' for '%s' failed: %s", action, step, _e)

    # Initialise a fresh cost accumulator for this run
    _acc: Dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0}
    _ctx_token = _cost_ctx.set(_acc)

    if existing_data is None:
        existing_data = _load_existing(race_id)

    if existing_data:
        log("info", f"Update mode for {race_id} (model={model}, small_model={small_model})")
        if goal:
            log("info", f"Run goal: {goal}")
        race_json = await _run_update(
            race_id,
            existing_data,
            model=model,
            small_model=small_model,
            on_log=on_log,
            max_iterations=max_iterations,
            step_enabled=_step_enabled,
            track=_track,
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            target_candidate_names=candidate_names,
            goal=goal,
            resume_partial=resume_partial,
        )
    else:
        log("info", f"New research for {race_id} (model={model}, small_model={small_model})")
        if goal:
            log("info", f"Run goal: {goal}")
        race_json = await _run_fresh(
            race_id,
            model=model,
            small_model=small_model,
            on_log=on_log,
            max_iterations=max_iterations,
            step_enabled=_step_enabled,
            track=_track,
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            target_candidate_names=candidate_names,
            goal=goal,
            resume_partial=resume_partial,
        )

    # LLMs sometimes wrap their output in {"race_json": {...}} - unwrap it so
    # metadata we add below lands at the top level, not buried inside a key.
    if "race_json" in race_json and isinstance(race_json.get("race_json"), dict):
        log("warning", "LLM wrapped output in 'race_json' key; unwrapping")
        race_json = race_json["race_json"]

    race_json.setdefault("id", race_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    race_json["updated_utc"] = now_iso

    should_review = _step_enabled("review")
    should_iterate = should_review and _step_enabled("iteration")

    # Record the models actually used (deduplicated - nano == model in full mode)
    generators = list(dict.fromkeys([model, small_model]))  # preserves order, drops duplicates
    if should_review:
        if os.getenv("ANTHROPIC_API_KEY"):
            generators.append(claude_model or (CHEAP_CLAUDE_MODEL if cheap_mode else DEFAULT_CLAUDE_MODEL))
        if os.getenv("GEMINI_API_KEY"):
            generators.append(gemini_model or (CHEAP_GEMINI_MODEL if cheap_mode else DEFAULT_GEMINI_MODEL))
        if os.getenv("XAI_API_KEY"):
            generators.append(grok_model or (CHEAP_GROK_MODEL if cheap_mode else DEFAULT_GROK_MODEL))
    race_json["generator"] = generators

    for candidate in race_json.get("candidates", []):
        if isinstance(candidate, dict):
            _normalize_candidate(candidate, now_iso)

    race_json.setdefault("polling", [])
    _sanitize_polling(race_json, log)

    if should_review:
        _track("start", "review")
        review_t0 = time.perf_counter()
        log("info", "Phase 4: Sending to review agents (Claude, Gemini, Grok)...")
        reviews = await run_reviews(
            race_id,
            race_json,
            on_log=on_log,
            cheap_mode=cheap_mode,
            claude_model=claude_model,
            gemini_model=gemini_model,
            grok_model=grok_model,
        )
        race_json["reviews"] = reviews
        # Log review results to live logs
        for rev in reviews:
            model_name = rev.get("model", "unknown")
            verdict = rev.get("verdict", "?")
            score = rev.get("score", "?")
            summary = rev.get("summary", "")
            n_flags = len(rev.get("flags", []))
            log("info", f"  {model_name}: {verdict} (score {score}/100, {n_flags} flags)")
            if summary:
                log("info", f"    -> {summary}")
        _track("complete", "review", duration_ms=int((time.perf_counter() - review_t0) * 1000), race_json=race_json)

        # --- Phase 5: Iterate on review feedback (up to 2 cycles) ---
        if should_iterate:
            _track("start", "iteration")
            iter_t0 = time.perf_counter()
            max_review_cycles = 2
            did_iterate = False
            for cycle in range(1, max_review_cycles + 1):
                # Cycle 2+: only iterate on error-severity flags to break subjective loops
                min_severity = "error" if cycle > 1 else "warning"
                if not _has_actionable_flags(reviews, min_severity=min_severity):
                    if cycle == 1:
                        log("info", "  No actionable review flags; skipping iteration")
                    else:
                        log("info", f"  Cycle {cycle}: no remaining {min_severity}+ flags; done")
                    break

                did_iterate = True
                log("info", f"Phase 5 (cycle {cycle}/{max_review_cycles}): Iterating on review feedback...")
                _track("progress", "iteration", pct=int(cycle / max_review_cycles * 80))
                # Split iteration budget: 60% cycle 1, 40% cycle 2
                cycle_budget = int(max_iterations * (0.6 if cycle == 1 else 0.4))
                improved = await _run_iteration_pass(
                    race_id,
                    race_json,
                    reviews,
                    model=model,
                    on_log=on_log,
                    max_iterations=max(cycle_budget, 14),
                )
                if improved is not None:
                    race_json = improved
                    # Re-normalize after iteration
                    now_iso = datetime.now(timezone.utc).isoformat()
                    race_json["updated_utc"] = now_iso
                    for candidate in race_json.get("candidates", []):
                        if isinstance(candidate, dict):
                            _normalize_candidate(candidate, now_iso)
                    race_json["generator"] = generators

                    log("info", f"  Cycle {cycle}: Re-running reviews...")
                    reviews = await run_reviews(
                        race_id,
                        race_json,
                        on_log=on_log,
                        cheap_mode=cheap_mode,
                        claude_model=claude_model,
                        gemini_model=gemini_model,
                        grok_model=grok_model,
                    )
                    race_json["reviews"] = reviews
                    for rev in reviews:
                        model_name = rev.get("model", "unknown")
                        verdict = rev.get("verdict", "?")
                        score = rev.get("score", "?")
                        summary = rev.get("summary", "")
                        n_flags = len(rev.get("flags", []))
                        log("info", f"  {model_name}: {verdict} (score {score}/100, {n_flags} flags)")
                        if summary:
                            log("info", f"    -> {summary}")
                else:
                    log("warning", f"  Cycle {cycle}: iteration failed; stopping")
                    break
            if not did_iterate:
                _track("skip", "iteration")
            else:
                _track("complete", "iteration", duration_ms=int((time.perf_counter() - iter_t0) * 1000), race_json=race_json)
        else:
            _track("skip", "iteration")
    else:
        race_json.setdefault("reviews", [])
        _track("skip", "review")
        _track("skip", "iteration")

    # Compute aggregate validation grade from review scores
    grade = compute_validation_grade(race_json.get("reviews", []))
    race_json["validation_grade"] = grade

    elapsed = time.perf_counter() - t0

    # Compute and attach cost estimate (covers all LLMs: OpenAI + review providers)
    _cost_ctx.reset(_ctx_token)
    pt = _acc["prompt_tokens"]
    ct = _acc["completion_tokens"]
    total_tokens = pt + ct
    breakdown = _acc.get("model_breakdown", {})
    total_cost = (
        sum(estimate_cost(m, bd.get("prompt_tokens", 0), bd.get("completion_tokens", 0)) for m, bd in breakdown.items())
        if breakdown
        else estimate_cost(model, pt, ct)
    )
    agent_metrics = {
        "model": model,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": total_tokens,
        "estimated_usd": round(total_cost, 4),
        "model_breakdown": breakdown,
        "duration_s": round(elapsed, 1),
    }
    race_json["agent_metrics"] = agent_metrics
    log(
        "info",
        f"Agent finished in {elapsed:.1f}s; "
        f"${total_cost:.4f} estimated "
        f"({pt:,} in + {ct:,} out = {total_tokens:,} tokens)",
    )

    # Sanity-check: reject partial LLM output (e.g. a stray polling entry)
    _candidates = race_json.get("candidates")
    if not isinstance(_candidates, list):
        raise ValueError(
            f"Agent output for '{race_id}' has no 'candidates'; looks like a partial "
            f"LLM response was returned instead of the full race profile. "
            f"Top-level keys present: {list(race_json.keys())}. Re-queue the race to retry."
        )
    _candidate_names = [_candidate_name(candidate) for candidate in _candidates]
    if not _candidate_names or all(_is_placeholder_candidate_name(name) for name in _candidate_names):
        raise ValueError(
            f"Agent output for '{race_id}' only contains placeholder candidate names: {_candidate_names}. "
            "Refusing to save a draft that cannot identify any real candidate."
        )

    # Full schema validation against RaceJSON — soft check so later phases
    # (refinement, iteration) can still fix issues.  Log every validation
    # error but never hard-fail here.
    try:
        from shared.models import RaceJSON as _RaceJSONModel

        _RaceJSONModel.model_validate(race_json)
        log("info", "Schema validation passed; output conforms to RaceJSON v0.3")
    except Exception as schema_exc:
        log("warning", f"Schema validation warnings (non-fatal): {schema_exc}")

    return race_json
