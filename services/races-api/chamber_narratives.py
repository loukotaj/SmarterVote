from __future__ import annotations

import json
import os
from typing import Any, Dict, Literal

import httpx

from shared.forecast_summary import build_chamber_context, get_chamber_forecast_system_prompt, summarize_chamber

Chamber = Literal["house", "senate", "governors"]

REQUIRED_ANALYSIS_KEYS = ["narrative", "bottom_line", "why_party_favored", "opposing_party_path", "key_uncertainty"]


def _office_matches(race: dict[str, Any], chamber: Chamber) -> bool:
    office = str(race.get("office") or "").lower()
    if chamber == "senate":
        return "senate" in office
    if chamber == "governors":
        return "governor" in office or "gubernatorial" in office
    return "house" in office or "representative" in office


def races_for_chamber(summaries: list[dict[str, Any]], chamber: Chamber) -> list[dict[str, Any]]:
    return [
        race
        for race in summaries
        if _office_matches(race, chamber) and not (chamber == "governors" and race.get("id") == "in-governor-2026")
    ]


def _strip_markdown_code_fence(content: str) -> str:
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


async def _call_openrouter(messages: list[dict[str, str]], *, model: str) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

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
    return resp.json()


async def generate_chamber_analysis(chamber_name: str, context_text: str, *, model: str) -> dict[str, str]:
    system_prompt = get_chamber_forecast_system_prompt(chamber_name)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Here is the aggregated forecast data for the {chamber_name}:\n\n{context_text}"},
    ]
    data = await _call_openrouter(messages, model=model)
    content = str(data["choices"][0]["message"]["content"]).strip()
    parsed = json.loads(_strip_markdown_code_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("OpenRouter chamber analysis response must be a JSON object")
    missing = [key for key in REQUIRED_ANALYSIS_KEYS if not parsed.get(key)]
    if missing:
        raise ValueError(f"OpenRouter chamber analysis missing required keys: {missing}")
    return {key: str(parsed[key]).strip() for key in REQUIRED_ANALYSIS_KEYS}


async def generate_chamber_analyses(summaries: list[dict[str, Any]], *, model: str) -> Dict[Chamber, dict[str, str]]:
    chamber_names: Dict[Chamber, str] = {"senate": "US Senate", "house": "US House", "governors": "Governors"}
    analyses: Dict[Chamber, dict[str, str]] = {}
    for chamber, name in chamber_names.items():
        races = races_for_chamber(summaries, chamber)
        summary = summarize_chamber(summaries, chamber)
        context = build_chamber_context(races, name, summary)
        analyses[chamber] = await generate_chamber_analysis(name, context, model=model)
    return analyses
