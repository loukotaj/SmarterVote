"""OpenRouter-backed review agents for fact-checking candidate profiles."""

import asyncio
import copy
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from shared.models import Candidate, CanonicalIssue, RaceJSON
from shared.pipeline_config import REVIEW_PROVIDERS

from .cost import estimate_cost
from .llm import _call_openrouter, _provider_usage_cost
from .model_registry import PROFILE_DEFAULTS, normalize_model_id
from .phase_state import race_identity_context
from .polling_quality import polling_semantic_problem
from .prompts import REVIEW_SYSTEM, REVIEW_USER
from .run_budget import RunBudget, RunBudgetExceeded
from .utils import _extract_json, make_logger
from .web_tools import _get_validated

logger = logging.getLogger("pipeline")

# Which profile role each review seat draws from. The models themselves are
# never named here: this module used to carry its own provider -> (full, cheap)
# table, a second source of truth that agent.py happened to override on every
# call, so it could have drifted from the profiles indefinitely without any
# test noticing.
_REVIEW_ROLES = {
    REVIEW_PROVIDERS[0]: "review_claude",
    REVIEW_PROVIDERS[1]: "review_gemini",
    REVIEW_PROVIDERS[2]: "review_grok",
}


def _review_model_for(provider: str, *, cheap_mode: bool) -> str:
    """Return the profile-default model for a review seat."""
    return PROFILE_DEFAULTS["default" if cheap_mode else "premium"][_REVIEW_ROLES[provider]]


_ACCESS_RESTRICTED_HOSTS = frozenset({"facebook.com", "www.facebook.com", "m.facebook.com"})
_OPERATIONAL_RACE_FIELDS = frozenset(
    {
        "agent_metrics",
        "candidate_limit_note",
        "generator",
        "pipeline_state",
        "post_run_analysis",
        "reviews",
        "run_audit",
        "validation_grade",
    }
)
_REVIEWABLE_RACE_FIELDS = tuple(field for field in RaceJSON.model_fields if field not in _OPERATIONAL_RACE_FIELDS)
_REVIEWABLE_CANDIDATE_FIELDS = tuple(Candidate.model_fields)
_STALE_ACCESS_THRESHOLD = timedelta(days=365)

# A race must reach this to publish.
PASSING_SCORE = 80
# What each warning-severity flag costs. Warnings are advisory, so they scale
# rather than veto: at 3 points a race reviewed in the 90s survives two or three
# of them, while one scraping by in the low 80s does not.
WARNING_SCORE_PENALTY = 3


def build_semantic_review_packet(race_json: Dict[str, Any]) -> Dict[str, Any]:
    """Return the complete semantic RaceJSON surface without operational metadata."""
    packet = {field: copy.deepcopy(race_json.get(field)) for field in _REVIEWABLE_RACE_FIELDS}
    candidates = packet.get("candidates")
    if isinstance(candidates, list):
        packet["candidates"] = [
            {field: copy.deepcopy(candidate.get(field)) for field in _REVIEWABLE_CANDIDATE_FIELDS}
            if isinstance(candidate, dict)
            else candidate
            for candidate in candidates
        ]
    return packet


def validate_semantic_review_packet(race_json: Dict[str, Any], packet: Dict[str, Any]) -> None:
    """Fail if a modeled semantic field was omitted or changed during packet assembly."""
    missing_top_level = [field for field in _REVIEWABLE_RACE_FIELDS if field not in packet]
    if missing_top_level:
        raise ValueError(f"Review packet omitted race fields: {', '.join(missing_top_level)}")
    for field in _REVIEWABLE_RACE_FIELDS:
        if field != "candidates" and packet[field] != race_json.get(field):
            raise ValueError(f"Review packet changed {field}")
    source_candidates = race_json.get("candidates")
    packet_candidates = packet.get("candidates")
    if not isinstance(source_candidates, list) or not isinstance(packet_candidates, list):
        return
    if len(source_candidates) != len(packet_candidates):
        raise ValueError("Review packet candidate count does not match RaceJSON")
    for index, (source, candidate_packet) in enumerate(zip(source_candidates, packet_candidates)):
        if not isinstance(source, dict) or not isinstance(candidate_packet, dict):
            continue
        missing = [field for field in _REVIEWABLE_CANDIDATE_FIELDS if field not in candidate_packet]
        if missing:
            raise ValueError(f"Review packet omitted candidates[{index}] fields: {', '.join(missing)}")
        for field in _REVIEWABLE_CANDIDATE_FIELDS:
            if candidate_packet[field] != source.get(field):
                raise ValueError(f"Review packet changed candidates[{index}].{field}")


def serialize_semantic_review_packet(packet: Dict[str, Any]) -> str:
    """Serialize the canonical packet compactly while preserving every semantic field."""
    return json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def build_issue_research_effort_context(race_json: Dict[str, Any]) -> str:
    """Summarize durable issue attempts so reviewers can distinguish absence from omission."""
    state = race_json.get("pipeline_state") if isinstance(race_json.get("pipeline_state"), dict) else {}
    attempts = state.get("issue_attempts") if isinstance(state.get("issue_attempts"), dict) else {}
    research = state.get("issue_research") if isinstance(state.get("issue_research"), dict) else {}
    lines: List[str] = []
    required = [issue.value for issue in CanonicalIssue]
    for candidate in race_json.get("candidates") or []:
        if not isinstance(candidate, dict) or not candidate.get("name"):
            continue
        name = str(candidate["name"])
        issues = candidate.get("issues") if isinstance(candidate.get("issues"), dict) else {}
        attempted_slots = sum(int(attempts.get(f"issues:{name}:{issue}", 0) or 0) > 0 for issue in required)
        total_attempts = sum(max(0, int(attempts.get(f"issues:{name}:{issue}", 0) or 0)) for issue in required)
        completed_slots = sum(bool(str((issues.get(issue) or {}).get("stance") or "").strip()) for issue in required)
        no_position_slots = sum(
            _is_documented_absence(str((issues.get(issue) or {}).get("stance") or "")) for issue in required
        )
        unproven_absence = sum(
            _is_documented_absence(str((issues.get(issue) or {}).get("stance") or ""))
            and (
                not isinstance(research.get(f"issues:{name}:{issue}"), dict)
                or research[f"issues:{name}:{issue}"].get("status") != "completed"
                or int(research[f"issues:{name}:{issue}"].get("search_calls", 0) or 0)
                + int(research[f"issues:{name}:{issue}"].get("page_fetches", 0) or 0)
                < 2
            )
            for issue in required
        )
        researched_slots = sum(
            isinstance(research.get(f"issues:{name}:{issue}"), dict)
            and int(research[f"issues:{name}:{issue}"].get("search_calls", 0) or 0)
            + int(research[f"issues:{name}:{issue}"].get("page_fetches", 0) or 0)
            > 0
            for issue in required
        )
        lines.append(
            f"- {name}: {completed_slots}/12 terminal issue outputs; {attempted_slots}/12 slots with recorded "
            f"pipeline attempts ({total_attempts} total attempts); {no_position_slots} documented no-position "
            f"outputs; {researched_slots}/12 slots with recorded search/fetch activity; {unproven_absence} "
            f"no-position outputs without sufficient research provenance."
        )
    return "\n".join(lines) or "- No candidate issue-research attempt evidence is present."


def build_review_change_manifest(previous: Dict[str, Any] | None, current: Dict[str, Any]) -> str:
    """Build a deterministic changed-field manifest while always sending the full packet."""
    if previous is None:
        return "Initial review. No previous revision is available."

    changed_paths: List[str] = []

    def _walk(before: Any, after: Any, path: str) -> None:
        if type(before) is not type(after):
            changed_paths.append(path or "$")
            return
        if isinstance(before, dict):
            for key in sorted(set(before) | set(after)):
                child = f"{path}.{key}" if path else str(key)
                if key not in before or key not in after:
                    changed_paths.append(child)
                else:
                    _walk(before[key], after[key], child)
            return
        if isinstance(before, list):
            if len(before) != len(after):
                changed_paths.append(path)
            for index, (before_item, after_item) in enumerate(zip(before, after)):
                _walk(before_item, after_item, f"{path}[{index}]")
            return
        if before != after:
            changed_paths.append(path or "$")

    _walk(previous, current, "")
    if not changed_paths:
        return "No semantic fields changed since the previous review."
    return "Semantic fields changed since the previous review:\n" + "\n".join(f"- {path}" for path in changed_paths)


def is_substantive_race_description(description: Any, title: Any = "") -> bool:
    """Return True when a race description is meaningfully more than its title."""
    if not isinstance(description, str):
        return False
    text = " ".join(description.split())
    normalized_title = " ".join(str(title or "").split()).casefold()
    if len(text) < 120 or len(text.split()) < 20:
        return False
    if normalized_title and text.casefold() == normalized_title:
        return False
    return sum(text.count(mark) for mark in ".!?") >= 2


def _is_access_restricted_response(url: str, status_code: int) -> bool:
    """Return True when a response cannot reliably establish that a link is dead."""
    if status_code in (401, 403, 429):
        return True
    hostname = (urlparse(url).hostname or "").lower()
    return status_code == 400 and hostname in _ACCESS_RESTRICTED_HOSTS


async def _call_review_model(
    system: str,
    user: str,
    *,
    model: str,
    run_budget: RunBudget | None = None,
) -> tuple[str, Dict[str, Any]]:
    """Call a review model and return content plus provider usage."""
    response = await _call_openrouter(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=model,
        max_tokens=8192,
        run_budget=run_budget,
    )
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    provider_cost = _provider_usage_cost(usage)
    return response.choices[0].message.content or "", {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "provider_cost_usd": provider_cost,
        "estimated_cost_usd": estimate_cost(model, prompt_tokens, completion_tokens),
    }


async def _run_single_review(
    race_id: str,
    profile_json: str,
    *,
    provider: str,
    model_override: Optional[str] = None,
    on_log: Optional[Callable] = None,
    change_manifest: str = "Initial review. No previous revision is available.",
    metrics_sink: Optional[Dict[str, Any]] = None,
    run_budget: RunBudget | None = None,
    race_identity_context_text: str = "",
    research_effort_context_text: str = "",
) -> Optional[Dict[str, Any]]:
    """Run a single review agent role (claude, gemini, or grok)."""
    log = make_logger(on_log)
    user_prompt = REVIEW_USER.format(
        race_id=race_id,
        profile_json=profile_json,
        change_manifest=change_manifest,
        race_identity_context=race_identity_context_text,
        research_effort_context=research_effort_context_text,
    )
    if provider not in _REVIEW_ROLES:
        return None
    model_name = normalize_model_id(model_override) or _review_model_for(provider, cheap_mode=False)
    try:
        log("info", f"  Reviewing with {model_name}...")
        call_result = await _call_review_model(REVIEW_SYSTEM, user_prompt, model=model_name, run_budget=run_budget)
        if isinstance(call_result, tuple):
            raw, usage = call_result
        else:
            raw, usage = call_result, {}
        if metrics_sink is not None:
            metrics_sink["calls"] = int(metrics_sink.get("calls", 0)) + 1
            provider_metrics = metrics_sink.setdefault("providers", {}).setdefault(
                provider,
                {
                    "model": model_name,
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "provider_cost_usd": 0.0,
                    "estimated_cost_usd": 0.0,
                },
            )
            provider_metrics["calls"] += 1
            provider_metrics["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
            provider_metrics["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
            provider_metrics["provider_cost_usd"] += float(usage.get("provider_cost_usd") or 0.0)
            provider_metrics["estimated_cost_usd"] += float(usage.get("estimated_cost_usd") or 0.0)

        try:
            review_data = _extract_json(raw)
        except (json.JSONDecodeError, ValueError):
            log("warning", f"  {provider} review returned malformed JSON - skipping")
            return None

        if not isinstance(review_data, dict):
            log("warning", f"  {provider} review returned unexpected type {type(review_data).__name__} - skipping")
            return None

        return {
            "model": model_name,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "verdict": review_data.get("verdict", "flagged"),
            "score": review_data.get("score"),
            "flags": review_data.get("flags", []),
            "summary": review_data.get("summary", ""),
        }
    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  {provider} review failed: {exc}")
        return None


# Failures that will not resolve themselves on a retry, so the citation can be
# dropped deterministically instead of being handed back to a model. A host that
# does not resolve is at least as dead as a 404.
_PERMANENT_DNS_FAILURE_MARKERS = (
    "name or service not known",
    "nodename nor servname provided",
    "getaddrinfo failed",
    "no address associated with hostname",
    "name does not resolve",
)


def _is_permanent_link_failure(exc: Exception) -> bool:
    """True when a fetch failure means the URL is gone, not merely unreachable now."""
    if isinstance(exc, ValueError):
        return True  # malformed / disallowed URL
    text = str(exc).casefold()
    if any(marker in text for marker in _PERMANENT_DNS_FAILURE_MARKERS):
        return True
    # A certificate that does not validate makes the address unusable as a
    # citation until someone fixes the host, which is not something a rerun can
    # resolve. Common on "www." variants of state election sites.
    return "certificate_verify_failed" in text or "certificate verify failed" in text


async def _verify_url(client: httpx.AsyncClient, url: str) -> Optional[tuple[str, bool]]:
    """Check a URL through the SSRF-safe fetch path.

    Returns ``None`` when healthy, otherwise ``(reason, permanent)``.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        }
        resp = await _get_validated(client, url, headers=headers)
        if _is_access_restricted_response(url, resp.status_code):
            return None
        if resp.status_code >= 400:
            return f"HTTP error {resp.status_code}", resp.status_code in {404, 410}
        return None
    except (httpx.HTTPError, ValueError) as exc:
        return f"Request failed: {exc}", _is_permanent_link_failure(exc)
    except Exception as exc:
        return f"Error: {exc}", False


async def check_profile_links(
    race_json: Dict[str, Any],
    on_log: Optional[Callable] = None,
    run_budget: RunBudget | None = None,
) -> Optional[Dict[str, Any]]:
    """Programmatically verify all source URLs in the profile."""
    log = make_logger(on_log)
    urls_to_check = []  # List of tuples: (url, path_str)

    # 1. Extract candidate sources
    for c_idx, c in enumerate(race_json.get("candidates", [])):
        # Summary sources
        for s_idx, src in enumerate(c.get("summary_sources", [])):
            if isinstance(src, dict) and src.get("url"):
                urls_to_check.append((str(src["url"]), f"candidates[{c_idx}].summary_sources[{s_idx}].url"))

        # Issue sources
        for issue, issue_data in c.get("issues", {}).items():
            if isinstance(issue_data, dict):
                for s_idx, src in enumerate(issue_data.get("sources", [])):
                    if isinstance(src, dict) and src.get("url"):
                        urls_to_check.append((str(src["url"]), f"candidates[{c_idx}].issues.{issue}.sources[{s_idx}].url"))

        # Donor sources
        for s_idx, src in enumerate(c.get("donor_sources", [])):
            if isinstance(src, dict) and src.get("url"):
                urls_to_check.append((str(src["url"]), f"candidates[{c_idx}].donor_sources[{s_idx}].url"))

        # Voting sources
        for s_idx, src in enumerate(c.get("voting_sources", [])):
            if isinstance(src, dict) and src.get("url"):
                urls_to_check.append((str(src["url"]), f"candidates[{c_idx}].voting_sources[{s_idx}].url"))

    if not urls_to_check:
        return None

    log("info", f"  Verifying {len(urls_to_check)} source links...")

    # Run link checks concurrently with a limit on concurrent requests
    sem = asyncio.Semaphore(10)
    timeout = run_budget.bounded_timeout(5.0, minimum_seconds=2.0, operation="review link check") if run_budget else 5.0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:

        async def _check(url: str, path: str):
            async with sem:
                err = await _verify_url(client, url)
                return url, path, err

        tasks = [_check(url, path) for url, path in urls_to_check]
        check_results = await asyncio.gather(*tasks)

    flags = []
    for url, path, err in check_results:
        if err:
            reason, permanent = err
            # Severity tracks what the check actually establishes. A 404, a 410,
            # an unresolvable host or a bad certificate is real evidence the
            # citation is gone. A timeout, a connection reset or a 5xx says only
            # that the host misbehaved during this one scan, which is a weaker
            # claim — reporting both as warnings let a single flaky fetch speak
            # with the authority of a confirmed dead link. 401/403/429 never
            # reach here at all; _is_access_restricted_response already treats
            # bot-blocking as no evidence either way.
            flags.append(
                {
                    "field": path,
                    "concern": (
                        f"Cited source URL ({url}) returned a dead link: {reason}."
                        if permanent
                        else f"Cited source URL ({url}) was unreachable during this check: {reason}."
                    ),
                    "suggestion": (
                        "Verify the URL, find a replacement source, and update the stance."
                        if permanent
                        else "Re-check the URL; this may be a transient outage rather than a broken citation."
                    ),
                    "severity": "warning" if permanent else "info",
                    # Machine-readable so deterministic cleanup does not have to
                    # parse these back out of prose. Recovering the URL by regex
                    # truncated any address containing parentheses — which covers
                    # every Ballotpedia/Wikipedia disambiguation link — so those
                    # citations could never be matched and removed.
                    "permanent_failure": permanent,
                    "url": url,
                }
            )

    confirmed = sum(1 for flag in flags if flag.get("permanent_failure"))
    unreachable = len(flags) - confirmed
    verdict = "flagged" if confirmed else "approved"
    summary = (
        f"Scanned {len(urls_to_check)} source links. Found {confirmed} dead link(s) "
        f"and {unreachable} that were unreachable without confirming they are gone."
    )
    log("info", f"  Link Validator: {verdict} ({confirmed} dead, {unreachable} unreachable)")

    return {
        "model": "automated-link-validator",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "score": None,
        "flags": flags,
        "summary": summary,
    }


def _remove_confirmed_dead_candidate_sources(race_json: Dict[str, Any], link_review: Dict[str, Any]) -> int:
    """Remove candidate URLs the link validator confirmed are permanently gone.

    Covers HTTP 404/410 and unresolvable hosts. A DNS failure used to fall through
    to the model, which then had to remove the citation by hand — in practice it
    never did, and the unfixable flag blocked publication indefinitely.
    """
    if not isinstance(link_review, dict):
        return 0
    removals: Dict[int, set[str]] = {}
    for flag in link_review.get("flags") or []:
        if not isinstance(flag, dict):
            continue
        concern = str(flag.get("concern") or "")
        permanent = flag.get("permanent_failure")
        if permanent is None:
            # Reviews stored before permanent_failure existed.
            permanent = "HTTP error 404" in concern or "HTTP error 410" in concern
        if not permanent:
            continue
        field_match = re.match(r"candidates\[(\d+)\]", str(flag.get("field") or ""))
        if not field_match:
            continue
        url = str(flag.get("url") or "").strip()
        if not url:
            # Reviews stored before the flag carried its URL. The regex truncates
            # any address containing parentheses, so it is a fallback only.
            url_match = re.search(r"Cited source URL \((https?://[^)]+)\)", concern)
            url = url_match.group(1) if url_match else ""
        if url:
            removals.setdefault(int(field_match.group(1)), set()).add(url)

    removed = 0
    candidates = race_json.get("candidates") or []
    for candidate_index, urls in removals.items():
        if candidate_index >= len(candidates) or not isinstance(candidates[candidate_index], dict):
            continue
        candidate = candidates[candidate_index]
        for key in ("roster_sources", "summary_sources", "donor_sources", "voting_sources", "links"):
            items = candidate.get(key)
            if isinstance(items, list):
                kept = [item for item in items if not (isinstance(item, dict) and str(item.get("url") or "").strip() in urls)]
                removed += len(items) - len(kept)
                candidate[key] = kept
        for key in ("donor_source_url", "voting_source_url"):
            if str(candidate.get(key) or "").strip() in urls:
                candidate[key] = None
                removed += 1
        for issue in (candidate.get("issues") or {}).values():
            if not isinstance(issue, dict) or not isinstance(issue.get("sources"), list):
                continue
            sources = issue["sources"]
            kept = [item for item in sources if not (isinstance(item, dict) and str(item.get("url") or "").strip() in urls)]
            removed += len(sources) - len(kept)
            issue["sources"] = kept

        pipeline_state = race_json.setdefault("pipeline_state", {})
        tombstones = pipeline_state.setdefault("removed_source_urls", [])
        candidate_name = str(candidate.get("name") or "").strip()
        for url in urls:
            tombstone = {"candidate_name": candidate_name, "url": url}
            if tombstone not in tombstones:
                tombstones.append(tombstone)
    return removed


def _is_documented_absence(stance: str) -> bool:
    normalized = stance.casefold()
    return "no public position found" in normalized or "no publicly stated position" in normalized


def _implausible_incumbency_claim(race_json: Dict[str, Any]) -> Optional[str]:
    office = str(race_json.get("office") or "").casefold()
    term_years = 2 if "house" in office or "representative" in office else 6 if "senate" in office else None
    if term_years is None:
        return None
    election_date = str(race_json.get("election_date") or "")
    try:
        election_year = int(election_date[:4])
    except (TypeError, ValueError):
        return None

    plausible_terms = []
    for candidate in race_json.get("candidates") or []:
        if not isinstance(candidate, dict) or not candidate.get("incumbent"):
            continue
        starts = [
            entry.get("start_year")
            for entry in candidate.get("career_history") or []
            if isinstance(entry, dict)
            and isinstance(entry.get("start_year"), int)
            and (
                "representative" in str(entry.get("title") or "").casefold()
                or "senator" in str(entry.get("title") or "").casefold()
            )
        ]
        if starts:
            plausible_terms.append(max(1, (election_year - min(starts) + term_years - 1) // term_years))
    if not plausible_terms:
        return None

    forecast_text = json.dumps(race_json.get("forecast") or {}, ensure_ascii=True)
    for match in re.finditer(r"\b(\d+)[ -]term\b", forecast_text, flags=re.IGNORECASE):
        claimed_terms = int(match.group(1))
        if claimed_terms > max(plausible_terms) + 1:
            return f"Forecast claims a {claimed_terms}-term incumbency, but candidate career dates support at most about {max(plausible_terms)} completed terms."
    return None


def check_profile_quality(race_json: Dict[str, Any], *, issues_step_ran: bool = True) -> Dict[str, Any]:
    """Run deterministic checks for important quality failures reviewers may miss.

    ``issues_step_ran`` says whether issue research was in scope for this run. A
    lightweight refresh deliberately skips it, and grading such a run on stances
    it was never asked to collect measures the wrong thing: md-house-01-2026 was
    approved by 3/3 reviewers at an average of 93 and still landed on grade C,
    because the absent stances capped the score at 79 and blocked publication.
    The gap is still reported — it is real, and the race does need issue research
    eventually — but as ``info`` so it does not fail a run that was never trying.
    """
    flags = []
    try:
        RaceJSON.model_validate(race_json)
    except Exception as exc:
        flags.append(
            {
                "field": "$",
                "concern": f"RaceJSON schema validation failed: {exc}",
                "suggestion": "Correct the schema errors before publishing.",
                "severity": "error",
            }
        )
    if not is_substantive_race_description(race_json.get("description"), race_json.get("title")):
        flags.append(
            {
                "field": "description",
                "concern": "Race description is missing, title-like, or too brief to explain the contest.",
                "suggestion": "Write a 3-4 sentence nonpartisan overview covering the office, candidates, political context, and key contrasts.",
                "severity": "error",
            }
        )

    seen_urls: Dict[str, str] = {}
    duplicate_urls: set[tuple[str, str]] = set()
    stale_sources: set[str] = set()
    now = datetime.now(timezone.utc)

    def _scan(value: Any, path: str) -> None:
        if isinstance(value, dict):
            url = value.get("url")
            if isinstance(url, str) and url:
                if url in seen_urls:
                    duplicate_urls.add((path, seen_urls[url]))
                else:
                    seen_urls[url] = path
                last_accessed = value.get("last_accessed")
                if last_accessed:
                    try:
                        accessed_at = datetime.fromisoformat(str(last_accessed).replace("Z", "+00:00"))
                        if accessed_at.tzinfo is None:
                            accessed_at = accessed_at.replace(tzinfo=timezone.utc)
                        if now - accessed_at > _STALE_ACCESS_THRESHOLD:
                            stale_sources.add(path)
                    except ValueError:
                        pass
            for key, child in value.items():
                _scan(child, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                _scan(child, f"{path}[{index}]")

    _scan(build_semantic_review_packet(race_json), "")
    for duplicate_path, original_path in sorted(duplicate_urls):
        flags.append(
            {
                "field": duplicate_path,
                "concern": f"Duplicate source URL also appears at {original_path}.",
                "suggestion": "Remove the redundant source entry.",
                "severity": "info",
            }
        )
    for path in sorted(stale_sources):
        flags.append(
            {
                "field": f"{path}.last_accessed",
                "concern": "Source access verification is more than one year old.",
                "suggestion": "Re-open the source and refresh last_accessed before publishing.",
                "severity": "warning",
            }
        )

    for poll_index, poll in enumerate(race_json.get("polling") or []):
        problem = polling_semantic_problem(poll, race_json.get("polling_note"))
        if problem:
            flags.append(
                {
                    "field": f"polling[{poll_index}]",
                    "concern": problem,
                    "suggestion": "Remove the entry or replace it with a genuine opinion poll from a named polling organization.",
                    "severity": "error",
                }
            )

    incumbency_problem = _implausible_incumbency_claim(race_json)
    if incumbency_problem:
        flags.append(
            {
                "field": "forecast.rationale",
                "concern": incumbency_problem,
                "suggestion": "Recalculate years and completed terms from the candidate's documented service dates.",
                "severity": "error",
            }
        )

    required_issues = {issue.value for issue in CanonicalIssue}
    state = race_json.get("pipeline_state") if isinstance(race_json.get("pipeline_state"), dict) else {}
    issue_attempts = state.get("issue_attempts") if isinstance(state.get("issue_attempts"), dict) else {}
    issue_research = state.get("issue_research") if isinstance(state.get("issue_research"), dict) else {}
    for index, candidate in enumerate(race_json.get("candidates") or []):
        if not isinstance(candidate, dict):
            continue
        issues = candidate.get("issues")
        issue_names = set(issues) if isinstance(issues, dict) else set()
        missing_issues = sorted(required_issues - issue_names)
        if missing_issues:
            flags.append(
                {
                    "field": f"candidates[{index}].issues",
                    "concern": f"Candidate is missing canonical issues: {', '.join(missing_issues)}.",
                    "suggestion": "Complete all canonical issue stances before final review."
                    if issues_step_ran
                    else "Issue research was not part of this run; queue the issues step when depth is wanted.",
                    "severity": "error" if issues_step_ran else "info",
                }
            )
        summary = candidate.get("summary")
        if isinstance(summary, str) and summary.strip() and not candidate.get("summary_sources"):
            flags.append(
                {
                    "field": f"candidates[{index}].summary_sources",
                    "concern": "Candidate summary has no supporting sources.",
                    "suggestion": "Add sources supporting the biographical and campaign claims in the summary.",
                    "severity": "warning",
                }
            )
        donor_summary = str(candidate.get("donor_summary") or "").strip()
        if donor_summary and not candidate.get("donor_sources") and not candidate.get("donor_source_url"):
            flags.append(
                {
                    "field": f"candidates[{index}].donor_sources",
                    "concern": "Candidate finance summary has no supporting sources.",
                    "suggestion": "Add an FEC filing or another reliable campaign-finance source.",
                    "severity": "warning",
                }
            )
        voting_summary = str(candidate.get("voting_summary") or "").strip()
        if voting_summary and not candidate.get("voting_sources") and not candidate.get("voting_source_url"):
            flags.append(
                {
                    "field": f"candidates[{index}].voting_sources",
                    "concern": "Candidate voting or public-record summary has no supporting sources.",
                    "suggestion": "Add official legislative, government, or reliable public-record sources.",
                    "severity": "warning",
                }
            )
        if isinstance(issues, dict):
            for issue_name, issue_data in issues.items():
                if not isinstance(issue_data, dict):
                    continue
                stance = str(issue_data.get("stance") or "").strip()
                attempt_key = f"issues:{candidate.get('name')}:{issue_name}"
                # The stance-level audit is durable; pipeline_state is rebuilt per
                # logical run and only describes the candidates that run touched.
                audit = issue_data.get("research_audit")
                if not isinstance(audit, dict):
                    audit = issue_research.get(attempt_key)
                researched_actions = (
                    int(audit.get("search_calls", 0) or 0) + int(audit.get("page_fetches", 0) or 0)
                    if isinstance(audit, dict)
                    else 0
                )
                # Attempt count comes from the same record as the rest of the audit,
                # so a durable stance-level audit is not defeated by run-scoped state.
                attempts = int(issue_attempts.get(attempt_key, 0) or 0)
                if isinstance(audit, dict) and audit.get("attempts") is not None:
                    attempts = max(attempts, int(audit.get("attempts") or 0))
                if _is_documented_absence(stance) and (
                    attempts < 1 or not isinstance(audit, dict) or audit.get("status") != "completed" or researched_actions < 2
                ):
                    flags.append(
                        {
                            "field": f"candidates[{index}].issues.{issue_name}.stance",
                            "concern": "No-position result lacks a completed audit with at least two recorded research actions.",
                            "suggestion": "Run the issues phase so absence is documented after an actual bounded search.",
                            "severity": "error",
                        }
                    )
                if stance and not _is_documented_absence(stance) and not issue_data.get("sources"):
                    flags.append(
                        {
                            "field": f"candidates[{index}].issues.{issue_name}.sources",
                            "concern": "Substantive issue stance has no supporting sources.",
                            "suggestion": "Add a source or record that no public position was found.",
                            "severity": "warning",
                        }
                    )
    verdict = "flagged" if flags else "approved"
    return {
        "model": "automated-profile-quality",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "score": None,
        "flags": flags,
        "summary": "Deterministic profile quality checks passed."
        if not flags
        else f"Found {len(flags)} profile quality issue(s).",
    }


async def run_reviews(
    race_id: str,
    race_json: Dict[str, Any],
    *,
    on_log: Optional[Callable] = None,
    cheap_mode: bool = True,
    claude_model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    grok_model: Optional[str] = None,
    review_providers: Optional[List[str]] = None,
    change_manifest: str = "Initial review. No previous revision is available.",
    semantic_packet: Optional[Dict[str, Any]] = None,
    metrics_sink: Optional[Dict[str, Any]] = None,
    review_cache: Optional[Dict[str, Any]] = None,
    run_budget: RunBudget | None = None,
    issues_step_ran: bool = True,
) -> List[Dict[str, Any]]:
    """Run review roles in parallel through OpenRouter."""
    import os

    requested_providers = (
        [provider for provider in review_providers if provider in _REVIEW_ROLES]
        if review_providers is not None
        else list(_REVIEW_ROLES)
    )

    if not os.environ.get("OPENROUTER_API_KEY"):
        log = make_logger(on_log)
        for provider in requested_providers:
            log("warning", f"  {provider} review failed: OPENROUTER_API_KEY is not set")
        return []

    packet = semantic_packet if semantic_packet is not None else build_semantic_review_packet(race_json)
    validate_semantic_review_packet(race_json, packet)
    profile_json = serialize_semantic_review_packet(packet)
    research_effort_context = build_issue_research_effort_context(race_json)
    packet_key = hashlib.sha256(f"{profile_json}\n{research_effort_context}".encode("utf-8")).hexdigest()
    if metrics_sink is not None:
        metrics_sink["whole_profile"] = True
        metrics_sink["configured_providers"] = requested_providers
        metrics_sink["packet_revisions"] = int(metrics_sink.get("packet_revisions", 0)) + 1
        metrics_sink["packet_chars"] = len(profile_json)
        metrics_sink["packet_estimated_tokens"] = max(1, len(profile_json) // 4)
    model_overrides = {"claude": claude_model, "gemini": gemini_model, "grok": grok_model}
    identity_context = race_identity_context(race_json)

    tasks = []
    for provider in requested_providers:
        effective_model = normalize_model_id(model_overrides.get(provider)) or _review_model_for(
            provider, cheap_mode=bool(cheap_mode)
        )
        tasks.append(
            _run_single_review(
                race_id,
                profile_json,
                provider=provider,
                model_override=effective_model,
                on_log=on_log,
                change_manifest=change_manifest,
                metrics_sink=metrics_sink,
                run_budget=run_budget,
                race_identity_context_text=identity_context,
                research_effort_context_text=research_effort_context,
            )
        )

    results = await asyncio.gather(*tasks)
    results_list = [r for r in results if r is not None]

    cache = review_cache if review_cache is not None else {}
    cached_deterministic = cache.get(packet_key)
    if cached_deterministic is None:
        link_review = await check_profile_links(race_json, on_log=on_log, run_budget=run_budget)
        removed_dead_sources = _remove_confirmed_dead_candidate_sources(race_json, link_review)
        if removed_dead_sources:
            if on_log:
                on_log(
                    "warning",
                    f"Removed {removed_dead_sources} candidate source occurrence(s) confirmed dead by HTTP status.",
                )
            link_review = await check_profile_links(race_json, on_log=on_log, run_budget=run_budget)
        quality_review = check_profile_quality(race_json, issues_step_ran=issues_step_ran)
        cached_deterministic = {
            "link_review": copy.deepcopy(link_review),
            "quality_review": copy.deepcopy(quality_review),
        }
        cache[packet_key] = cached_deterministic
    else:
        link_review = copy.deepcopy(cached_deterministic["link_review"])
        quality_review = copy.deepcopy(cached_deterministic["quality_review"])

    if link_review is not None:
        results_list.append(link_review)
    results_list.append(quality_review)

    return results_list


def compute_validation_grade(reviews: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Compute an aggregate validation grade from review scores."""
    automated_models = {"automated-link-validator", "automated-profile-quality"}
    eligible_reviews = [r for r in reviews if r.get("model") not in automated_models]

    scores = [r["score"] for r in eligible_reviews if isinstance(r.get("score"), (int, float))]
    if not scores:
        return None

    avg = round(sum(scores) / len(scores))
    avg = max(0, min(100, avg))
    flags = [flag for review in reviews for flag in (review.get("flags") or []) if isinstance(flag, dict)]
    error_flags = [flag for flag in flags if flag.get("severity") == "error"]
    warning_flags = [flag for flag in flags if flag.get("severity") == "warning"]

    # An error means something is demonstrably wrong — a placeholder candidate
    # name, an issue stance the pipeline was asked to research and did not. Those
    # still pin the grade below the pass mark however well the race scored.
    if error_flags:
        avg = min(avg, PASSING_SCORE - 1)

    # Warnings are advisory, and used to pin the score to the same place. Against
    # a pass mark of 80 that made a single warning an unconditional veto: a race
    # three models approved at an average of 93 graded C over three unsourced
    # stances and one dead link, and no further research could lift it, because
    # every surviving warning re-applied the identical cap. They now cost a fixed
    # amount each, so a strong review absorbs a couple and a weak one carrying
    # many still fails.
    avg = max(0, avg - WARNING_SCORE_PENALTY * len(warning_flags))

    if avg >= 90:
        grade = "A"
    elif avg >= 80:
        grade = "B"
    elif avg >= 70:
        grade = "C"
    elif avg >= 60:
        grade = "D"
    else:
        grade = "F"

    passed = avg >= PASSING_SCORE
    verdicts = [r.get("verdict", "") for r in eligible_reviews]
    approved_count = sum(1 for v in verdicts if v == "approved")
    total = len(eligible_reviews)

    deduction = (
        f"after a {WARNING_SCORE_PENALTY * len(warning_flags)}-point deduction for {len(warning_flags)} warning flag(s)"
    )
    if error_flags:
        summary = (
            f"Below quality threshold - {approved_count}/{total} reviewers approved, but {len(error_flags)} "
            f"error-severity flag(s) block publication (scored {avg}/100)."
        )
    elif passed and warning_flags:
        summary = f"Validated by {approved_count}/{total} reviewers at {avg}/100 {deduction}."
    elif passed:
        summary = f"Validated by {approved_count}/{total} reviewers with an average score of {avg}/100."
    elif warning_flags:
        summary = f"Below quality threshold - {approved_count}/{total} reviewers approved, {avg}/100 {deduction}."
    else:
        summary = f"Below quality threshold - {approved_count}/{total} reviewers approved, average score {avg}/100."

    return {"grade": grade, "score": avg, "passed": passed, "summary": summary}
