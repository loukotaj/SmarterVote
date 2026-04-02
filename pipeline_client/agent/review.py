"""Multi-LLM review agents (Claude, Gemini, Grok) for fact-checking candidate profiles."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .cost import accumulate
from .prompts import REVIEW_SYSTEM, REVIEW_USER
from .utils import _extract_json, make_logger

logger = logging.getLogger("pipeline")

# Review models (full quality)
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_GROK_MODEL = "grok-3"

# Review models (cheap mode)
CHEAP_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CHEAP_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
CHEAP_GROK_MODEL = "grok-3-mini"

_REVIEW_PROVIDERS = {
    "claude": ("ANTHROPIC_API_KEY", DEFAULT_CLAUDE_MODEL, CHEAP_CLAUDE_MODEL),
    "gemini": ("GEMINI_API_KEY", DEFAULT_GEMINI_MODEL, CHEAP_GEMINI_MODEL),
    "grok": ("XAI_API_KEY", DEFAULT_GROK_MODEL, CHEAP_GROK_MODEL),
}


async def _call_anthropic(system: str, user: str, *, model: str = DEFAULT_CLAUDE_MODEL) -> str:
    """Call the Anthropic Messages API and return the text response."""
    from anthropic import AsyncAnthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if response.usage:
        accumulate(response.usage.input_tokens, response.usage.output_tokens, model)
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


async def _call_gemini(system: str, user: str, *, model: str = DEFAULT_GEMINI_MODEL) -> str:
    """Call the Google Gemini API via the google-genai client and return the text response."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    from google import genai  # type: ignore

    client = genai.Client(api_key=api_key)
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=model,
            contents=f"{system}\n\n{user}",
        ),
    )
    try:
        um = response.usage_metadata
        accumulate(um.prompt_token_count or 0, um.candidates_token_count or 0, model)
    except Exception:
        pass
    return response.text or ""


async def _call_grok(system: str, user: str, *, model: str = DEFAULT_GROK_MODEL) -> str:
    """Call the xAI Grok API (OpenAI-compatible) and return the text response."""
    from openai import AsyncOpenAI

    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set")

    client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1", timeout=120)
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    if response.usage:
        accumulate(response.usage.prompt_tokens or 0, response.usage.completion_tokens or 0, model)
    return response.choices[0].message.content or ""


async def _run_single_review(
    race_id: str,
    profile_json: str,
    *,
    provider: str,
    model_override: Optional[str] = None,
    on_log: Optional[Callable] = None,
) -> Optional[Dict[str, Any]]:
    """Run a single review agent (claude, gemini, or grok)."""
    log = make_logger(on_log)
    user_prompt = REVIEW_USER.format(race_id=race_id, profile_json=profile_json)
    model_name = ""
    try:
        if provider == "claude":
            model_name = model_override or DEFAULT_CLAUDE_MODEL
            log("info", f"  Reviewing with {model_name}...")
            raw = await _call_anthropic(REVIEW_SYSTEM, user_prompt, model=model_name)
        elif provider == "gemini":
            model_name = model_override or DEFAULT_GEMINI_MODEL
            log("info", f"  Reviewing with {model_name}...")
            raw = await _call_gemini(REVIEW_SYSTEM, user_prompt, model=model_name)
        elif provider == "grok":
            model_name = model_override or DEFAULT_GROK_MODEL
            log("info", f"  Reviewing with {model_name}...")
            raw = await _call_grok(REVIEW_SYSTEM, user_prompt, model=model_name)
        else:
            return None

        try:
            review_data = _extract_json(raw)
        except (json.JSONDecodeError, ValueError):
            log("warning", f"  {provider} review returned malformed JSON — skipping")
            return None

        return {
            "model": model_name,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "verdict": review_data.get("verdict", "flagged"),
            "flags": review_data.get("flags", []),
            "summary": review_data.get("summary", ""),
        }
    except Exception as exc:
        log("warning", f"  {provider} review failed: {exc}")
        return None


async def run_reviews(
    race_id: str,
    race_json: Dict[str, Any],
    *,
    on_log: Optional[Callable] = None,
    cheap_mode: bool = True,
    claude_model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    grok_model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run reviews with all available providers in parallel."""
    profile_json = json.dumps(race_json, indent=2, default=str)
    log = make_logger(on_log)
    model_overrides = {"claude": claude_model, "gemini": gemini_model, "grok": grok_model}

    tasks = []
    for provider, (env_key, full_model, cheap_model_name) in _REVIEW_PROVIDERS.items():
        if not os.environ.get(env_key):
            log("info", f"  Skipping {provider} review ({env_key} not set)")
            continue
        effective_model = model_overrides.get(provider) or (
            cheap_model_name if cheap_mode else full_model
        )
        tasks.append(_run_single_review(
            race_id, profile_json,
            provider=provider,
            model_override=effective_model,
            on_log=on_log,
        ))

    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Post-run improvement analysis via Gemini Flash
# ---------------------------------------------------------------------------

# Max characters of logs to send — Gemini Flash has a large context window but
# we cap here to keep costs reasonable (~300k chars ≈ ~75k tokens).
_MAX_LOG_CHARS = 300_000


async def run_post_run_analysis(
    run_id: str,
    race_id: str,
    logs: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Call Gemini Flash with the full run logs + system prompts and ask for
    improvement suggestions.  Returns a dict suitable for JSON serialisation."""
    from .prompts import (
        DISCOVERY_SYSTEM,
        FINANCE_VOTING_SYSTEM,
        ISSUE_SUBAGENT_SYSTEM,
        ITERATE_SYSTEM,
        POST_RUN_ANALYSIS_SYSTEM,
        POST_RUN_ANALYSIS_USER,
        REFINE_SYSTEM,
    )

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.info("Post-run analysis skipped: GEMINI_API_KEY not set")
        return {"skipped": True, "reason": "GEMINI_API_KEY not set"}

    effective_model = model or DEFAULT_GEMINI_MODEL

    # Format logs as plain text, newest-last, truncated if necessary
    log_lines = [
        f"[{e.get('timestamp', '')}] {e.get('level', 'info').upper():7s} {e.get('message', '')}"
        for e in logs
    ]
    logs_text = "\n".join(log_lines)
    if len(logs_text) > _MAX_LOG_CHARS:
        logs_text = "... (truncated — showing last portion) ...\n" + logs_text[-_MAX_LOG_CHARS:]

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

    logger.info(f"Post-run analysis: sending {len(logs)} log entries to {effective_model}")
    try:
        analysis_text = await _call_gemini(POST_RUN_ANALYSIS_SYSTEM, user_prompt, model=effective_model)
    except Exception as exc:
        logger.warning(f"Post-run analysis failed: {exc}")
        return {"skipped": True, "reason": str(exc)}

    return {
        "run_id": run_id,
        "race_id": race_id,
        "model": effective_model,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "log_count": len(logs),
        "analysis": analysis_text,
    }
