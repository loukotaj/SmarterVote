"""Multi-phase candidate research agent with web search & caching.

Phases (fresh run):
1.  Discovery        — identify the race, candidates, career history, images.
1b. Image resolution — verify/find direct image URLs per candidate.
2.  Issue research   — 12 per-candidate sub-agent calls (one per canonical issue).
2b. Finance          — dedicated donor and voting-record research.
3.  Refinement       — tools-mode per-candidate and meta cleanup.
3b. Polling          — fetch and attach available polling data.
3c. Forecast         — generate chamber outcome forecast.
3d. Voter resources  — compile local registration and voting info.
4.  Review     (optional) — send to enabled OpenRouter reviewer roles for fact-checking.
5.  Iteration        — tools-mode pass to address review flags (one cycle by default; up to three for errors).

Update run adds Phase 0 (roster sync) before Phase 1 (meta update).

Uses a SQLite search cache (``pipeline_client.agent.search_cache``) to avoid
redundant Serper API calls across runs.  Token usage and estimated USD cost
are attached to the output JSON under ``agent_metrics``.
"""

import copy
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.pipeline_config import PIPELINE_STEP_IDS, REVIEW_PROVIDERS, PipelineRuntimeConfig

from .ballotpedia import default_ballotpedia_race_url
from .cost import _cost_ctx, estimate_cost
from .handlers import _make_editing_handlers  # noqa: F401 - re-exported for tests
from .llm import _agent_loop, _call_openrouter, _ensure_dict, _normalize_candidate  # noqa: F401 - re-exported for tests
from .model_registry import resolve_run_models
from .phases import (  # noqa: F401 - re-exported for backward compat
    _candidate_source_hints,
    _has_actionable_flags,
    _run_fresh,
    _run_iteration_pass,
    _run_update,
    _sanitize_roster,
    _scale_iterations,
    _select_target_candidates,
)
from .review import build_review_change_manifest, build_semantic_review_packet, compute_validation_grade, run_reviews
from .run_budget import RunBudget
from .tools import (  # noqa: F401 - re-exported for tests
    ADD_CANDIDATE_TOOL,
    ADD_LINK_TOOL,
    ADD_POLL_TOOL,
    BACKGROUND_TOOLS,
    BALLOTPEDIA_ELECTION_TOOL,
    BALLOTPEDIA_TOOL,
    CANDIDATE_TOOLS,
    FETCH_TOOL,
    FORECAST_TOOLS,
    ISSUE_TOOLS,
    RACE_TOOLS,
    READ_PROFILE_TOOL,
    RECORD_TOOLS,
    REMOVE_CANDIDATE_TOOL,
    RENAME_CANDIDATE_TOOL,
    ROSTER_TOOLS,
    SEARCH_TOOL,
    SET_CANDIDATE_FIELD_TOOL,
    SET_CANDIDATE_ROSTER_SOURCES_TOOL,
    SET_CANDIDATE_SUMMARY_TOOL,
    SET_DONOR_SUMMARY_TOOL,
    SET_FORECAST_TOOL,
    SET_ISSUE_STANCE_TOOL,
    SET_RACE_IDENTITY_TOOL,
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
    _serper_image_search,
    _serper_search,
)

logger = logging.getLogger("pipeline")

_PLACEHOLDER_CANDIDATE_NAMES = {
    "",
    "unknown",
    "tbd",
    "to be determined",
    "n/a",
    "na",
    "none",
    "dummy",
    "test",
    "placeholder",
    "candidate",
    "sample",
    "example",
}
_MISSING_STANCE_MARKERS = {
    "",
    "missing",
    "unknown",
    "n/a",
    "na",
    "none",
    "temp",
    "pending",
    "tbd",
    "to be determined",
    "draft",
    "todo",
    "fixme",
    "placeholder",
    "wip",
    "work in progress",
    "in progress",
    "coming soon",
    "no position found",
    "no public position found",
    "no public position found after repeated research attempts.",
}
_MISSING_STANCE_PREFIX_RE = re.compile(
    r"^(?:"
    + "|".join(re.escape(marker) for marker in sorted(_MISSING_STANCE_MARKERS, key=len, reverse=True) if marker)
    + r")\b",
    re.IGNORECASE,
)
# Real stances are full sentences; every known placeholder marker is a short phrase.
# Requiring both the prefix match AND a short overall length avoids false-positives
# on genuine stances that happen to start with a marker word (e.g. a real "Missing
# and murdered Indigenous women..." policy position should not be treated as absent).
_MISSING_STANCE_MAX_LEN = 60


def _is_missing_stance_text(stance: str) -> bool:
    """True if *stance* is empty or a placeholder rather than a real position.

    Catches exact markers ("tbd", "none", ...) plus short variants that merely
    add trailing words around a marker, e.g. "To be determined after review" —
    an exact-match-only check misses that variant entirely.
    """
    normalized = stance.strip()
    if not normalized:
        return True
    lowered = normalized.lower()
    if lowered in _MISSING_STANCE_MARKERS or "no public position found" in lowered:
        return True
    return len(normalized) <= _MISSING_STANCE_MAX_LEN and bool(_MISSING_STANCE_PREFIX_RE.match(normalized))


_VALID_CANDIDATE_LINK_TYPES = {
    "finance",
    "ballotpedia",
    "wiki",
    "official",
    "legislature",
    "votesmart",
    "govtrack",
    "news",
    "other",
}


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

    active_names = {
        _candidate_name(candidate) for candidate in race_json.get("candidates") or [] if _candidate_name(candidate)
    }
    kept_polls: List[Dict[str, Any]] = []
    dropped_polls = 0

    for poll_index, poll in enumerate(polling):
        if not isinstance(poll, dict):
            dropped_polls += 1
            continue
        matchups = poll.get("matchups")
        if matchups is None:
            poll["matchups"] = []
            matchups = poll["matchups"]
        if not isinstance(matchups, list):
            if log:
                log("warning", f"Poll {poll_index} matchups was not a list; dropping malformed matchups")
            poll["matchups"] = []
            matchups = poll["matchups"]

        kept_matchups: List[Dict[str, Any]] = []
        for matchup_index, matchup in enumerate(matchups):
            if not isinstance(matchup, dict):
                continue
            names = matchup.get("candidates")
            if active_names and isinstance(names, list):
                roster_names = [str(name).strip() for name in names]
                if any(name and name not in active_names for name in roster_names):
                    if log:
                        log("warning", f"Poll {poll_index} matchup {matchup_index} references non-roster candidates; dropping")
                    continue
            percentages = matchup.get("percentages")
            if not isinstance(names, list) or not names:
                if log:
                    log("warning", f"Poll {poll_index} matchup {matchup_index} has no candidate names; dropping")
                continue
            if not isinstance(percentages, list) or not percentages:
                if log:
                    log("warning", f"Poll {poll_index} matchup {matchup_index} has no numeric percentages; dropping")
                continue
            if len(names) != len(percentages):
                if log:
                    log(
                        "warning", f"Poll {poll_index} matchup {matchup_index} has mismatched candidates/percentages; dropping"
                    )
                continue
            if any(not isinstance(pct, (int, float)) or not 0 <= pct <= 100 for pct in percentages):
                if log:
                    log("warning", f"Poll {poll_index} matchup {matchup_index} has invalid percentages; dropping")
                continue
            kept_matchups.append(matchup)
        poll["matchups"] = kept_matchups

        pollster = str(poll.get("pollster") or "").lower()
        no_poll_placeholder = "no " in pollster and ("poll" in pollster or "public" in pollster)
        has_percentages = any(isinstance(m.get("percentages"), list) and m.get("percentages") for m in kept_matchups)
        if no_poll_placeholder and not has_percentages:
            dropped_polls += 1
            continue
        kept_polls.append(poll)

    if len(kept_polls) != len(polling):
        race_json["polling"] = kept_polls
        if log:
            log(
                "warning",
                f"Dropped {dropped_polls} malformed or placeholder polling entr{'y' if dropped_polls == 1 else 'ies'}",
            )


def _sanitize_candidate_links(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Normalize candidate reference links before validation and later saves."""
    for candidate_index, candidate in enumerate(race_json.get("candidates") or []):
        if not isinstance(candidate, dict):
            continue
        links = candidate.get("links")
        if links is None:
            candidate["links"] = []
            continue
        if not isinstance(links, list):
            candidate["links"] = []
            if log:
                log("warning", f"Candidate {candidate_index} links was not a list; dropping malformed links")
            continue

        normalized: List[Dict[str, str]] = []
        seen_urls: set[str] = set()
        changed = False
        for link in links:
            if isinstance(link, str):
                url = link.strip()
                if not url:
                    changed = True
                    continue
                normalized_link = {"url": url, "title": url, "type": "other"}
                changed = True
            elif isinstance(link, dict):
                url = str(link.get("url") or "").strip()
                if not url:
                    changed = True
                    continue
                title = str(link.get("title") or url).strip()
                link_type = str(link.get("type") or "other").strip()
                if link_type not in _VALID_CANDIDATE_LINK_TYPES:
                    link_type = "other"
                    changed = True
                normalized_link = {"url": url, "title": title or url, "type": link_type}
                changed = changed or normalized_link != link
            else:
                changed = True
                continue

            if normalized_link["url"] in seen_urls:
                changed = True
                continue
            normalized.append(normalized_link)
            seen_urls.add(normalized_link["url"])

        if changed:
            candidate["links"] = normalized
            if log:
                name = _candidate_name(candidate) or f"candidate {candidate_index}"
                log("warning", f"Normalized malformed reference links for {name}")


def _issue_quality(issue_data: Any) -> tuple[int, int]:
    if not isinstance(issue_data, dict):
        return (0, 0)
    stance = str(issue_data.get("stance") or "").strip()
    sources = issue_data.get("sources") or []
    source_count = len(sources) if isinstance(sources, list) else 0
    return (0 if _is_missing_stance_text(stance) else 1, source_count)


def _sanitize_candidate_issues(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Normalize issue keys and placeholder stances in raw agent output."""
    from shared.run_health import RunFailureReason
    from shared.run_health import is_placeholder_junk_stance as _is_placeholder_junk_stance
    from shared.run_health import record_step_failure as _record_step_failure

    try:
        from shared.models import LEGACY_ISSUE_NAMES, CanonicalIssue

        canonical_issue_names = {issue.value for issue in CanonicalIssue}
    except Exception:
        LEGACY_ISSUE_NAMES = {}
        canonical_issue_names = set()

    for candidate_index, candidate in enumerate(race_json.get("candidates") or []):
        if not isinstance(candidate, dict):
            continue
        issues = candidate.get("issues")
        if not isinstance(issues, dict):
            candidate["issues"] = {}
            continue

        normalized: Dict[str, Any] = {}
        for raw_key, raw_issue in issues.items():
            key = LEGACY_ISSUE_NAMES.get(str(raw_key), str(raw_key))
            if canonical_issue_names and key not in canonical_issue_names:
                if log:
                    log("warning", f"Removed noncanonical issue key candidates[{candidate_index}].issues.{raw_key}")
                continue
            if not isinstance(raw_issue, dict):
                if log:
                    log("warning", f"Removed malformed issue value candidates[{candidate_index}].issues.{raw_key}")
                continue
            issue = dict(raw_issue)
            if isinstance(issue, dict):
                issue["issue"] = LEGACY_ISSUE_NAMES.get(str(issue.get("issue") or key), str(issue.get("issue") or key))
                stance = str(issue.get("stance") or "").strip()
                if _is_missing_stance_text(stance):
                    if _is_placeholder_junk_stance(stance):
                        # A literal placeholder artifact (e.g. a stance that is
                        # just the word "DRAFT") — distinct from a deliberate
                        # "no public position found" research conclusion. Register
                        # it as a failure instead of letting it pass silently.
                        _record_step_failure(
                            race_json,
                            "issues",
                            RunFailureReason.PLACEHOLDER_CONTENT,
                            f"{_candidate_name(candidate)}/{key}: literal placeholder stance {stance!r}",
                        )
                    issue["stance"] = "No public position found after repeated research attempts."
                    issue["confidence"] = "low"
                    issue.setdefault("sources", [])
                    if log:
                        log("warning", f"Normalized placeholder stance for candidates[{candidate_index}].issues.{key}")
            if key not in normalized or _issue_quality(issue) > _issue_quality(normalized[key]):
                normalized[key] = issue

        # Always write back so value-level normalizations (e.g. "TBD" stances) are
        # persisted, not just key-level changes like legacy-name mappings.
        candidate["issues"] = normalized
        if set(normalized) != set(issues) and log:
            log("warning", f"Normalized legacy/duplicate issue keys for candidate '{_candidate_name(candidate)}'")


def _sanitize_roster_sources(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Clamp roster_sources[].type to the schema enum before validation.

    Discovery writes roster_sources directly into the race JSON blob rather
    than through the ``set_candidate_roster_sources`` tool (which already
    clamps invalid types via ``_ROSTER_SOURCE_TYPES``), so an out-of-enum
    value like "website" can reach here unnormalized. Left unclamped, the
    subsequent ``RaceJSON.model_validate`` call below raises, its exception is
    swallowed, and the *raw* unmigrated document — with the invalid value
    still in it — is what persists instead of the normalized one.
    """
    from pipeline_client.agent.handlers import _ROSTER_SOURCE_TYPES

    for candidate_index, candidate in enumerate(race_json.get("candidates") or []):
        if not isinstance(candidate, dict):
            continue
        sources = candidate.get("roster_sources")
        if not isinstance(sources, list):
            continue
        changed = False
        for source in sources:
            if not isinstance(source, dict):
                continue
            source_type = str(source.get("type") or "other").strip().lower()
            if source_type not in _ROSTER_SOURCE_TYPES:
                source["type"] = "other"
                changed = True
        if changed and log:
            name = _candidate_name(candidate) or f"candidate {candidate_index}"
            log("warning", f"Normalized invalid roster_sources type(s) for {name}")


def _normalize_schema_fields(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Apply schema defaults and Pydantic migrations while preserving extra metadata."""
    if not isinstance(race_json.get("schema_version"), str) or not race_json.get("schema_version"):
        race_json["schema_version"] = "0.3"
    _sanitize_candidate_issues(race_json, log)
    _sanitize_polling(race_json, log)
    _sanitize_candidate_links(race_json, log)
    _sanitize_roster_sources(race_json, log)

    try:
        from shared.models import RaceJSON as _RaceJSONModel

        normalized = _RaceJSONModel.model_validate(race_json).model_dump(mode="json")
    except Exception:
        return

    # Keep pipeline-only extras such as agent_metrics, but replace schema-owned
    # fields with the normalized model output so migrations are persisted.
    for key, value in normalized.items():
        race_json[key] = value


def _candidate_names_for_audit(race_json: Dict[str, Any] | None) -> set[str]:
    if not isinstance(race_json, dict):
        return set()
    return {
        str(candidate.get("name") or "").strip()
        for candidate in race_json.get("candidates", [])
        if isinstance(candidate, dict) and str(candidate.get("name") or "").strip()
    }


def _build_run_audit(existing_data: Dict[str, Any] | None, race_json: Dict[str, Any]) -> Dict[str, Any]:
    """Build non-gating notes that make future data-quality audits faster."""
    before_names = _candidate_names_for_audit(existing_data)
    after_names = _candidate_names_for_audit(race_json)
    candidate_changes: List[str] = []
    for name in sorted(after_names - before_names):
        candidate_changes.append(f"Added candidate: {name}")
    for name in sorted(before_names - after_names):
        candidate_changes.append(f"Removed candidate: {name}")
    if not candidate_changes:
        candidate_changes.append("No roster membership changes detected.")

    contest_stage = str(race_json.get("contest_stage") or "unknown")
    roster_source_counts: Dict[str, int] = {}
    candidates_missing_sources: List[str] = []
    for candidate in race_json.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        sources = candidate.get("roster_sources")
        if not isinstance(sources, list) or not sources:
            candidates_missing_sources.append(str(candidate.get("name") or "Unnamed candidate"))
            continue
        for source in sources:
            if not isinstance(source, dict):
                continue
            source_type = str(source.get("type") or "other")
            roster_source_counts[source_type] = roster_source_counts.get(source_type, 0) + 1

    if roster_source_counts:
        parts = [f"{count} {source_type}" for source_type, count in sorted(roster_source_counts.items())]
        roster_source_summary = "Roster evidence captured from " + ", ".join(parts) + " source(s)."
    else:
        roster_source_summary = "No candidate roster source evidence captured."

    forecast_changes: List[str] = []
    before_forecast = existing_data.get("forecast") if isinstance(existing_data, dict) else None
    after_forecast = race_json.get("forecast")
    if isinstance(before_forecast, dict) and isinstance(after_forecast, dict):
        for key in ("predicted_winner_name", "predicted_winner_party", "rating", "confidence"):
            if before_forecast.get(key) != after_forecast.get(key):
                forecast_changes.append(f"{key}: {before_forecast.get(key)!r} -> {after_forecast.get(key)!r}")
    elif not before_forecast and isinstance(after_forecast, dict):
        forecast_changes.append("Forecast added.")
    elif before_forecast and not after_forecast:
        forecast_changes.append("Forecast removed.")
    if not forecast_changes:
        forecast_changes.append("No forecast headline changes detected.")

    remaining_uncertainty: List[str] = []
    if contest_stage == "unknown":
        remaining_uncertainty.append("Contest stage is still unknown.")
    forecast = race_json.get("forecast")
    if isinstance(forecast, dict) and forecast.get("uncertainty"):
        remaining_uncertainty.append(str(forecast["uncertainty"]))
    if candidates_missing_sources:
        remaining_uncertainty.append(
            "Candidate roster source evidence missing for: " + ", ".join(candidates_missing_sources[:8])
        )

    publish_attention: List[str] = []
    pipeline_state = race_json.get("pipeline_state")
    if isinstance(pipeline_state, dict) and pipeline_state.get("complete") is False:
        publish_attention.append("Pipeline state is incomplete.")
    validation_grade = race_json.get("validation_grade")
    if isinstance(validation_grade, dict) and validation_grade.get("passed") is False:
        publish_attention.append(f"Validation grade did not pass: {validation_grade.get('grade')}.")
    if not race_json.get("candidates"):
        publish_attention.append("No candidates are present.")
    if candidates_missing_sources:
        publish_attention.append("Some candidates lack explicit roster source evidence.")

    return {
        "contest_stage": contest_stage,
        "roster_source_summary": roster_source_summary,
        "candidate_changes": candidate_changes,
        "forecast_changes": forecast_changes,
        "remaining_uncertainty": remaining_uncertainty,
        "publish_attention": publish_attention,
    }


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
    model_profile: Optional[str] = None,
    model_overrides: Optional[Dict[str, str]] = None,
    review_providers: Optional[List[str]] = None,
    enabled_steps: Optional[List[str]] = None,
    step_tracker: Optional[Dict[str, Any]] = None,
    max_candidates: Optional[int] = None,
    target_no_info: bool = False,
    candidate_names: Optional[List[str]] = None,
    goal: Optional[str] = None,
    resume_partial: bool = False,
    continue_incomplete_work: bool = False,
    reject_empty_candidates: bool = False,
    prior_agent_metrics: Optional[Dict[str, Any]] = None,
    run_budget: RunBudget | None = None,
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
        Override the OpenRouter model for research phases.
    claude_model / gemini_model / grok_model : str, optional
        Override individual OpenRouter review role models.
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
    option_models = resolve_run_models(
        {"model_profile": model_profile, "model_overrides": model_overrides or {}},
        cheap_mode=cheap_mode,
        research_model=research_model,
        claude_model=claude_model,
        gemini_model=gemini_model,
        grok_model=grok_model,
    )
    model = option_models["primary"]
    small_model = option_models["small"]
    roster_model = option_models.get("roster") or model
    profile = option_models["profile"]
    claude_model = option_models["review_claude"]
    gemini_model = option_models["review_gemini"]
    grok_model = option_models["review_grok"]
    enabled_review_providers = (
        [provider for provider in review_providers if provider in REVIEW_PROVIDERS]
        if review_providers is not None
        else list(REVIEW_PROVIDERS)
    )
    log = make_logger(on_log)
    t0 = time.perf_counter()

    # Step enablement check - None means all enabled
    _all_steps = set(PIPELINE_STEP_IDS)
    _enabled = set(enabled_steps) if enabled_steps else _all_steps

    def _step_enabled(step: str) -> bool:
        return step in _enabled

    def _track(action: str, step: str, **kwargs):
        if step_tracker and action in step_tracker:
            try:
                step_tracker[action](step, **kwargs)
            except Exception as _e:
                if _e.__class__.__name__ in {"AgentCancelled", "HandoffFailed", "HandoffTriggered", "RunBudgetExceeded"}:
                    raise
                logger.debug("Step tracker callback '%s' for '%s' failed: %s", action, step, _e)

    # Initialise a fresh cost accumulator for this run
    prior_agent_metrics = prior_agent_metrics or {}
    _acc: Dict[str, Any] = {
        "prompt_tokens": int(prior_agent_metrics.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(prior_agent_metrics.get("completion_tokens", 0) or 0),
        "provider_cost_usd": float(prior_agent_metrics.get("provider_cost_usd", 0.0) or 0.0),
        "priced_calls": int(prior_agent_metrics.get("priced_calls", 0) or 0),
        "unpriced_calls": int(prior_agent_metrics.get("unpriced_calls", 0) or 0),
        "serper_calls": int(prior_agent_metrics.get("serper_calls", 0) or 0),
        "context_requests": int(prior_agent_metrics.get("context_requests", 0) or 0),
        "max_estimated_context_tokens": int(prior_agent_metrics.get("max_estimated_context_tokens", 0) or 0),
        "max_context_window_tokens": int(prior_agent_metrics.get("max_context_window_tokens", 0) or 0),
        "context_deduplicated_results": int(prior_agent_metrics.get("context_deduplicated_results", 0) or 0),
        "context_compacted_results": int(prior_agent_metrics.get("context_compacted_results", 0) or 0),
        "context_truncated_results": int(prior_agent_metrics.get("context_truncated_results", 0) or 0),
        "context_dropped_tool_turns": int(prior_agent_metrics.get("context_dropped_tool_turns", 0) or 0),
        "retry_rate_limits": int(prior_agent_metrics.get("retry_rate_limits", 0) or 0),
        "retry_provider_failures": int(prior_agent_metrics.get("retry_provider_failures", 0) or 0),
        "retry_deadline_exits": int(prior_agent_metrics.get("retry_deadline_exits", 0) or 0),
        "model_breakdown": copy.deepcopy(prior_agent_metrics.get("model_breakdown", {})),
    }
    _ctx_token = _cost_ctx.set(_acc)

    if existing_data is None:
        existing_data = _load_existing(race_id)
    baseline_existing_data = copy.deepcopy(existing_data) if isinstance(existing_data, dict) else None

    if existing_data:
        log("info", f"Update mode for {race_id} (profile={profile}, model={model}, small_model={small_model})")
        if goal:
            log("info", f"Run goal: {goal}")
        race_json = await _run_update(
            race_id,
            existing_data,
            model=model,
            small_model=small_model,
            roster_model=roster_model,
            on_log=on_log,
            max_iterations=max_iterations,
            step_enabled=_step_enabled,
            track=_track,
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            target_candidate_names=candidate_names,
            goal=goal,
            resume_partial=resume_partial,
            continue_incomplete_work=continue_incomplete_work,
            run_budget=run_budget,
        )
    else:
        log("info", f"New research for {race_id} (profile={profile}, model={model}, small_model={small_model})")
        if goal:
            log("info", f"Run goal: {goal}")
        race_json = await _run_fresh(
            race_id,
            model=model,
            small_model=small_model,
            roster_model=roster_model,
            on_log=on_log,
            max_iterations=max_iterations,
            step_enabled=_step_enabled,
            track=_track,
            max_candidates=max_candidates,
            target_no_info=target_no_info,
            target_candidate_names=candidate_names,
            goal=goal,
            resume_partial=resume_partial,
            continue_incomplete_work=continue_incomplete_work,
            run_budget=run_budget,
        )

    # LLMs sometimes wrap their output in {"race_json": {...}} - unwrap it so
    # metadata we add below lands at the top level, not buried inside a key.
    if "race_json" in race_json and isinstance(race_json.get("race_json"), dict):
        log("warning", "LLM wrapped output in 'race_json' key; unwrapping")
        race_json = race_json["race_json"]

    race_json.setdefault("id", race_id)
    race_json.setdefault("contest_stage", "unknown")
    if not race_json.get("ballotpedia_url"):
        default_ballotpedia_url = default_ballotpedia_race_url(race_id)
        if default_ballotpedia_url:
            race_json["ballotpedia_url"] = default_ballotpedia_url
    race_json.setdefault("reviews", [])
    race_json.setdefault("validation_grade", None)
    now_iso = datetime.now(timezone.utc).isoformat()
    race_json["updated_utc"] = now_iso

    review_step_enabled = _step_enabled("review")
    carried_reviews = race_json.get("reviews")
    resume_review_iteration = (
        not review_step_enabled and _step_enabled("iteration") and isinstance(carried_reviews, list) and bool(carried_reviews)
    )
    should_review = review_step_enabled or resume_review_iteration
    pipeline_state = race_json.setdefault("pipeline_state", {})
    pipeline_state.setdefault("complete", True)
    pipeline_state.setdefault("remaining_candidates", [])
    pipeline_state.setdefault("remaining_steps", [])
    pipeline_state.setdefault("completed_units", [])
    unfinished_research_steps = [step for step in pipeline_state["remaining_steps"] if step not in {"review", "iteration"}]
    if should_review and unfinished_research_steps:
        log(
            "warning",
            "Final review blocked because required pipeline work remains: " + ", ".join(unfinished_research_steps),
        )
        should_review = False
    should_iterate = should_review and _step_enabled("iteration")

    # Record the models actually used.
    generators = list(dict.fromkeys([model, small_model]))  # preserves order, drops duplicates
    if should_review:
        reviewer_models = {
            "claude": claude_model,
            "gemini": gemini_model,
            "grok": grok_model,
        }
        generators.extend(reviewer_models[provider] for provider in enabled_review_providers)
        generators = list(dict.fromkeys(generators))
    race_json["generator"] = generators

    for candidate in race_json.get("candidates", []):
        if isinstance(candidate, dict):
            _normalize_candidate(candidate, now_iso)

    _sanitize_roster(race_json, log)
    race_json.setdefault("polling", [])
    _normalize_schema_fields(race_json, log)
    pipeline_state = race_json.setdefault("pipeline_state", pipeline_state)

    review_required_steps_ran = bool(_enabled & {"issues", "refinement", "iteration"})
    maintenance_steps_ran = bool(_enabled & {"polling", "forecast", "voter_resources"})
    validation_grade = race_json.get("validation_grade")
    if not isinstance(validation_grade, dict) and race_json.get("reviews"):
        validation_grade = compute_validation_grade(race_json.get("reviews", []))
    has_passing_validation = (
        isinstance(validation_grade, dict) and validation_grade.get("passed") is True and bool(race_json.get("reviews"))
    )
    if should_review:
        pipeline_state["complete"] = True
        pipeline_state["remaining_candidates"] = []
        pipeline_state["remaining_steps"] = []
    elif review_required_steps_ran:
        pipeline_state["complete"] = False
        if "review" not in pipeline_state["remaining_steps"]:
            pipeline_state["remaining_steps"].append("review")
    elif maintenance_steps_ran and has_passing_validation:
        remaining_steps = [step for step in pipeline_state.get("remaining_steps", []) if step != "review"]
        pipeline_state["remaining_steps"] = remaining_steps
        pipeline_state["complete"] = not remaining_steps and not pipeline_state.get("remaining_candidates")

    if reject_empty_candidates and should_review and not race_json.get("candidates"):
        raise ValueError(
            f"Agent discovery for '{race_id}' returned no candidates. "
            "Stopping before review to avoid spending on an empty profile."
        )

    if should_review:
        prior_review_metrics = (race_json.get("agent_metrics") or {}).get("review", {})
        review_metrics: Dict[str, Any] = copy.deepcopy(prior_review_metrics) if resume_review_iteration else {}
        review_cache: Dict[str, Any] = {}
        reviewed_packet = build_semantic_review_packet(race_json)
        if review_step_enabled:
            _track("start", "review")
            review_t0 = time.perf_counter()
            log("info", f"Phase 4: Sending to review agents ({', '.join(enabled_review_providers)})...")
            reviews = await run_reviews(
                race_id,
                race_json,
                on_log=on_log,
                cheap_mode=cheap_mode,
                claude_model=claude_model,
                gemini_model=gemini_model,
                grok_model=grok_model,
                review_providers=enabled_review_providers,
                change_manifest=build_review_change_manifest(None, reviewed_packet),
                semantic_packet=reviewed_packet,
                metrics_sink=review_metrics,
                review_cache=review_cache,
                run_budget=run_budget,
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
        else:
            reviews = copy.deepcopy(carried_reviews)
            log("info", f"Resuming review iteration with {len(reviews)} checkpointed review result(s)")
            _track("skip", "review")

        # --- Phase 5: Iterate on review feedback (up to 3 cycles) ---
        if should_iterate:
            _track("start", "iteration")
            iter_t0 = time.perf_counter()
            runtime_config = PipelineRuntimeConfig.from_env()
            max_review_cycles = runtime_config.max_review_cycles
            did_iterate = False
            for cycle in range(1, max_review_cycles + 1):
                min_severity = "warning" if cycle == 1 else "error"
                if not _has_actionable_flags(reviews, min_severity=min_severity):
                    if cycle == 1:
                        log("info", "  No actionable review flags; skipping iteration")
                    else:
                        log("info", f"  Cycle {cycle}: no remaining {min_severity}+ flags; done")
                    break

                did_iterate = True
                log("info", f"Phase 5 (cycle {cycle}/{max_review_cycles}): Iterating on review feedback...")
                cycle_budget = max_iterations if max_review_cycles == 1 else int(max_iterations / max_review_cycles)

                def _on_iteration_progress(pct: int, message: str, checkpoint_race: Dict[str, Any]) -> None:
                    cycle_pct = int(((cycle - 1) + pct / 100) / max_review_cycles * 100)
                    _track("progress", "iteration", pct=cycle_pct, message=message, race_json=checkpoint_race)

                improved = await _run_iteration_pass(
                    race_id,
                    race_json,
                    reviews,
                    model=model,
                    on_log=on_log,
                    on_progress=_on_iteration_progress,
                    max_iterations=max(cycle_budget, runtime_config.iteration_min_iterations),
                    resume_partial=resume_partial,
                    unit_prefix=f"iteration:{cycle}",
                    run_budget=run_budget,
                )
                if improved is not None:
                    race_json = improved
                    pipeline_state = race_json.setdefault("pipeline_state", pipeline_state)
                    # Re-normalize after iteration
                    now_iso = datetime.now(timezone.utc).isoformat()
                    race_json["updated_utc"] = now_iso
                    for candidate in race_json.get("candidates", []):
                        if isinstance(candidate, dict):
                            _normalize_candidate(candidate, now_iso)
                    race_json["generator"] = generators
                    _sanitize_roster(race_json, log)
                    _normalize_schema_fields(race_json, log)

                    updated_packet = build_semantic_review_packet(race_json)
                    log("info", f"  Cycle {cycle}: Re-running reviews...")
                    reviews = await run_reviews(
                        race_id,
                        race_json,
                        on_log=on_log,
                        cheap_mode=cheap_mode,
                        claude_model=claude_model,
                        gemini_model=gemini_model,
                        grok_model=grok_model,
                        review_providers=enabled_review_providers,
                        change_manifest=build_review_change_manifest(reviewed_packet, updated_packet),
                        semantic_packet=updated_packet,
                        metrics_sink=review_metrics,
                        review_cache=review_cache,
                        run_budget=run_budget,
                    )
                    reviewed_packet = updated_packet
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
        _track("skip", "review")
        _track("skip", "iteration")

    # Compute aggregate validation grade from review scores
    grade = compute_validation_grade(race_json.get("reviews", [])) if race_json.get("reviews") else None
    race_json["validation_grade"] = grade
    race_json["run_audit"] = _build_run_audit(baseline_existing_data, race_json)

    # A definitive machine-readable "did this run actually work" verdict —
    # distinct from pipeline_state.complete, which only tracks whether all
    # requested steps ran, not whether they produced trustworthy data. See
    # shared/run_health.py for the taxonomy and CLAUDE.md rule 7 for the
    # motivating silent-failure patterns.
    from shared.run_health import compute_run_health_verdict

    run_health = compute_run_health_verdict(race_json, should_review=should_review, validation_grade=grade)
    race_json["run_health"] = run_health.model_dump(mode="json")
    if not run_health.passed:
        log(
            "warning",
            f"Run health verdict: {run_health.status.value} "
            f"(reasons: {', '.join(r.value for r in run_health.reasons) or 'none'})",
        )

    elapsed = time.perf_counter() - t0

    # Compute and attach cost estimate across all OpenRouter model calls.
    _cost_ctx.reset(_ctx_token)
    pt = _acc["prompt_tokens"]
    ct = _acc["completion_tokens"]
    total_tokens = pt + ct
    breakdown = _acc.get("model_breakdown", {})
    estimated_cost = (
        sum(estimate_cost(m, bd.get("prompt_tokens", 0), bd.get("completion_tokens", 0)) for m, bd in breakdown.items())
        if breakdown
        else estimate_cost(model, pt, ct)
    )
    provider_cost = _acc.get("provider_cost_usd", 0.0)

    # Add Serper costs ($0.001 per call) to both estimated and provider costs
    serper_calls = _acc.get("serper_calls", 0)
    serper_cost = serper_calls * 0.001
    estimated_cost += serper_cost
    if provider_cost > 0:
        provider_cost += serper_cost

    has_exact_provider_cost = _acc.get("priced_calls", 0) > 0 and _acc.get("unpriced_calls", 0) == 0
    agent_metrics = {
        "model": model,
        "model_profile": profile,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": total_tokens,
        "cost_usd": provider_cost if has_exact_provider_cost else None,
        "cost_source": "provider" if has_exact_provider_cost else "estimated",
        "estimated_usd": round(estimated_cost, 6),
        "model_breakdown": breakdown,
        "duration_s": round(elapsed, 1),
        "serper_calls": serper_calls,
        "context_requests": _acc.get("context_requests", 0),
        "max_estimated_context_tokens": _acc.get("max_estimated_context_tokens", 0),
        "max_context_window_tokens": _acc.get("max_context_window_tokens", 0),
        "max_context_utilization": round(
            _acc.get("max_estimated_context_tokens", 0) / max(_acc.get("max_context_window_tokens", 0), 1),
            4,
        ),
        "context_deduplicated_results": _acc.get("context_deduplicated_results", 0),
        "context_compacted_results": _acc.get("context_compacted_results", 0),
        "context_truncated_results": _acc.get("context_truncated_results", 0),
        "context_dropped_tool_turns": _acc.get("context_dropped_tool_turns", 0),
        "retry_rate_limits": _acc.get("retry_rate_limits", 0),
        "retry_provider_failures": _acc.get("retry_provider_failures", 0),
        "retry_deadline_exits": _acc.get("retry_deadline_exits", 0),
    }
    if should_review:
        agent_metrics["review"] = review_metrics
    race_json["agent_metrics"] = agent_metrics
    log(
        "info",
        f"Agent finished in {elapsed:.1f}s; "
        f"${(provider_cost if has_exact_provider_cost else estimated_cost):.6f} "
        f"{'provider billed' if has_exact_provider_cost else 'estimated'} "
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
    if _candidate_names and all(_is_placeholder_candidate_name(name) for name in _candidate_names):
        raise ValueError(
            f"Agent output for '{race_id}' only contains placeholder candidate names: {_candidate_names}. "
            "Refusing to save a draft that cannot identify any real candidate."
        )

    # Full schema validation against RaceJSON — soft check so later phases
    # (refinement, iteration) can still fix issues.  Log every validation
    # error but never hard-fail here.
    try:
        from shared.models import RaceJSON as _RaceJSONModel

        _sanitize_roster(race_json, log)
        _normalize_schema_fields(race_json, log)
        _RaceJSONModel.model_validate(race_json)
        log("info", "Schema validation passed; output conforms to RaceJSON v0.3")
    except Exception as schema_exc:
        log("warning", f"Schema validation warnings (non-fatal): {schema_exc}")

    return race_json
