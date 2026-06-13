"""OpenRouter-backed review agents for fact-checking candidate profiles."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

from .llm import _call_openai
from .model_registry import (
    CHEAP_CLAUDE_MODEL,
    CHEAP_GEMINI_MODEL,
    CHEAP_GROK_MODEL,
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROK_MODEL,
    DEFAULT_POST_RUN_ANALYSIS_MODEL,
    normalize_model_id,
)
from .prompts import REVIEW_SYSTEM, REVIEW_USER
from .utils import _extract_json, make_logger
from .web_tools import _get_validated

logger = logging.getLogger("pipeline")

_REVIEW_MODELS = {
    "claude": (DEFAULT_CLAUDE_MODEL, CHEAP_CLAUDE_MODEL),
    "gemini": (DEFAULT_GEMINI_MODEL, CHEAP_GEMINI_MODEL),
    "grok": (DEFAULT_GROK_MODEL, CHEAP_GROK_MODEL),
}


async def _call_review_model(system: str, user: str, *, model: str) -> str:
    """Call any review model through OpenRouter and return text content."""
    response = await _call_openai(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=model,
        max_tokens=8192,
    )
    return response.choices[0].message.content or ""


async def _run_single_review(
    race_id: str,
    profile_json: str,
    *,
    provider: str,
    model_override: Optional[str] = None,
    on_log: Optional[Callable] = None,
) -> Optional[Dict[str, Any]]:
    """Run a single review agent role (claude, gemini, or grok)."""
    log = make_logger(on_log)
    user_prompt = REVIEW_USER.format(race_id=race_id, profile_json=profile_json)
    if provider not in _REVIEW_MODELS:
        return None
    full_model, _cheap_model = _REVIEW_MODELS[provider]
    model_name = normalize_model_id(model_override) or full_model
    try:
        log("info", f"  Reviewing with {model_name}...")
        raw = await _call_review_model(REVIEW_SYSTEM, user_prompt, model=model_name)

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
        if resp.status_code in (401, 403, 429):
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
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:

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

    clean = {k: v for k, v in race_json.items() if k not in ("reviews", "validation_grade")}
    profile_json = json.dumps(clean, indent=2, default=str)
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
            )
        )

    results = await asyncio.gather(*tasks)
    results_list = [r for r in results if r is not None]

    # Run the automated link checker and append the result
    link_review = await check_profile_links(race_json, on_log=on_log)
    if link_review is not None:
        results_list.append(link_review)

    return results_list


def compute_validation_grade(reviews: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Compute an aggregate validation grade from review scores."""
    scores = [r["score"] for r in reviews if isinstance(r.get("score"), (int, float))]
    if not scores:
        return None

    avg = round(sum(scores) / len(scores))
    avg = max(0, min(100, avg))
    error_flags = [
        flag
        for review in reviews
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
    verdicts = [r.get("verdict", "") for r in reviews]
    approved_count = sum(1 for v in verdicts if v == "approved")
    total = len(reviews)

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


_MAX_LOG_CHARS = 300_000


async def run_post_run_analysis(
    run_id: str,
    race_id: str,
    logs: List[Dict[str, Any]],
    *,
    artifact: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyze run logs and output through OpenRouter."""
    from .prompts import (
        DISCOVERY_SYSTEM,
        FINANCE_VOTING_SYSTEM,
        ISSUE_SUBAGENT_SYSTEM,
        ITERATE_SYSTEM,
        POST_RUN_ANALYSIS_SYSTEM,
        POST_RUN_ANALYSIS_USER,
        REFINE_SYSTEM,
    )

    effective_model = normalize_model_id(model) or DEFAULT_POST_RUN_ANALYSIS_MODEL

    log_lines = [f"[{e.get('timestamp', '')}] {e.get('level', 'info').upper():7s} {e.get('message', '')}" for e in logs]
    logs_text = "\n".join(log_lines)
    if len(logs_text) > _MAX_LOG_CHARS:
        logs_text = "... (truncated - showing last portion) ...\n" + logs_text[-_MAX_LOG_CHARS:]

    user_prompt = POST_RUN_ANALYSIS_USER.format(
        run_id=run_id,
        race_id=race_id,
        discovery_system=DISCOVERY_SYSTEM,
        issue_system=ISSUE_SUBAGENT_SYSTEM,
        refine_system=REFINE_SYSTEM,
        finance_system=FINANCE_VOTING_SYSTEM,
        iterate_system=ITERATE_SYSTEM,
        log_count=len(logs),
        logs_text=logs_text,
    )

    if artifact:
        artifact_text = json.dumps(artifact, indent=2, default=str)
        if len(artifact_text) > 100_000:
            artifact_text = artifact_text[:100_000] + "\n... (truncated)"
        user_prompt += f"\n\n## Output Artifact (RaceJSON)\n\n```json\n{artifact_text}\n```"

    logger.info("Post-run analysis: sending %s log entries to %s", len(logs), effective_model)
    try:
        analysis_text = await _call_review_model(POST_RUN_ANALYSIS_SYSTEM, user_prompt, model=effective_model)
    except Exception as exc:
        logger.warning("Post-run analysis failed: %s", exc)
        return {"skipped": True, "reason": str(exc)}

    return {
        "run_id": run_id,
        "race_id": race_id,
        "model": effective_model,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "log_count": len(logs),
        "analysis": analysis_text,
    }
