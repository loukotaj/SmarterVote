from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Literal

import httpx

from shared.forecast_summary import (
    build_chamber_context,
    election_cycle_year,
    get_chamber_forecast_system_prompt,
    get_chamber_narrative_review_prompt,
    is_chamber_control_race,
    summarize_chamber,
)

Chamber = Literal["house", "senate", "governors"]

REQUIRED_ANALYSIS_KEYS = ["narrative", "bottom_line", "why_party_favored", "opposing_party_path", "key_uncertainty"]


def races_for_chamber(summaries: list[dict[str, Any]], chamber: Chamber) -> list[dict[str, Any]]:
    """Races the narrative should describe — the same set `summarize_chamber` counts."""
    return [race for race in summaries if is_chamber_control_race(race, chamber)]


def _strip_markdown_code_fence(content: str) -> str:
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# OpenRouter answers a rate limit or an upstream provider failure with HTTP 429
# or 5xx, and both clear on their own within seconds.  Losing a whole chamber
# forecast to one is needless.
_RETRY_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 4


def _extract_choice_content(data: dict[str, Any]) -> str:
    """Return the completion text, explaining clearly when there is none.

    OpenRouter reports a rate limit or a provider outage as HTTP 200 carrying an
    ``error`` object instead of ``choices``.  Indexing straight into the
    response turned that into a bare ``KeyError: 'choices'``, which surfaced to
    the caller as "chamber forecast generation failed: 'choices'" and said
    nothing about the actual cause.
    """
    error = data.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise ValueError(f"OpenRouter returned an error instead of a completion: {message}")
    choices = data.get("choices")
    if not choices:
        raise ValueError("OpenRouter returned no choices and no error; the response was empty")
    return str(choices[0]["message"]["content"]).strip()


async def _call_openrouter(messages: list[dict[str, str]], *, model: str) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=240) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://smarter.vote"),
                        "X-Title": os.getenv("OPENROUTER_APP_TITLE", "SmarterVote"),
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 16384,
                        "temperature": 0.2,
                    },
                )
            resp.raise_for_status()
            data = resp.json()
            error = data.get("error") if isinstance(data, dict) else None
            raw_code = error.get("code") if isinstance(error, dict) else None
            try:
                error_code = int(raw_code)
            except (TypeError, ValueError):
                error_code = None
            if error_code not in _RETRY_STATUS_CODES:
                return data
            message = error.get("message") or f"provider error {error_code}"
            last_error = ValueError(f"OpenRouter returned an error instead of a completion: {message}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRY_STATUS_CODES:
                raise
            last_error = exc
        except httpx.ReadTimeout:
            # A full 240-second generation timeout has already exceeded the
            # request's useful wall-clock budget. Retrying it up to three more
            # times would leave backend work running long after the gateway
            # has given up.
            raise
        except httpx.TransportError as exc:
            last_error = exc
        if attempt < _MAX_ATTEMPTS - 1:
            await asyncio.sleep(2**attempt)

    assert last_error is not None
    raise last_error


async def generate_chamber_analysis(
    chamber_name: str, context_text: str, *, model: str, cycle_year: str | None = None
) -> dict[str, str]:
    system_prompt = get_chamber_forecast_system_prompt(chamber_name, cycle_year)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Here is the aggregated forecast data for the {chamber_name}:\n\n{context_text}"},
    ]
    data = await _call_openrouter(messages, model=model)
    content = _extract_choice_content(data)
    parsed = json.loads(_strip_markdown_code_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("OpenRouter chamber analysis response must be a JSON object")
    missing = [key for key in REQUIRED_ANALYSIS_KEYS if not parsed.get(key)]
    if missing:
        raise ValueError(f"OpenRouter chamber analysis missing required keys: {missing}")
    return {key: str(parsed[key]).strip() for key in REQUIRED_ANALYSIS_KEYS}


async def review_chamber_analysis(
    chamber_name: str,
    context_text: str,
    analysis: dict[str, str],
    *,
    model: str,
    goal: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Re-read a drafted analysis against its own data and correct contradictions.

    Returns the analysis and the corrections applied. On any failure the draft
    comes back untouched: a review pass that cannot run is not a reason to lose
    an otherwise usable narrative.
    """
    messages = [
        {"role": "system", "content": get_chamber_narrative_review_prompt(chamber_name, goal)},
        {
            "role": "user",
            "content": (
                f"Authoritative forecast data for the {chamber_name}:\n\n{context_text}\n\n"
                f"Drafted analysis to review:\n\n{json.dumps(analysis, indent=2)}"
            ),
        },
    ]
    try:
        data = await _call_openrouter(messages, model=model)
        content = _extract_choice_content(data)
        parsed = json.loads(_strip_markdown_code_fence(content))
        if not isinstance(parsed, dict):
            raise ValueError("chamber narrative review response must be a JSON object")
        missing = [key for key in REQUIRED_ANALYSIS_KEYS if not parsed.get(key)]
        if missing:
            raise ValueError(f"chamber narrative review missing required keys: {missing}")
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError):
        return analysis, []

    corrections = [str(item).strip() for item in (parsed.get("corrections") or []) if str(item).strip()]
    return {key: str(parsed[key]).strip() for key in REQUIRED_ANALYSIS_KEYS}, corrections


async def generate_chamber_analyses(
    summaries: list[dict[str, Any]],
    *,
    model: str,
    review: bool = False,
    goal: str | None = None,
) -> Dict[Chamber, dict[str, str]]:
    chamber_names: Dict[Chamber, str] = {"senate": "US Senate", "house": "US House", "governors": "Governors"}
    cycle_year = election_cycle_year(summaries)
    analyses: Dict[Chamber, dict[str, str]] = {}
    for chamber, name in chamber_names.items():
        races = races_for_chamber(summaries, chamber)
        summary = summarize_chamber(summaries, chamber)
        context = build_chamber_context(races, name, summary)
        analysis = await generate_chamber_analysis(name, context, model=model, cycle_year=cycle_year)
        if review:
            analysis, corrections = await review_chamber_analysis(name, context, analysis, model=model, goal=goal)
            if corrections:
                analysis = {**analysis, "review_corrections": corrections}
        analyses[chamber] = analysis
    return analyses
