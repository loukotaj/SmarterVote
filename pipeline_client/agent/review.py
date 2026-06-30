"""OpenRouter-backed review agents for fact-checking candidate profiles."""

import asyncio
import copy
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from shared.models import Candidate, CanonicalIssue, RaceJSON
from shared.pipeline_config import REVIEW_PROVIDERS

from .cost import estimate_cost
from .llm import _call_openrouter, _provider_usage_cost
from .model_registry import (
    CHEAP_CLAUDE_MODEL,
    CHEAP_GEMINI_MODEL,
    CHEAP_GROK_MODEL,
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROK_MODEL,
    normalize_model_id,
)
from .prompts import REVIEW_SYSTEM, REVIEW_USER
from .run_budget import RunBudget, RunBudgetExceeded
from .utils import _extract_json, make_logger
from .web_tools import _get_validated

logger = logging.getLogger("pipeline")

_REVIEW_MODELS = {
    REVIEW_PROVIDERS[0]: (DEFAULT_CLAUDE_MODEL, CHEAP_CLAUDE_MODEL),
    REVIEW_PROVIDERS[1]: (DEFAULT_GEMINI_MODEL, CHEAP_GEMINI_MODEL),
    REVIEW_PROVIDERS[2]: (DEFAULT_GROK_MODEL, CHEAP_GROK_MODEL),
}

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
) -> Optional[Dict[str, Any]]:
    """Run a single review agent role (claude, gemini, or grok)."""
    log = make_logger(on_log)
    user_prompt = REVIEW_USER.format(race_id=race_id, profile_json=profile_json, change_manifest=change_manifest)
    if provider not in _REVIEW_MODELS:
        return None
    full_model, _cheap_model = _REVIEW_MODELS[provider]
    model_name = normalize_model_id(model_override) or full_model
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


async def _verify_url(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Check whether a URL is reachable through the SSRF-safe fetch path."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        }
        resp = await _get_validated(client, url, headers=headers)
        if _is_access_restricted_response(url, resp.status_code):
            return None
        if resp.status_code >= 400:
            return f"HTTP error {resp.status_code}"
        return None
    except (httpx.HTTPError, ValueError) as exc:
        return f"Request failed: {exc}"
    except Exception as exc:
        return f"Error: {exc}"


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
            flags.append(
                {
                    "field": path,
                    "concern": f"Cited source URL ({url}) returned a dead link: {err}.",
                    "suggestion": "Verify the URL, find a replacement source, and update the stance.",
                    "severity": "warning",
                }
            )

    verdict = "flagged" if flags else "approved"
    summary = f"Scanned {len(urls_to_check)} source links. Found {len(flags)} dead link(s)."
    log("info", f"  Link Validator: {verdict} ({len(flags)} dead links found)")

    return {
        "model": "automated-link-validator",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "score": None,
        "flags": flags,
        "summary": summary,
    }


def check_profile_quality(race_json: Dict[str, Any]) -> Dict[str, Any]:
    """Run deterministic checks for important quality failures reviewers may miss."""
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

    required_issues = {issue.value for issue in CanonicalIssue}
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
                    "suggestion": "Complete all canonical issue stances before final review.",
                    "severity": "error",
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
        if isinstance(issues, dict):
            for issue_name, issue_data in issues.items():
                if not isinstance(issue_data, dict):
                    continue
                stance = str(issue_data.get("stance") or "").strip()
                if stance and stance.casefold() != "no public position found" and not issue_data.get("sources"):
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
) -> List[Dict[str, Any]]:
    """Run review roles in parallel through OpenRouter."""
    import os

    requested_providers = (
        [provider for provider in review_providers if provider in _REVIEW_MODELS]
        if review_providers is not None
        else list(_REVIEW_MODELS)
    )

    if not os.environ.get("OPENROUTER_API_KEY"):
        log = make_logger(on_log)
        for provider in requested_providers:
            log("warning", f"  {provider} review failed: OPENROUTER_API_KEY is not set")
        return []

    packet = semantic_packet if semantic_packet is not None else build_semantic_review_packet(race_json)
    validate_semantic_review_packet(race_json, packet)
    profile_json = serialize_semantic_review_packet(packet)
    packet_key = hashlib.sha256(profile_json.encode("ascii")).hexdigest()
    if metrics_sink is not None:
        metrics_sink["whole_profile"] = True
        metrics_sink["configured_providers"] = requested_providers
        metrics_sink["packet_revisions"] = int(metrics_sink.get("packet_revisions", 0)) + 1
        metrics_sink["packet_chars"] = len(profile_json)
        metrics_sink["packet_estimated_tokens"] = max(1, len(profile_json) // 4)
    model_overrides = {"claude": claude_model, "gemini": gemini_model, "grok": grok_model}

    tasks = []
    for provider in requested_providers:
        full_model, cheap_model_name = _REVIEW_MODELS[provider]
        effective_model = normalize_model_id(model_overrides.get(provider)) or (cheap_model_name if cheap_mode else full_model)
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
            )
        )

    results = await asyncio.gather(*tasks)
    results_list = [r for r in results if r is not None]

    cache = review_cache if review_cache is not None else {}
    cached_deterministic = cache.get(packet_key)
    if cached_deterministic is None:
        link_review = await check_profile_links(race_json, on_log=on_log, run_budget=run_budget)
        quality_review = check_profile_quality(race_json)
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
    # Exclude automated link validator and automated profile quality from scoring and publish gates
    excluded_models = {"automated-link-validator", "automated-profile-quality"}
    eligible_reviews = [r for r in reviews if r.get("model") not in excluded_models]

    scores = [r["score"] for r in eligible_reviews if isinstance(r.get("score"), (int, float))]
    if not scores:
        return None

    avg = round(sum(scores) / len(scores))
    avg = max(0, min(100, avg))
    error_flags = [
        flag
        for review in eligible_reviews
        for flag in (review.get("flags") or [])
        if isinstance(flag, dict) and flag.get("severity") == "error"
    ]
    if error_flags:
        avg = min(avg, 79)

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

    passed = avg >= 80
    verdicts = [r.get("verdict", "") for r in eligible_reviews]
    approved_count = sum(1 for v in verdicts if v == "approved")
    total = len(eligible_reviews)

    if error_flags:
        summary = (
            f"Below quality threshold - {approved_count}/{total} reviewers approved, average score capped at {avg}/100 "
            f"because {len(error_flags)} error-severity flag(s) remain."
        )
    elif passed:
        summary = f"Validated by {approved_count}/{total} reviewers with an average score of {avg}/100."
    else:
        summary = f"Below quality threshold - {approved_count}/{total} reviewers approved, average score {avg}/100."

    return {"grade": grade, "score": avg, "passed": passed, "summary": summary}
