"""Multi-LLM review agents (Claude, Gemini, Grok) for fact-checking candidate profiles."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

from .prompts import REVIEW_SYSTEM, REVIEW_USER
from .utils import _extract_json, make_logger

logger = logging.getLogger("pipeline")

# Review models (full quality)
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"
DEFAULT_GROK_MODEL = "grok-3"

# Review models (cheap mode)
CHEAP_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CHEAP_GEMINI_MODEL = "gemini-2.0-flash"
CHEAP_GROK_MODEL = "grok-3-mini"

_REVIEW_PROVIDERS = {
    "claude": ("ANTHROPIC_API_KEY", DEFAULT_CLAUDE_MODEL, CHEAP_CLAUDE_MODEL),
    "gemini": ("GEMINI_API_KEY", DEFAULT_GEMINI_MODEL, CHEAP_GEMINI_MODEL),
    "grok": ("XAI_API_KEY", DEFAULT_GROK_MODEL, CHEAP_GROK_MODEL),
}


async def _call_anthropic(system: str, user: str, *, model: str = DEFAULT_CLAUDE_MODEL) -> str:
    """Call the Anthropic Messages API and return the text response."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 8192,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block["text"]
    return ""


async def _call_gemini(system: str, user: str, *, model: str = DEFAULT_GEMINI_MODEL) -> str:
    """Call the Google Gemini API and return the text response."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                return part["text"]
    return ""


async def _call_grok(system: str, user: str, *, model: str = DEFAULT_GROK_MODEL) -> str:
    """Call the xAI Grok API (OpenAI-compatible) and return the text response."""
    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


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
