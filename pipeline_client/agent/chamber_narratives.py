from __future__ import annotations

import json
from typing import Any, Dict, Literal

from shared.forecast_summary import summarize_chamber

from .llm import _call_openrouter

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


def build_chamber_context(races: list[dict[str, Any]], name: str, summary: dict[str, Any]) -> str:
    if not races:
        return f"No published races found for the {name}."

    dem_wins = 0
    gop_wins = 0
    toss_ups = 0
    competitive_list = []
    for race in races:
        forecast = race.get("forecast") or {}
        rating = str(forecast.get("rating") or "").lower()
        winner_party = str(forecast.get("predicted_winner_party") or "").lower()
        prob = forecast.get("win_probability") or 0.5
        title = race.get("title") or race.get("id")
        if "toss-up" in rating or "tossup" in rating:
            toss_ups += 1
            competitive_list.append(f"- {title}: Toss-up (Win Prob: {prob * 100:.1f}%)")
        elif "tilt" in rating:
            competitive_list.append(f"- {title}: Tilt {winner_party.upper()} (Win Prob: {prob * 100:.1f}%)")
            if "democrat" in winner_party:
                dem_wins += 1
            elif "republican" in winner_party or "gop" in winner_party:
                gop_wins += 1
        elif "lean" in rating:
            competitive_list.append(f"- {title}: Lean {winner_party.upper()} (Win Prob: {prob * 100:.1f}%)")
            if "democrat" in winner_party:
                dem_wins += 1
            elif "republican" in winner_party or "gop" in winner_party:
                gop_wins += 1
        elif "likely" in rating:
            competitive_list.append(f"- {title}: Likely {winner_party.upper()} (Win Prob: {prob * 100:.1f}%)")
            if "democrat" in winner_party:
                dem_wins += 1
            elif "republican" in winner_party or "gop" in winner_party:
                gop_wins += 1
        elif "safe" in rating:
            if "democrat" in winner_party:
                dem_wins += 1
            elif "republican" in winner_party or "gop" in winner_party:
                gop_wins += 1

    expected_d = summary.get("expected_seats", {}).get("Democratic", 0.0)
    expected_r = summary.get("expected_seats", {}).get("Republican", 0.0)
    projected_d = summary.get("projected_seats", {}).get("Democratic", 0)
    projected_r = summary.get("projected_seats", {}).get("Republican", 0)
    control_party = summary.get("control_party", "Other")
    control_prob = summary.get("control_probability", 0.5)
    outcome_probs = summary.get("outcome_probabilities", {})
    tie_prob = outcome_probs.get("tie_50_50", 0.0) if name == "US Senate" else 0.0

    lines = [
        f"Chamber: {name}",
        f"Total Published Races: {len(races)}",
        f"Toss-up Races: {toss_ups}",
        f"Projected Democratic Wins (among published non-tossups): {dem_wins}",
        f"Projected Republican Wins (among published non-tossups): {gop_wins}",
        "",
        "Aggregated Mathematical Model Results:",
        f"- Projected Control: {control_party} control projected (prob: {control_prob * 100:.1f}%)",
        f"- Projected Seats: {projected_d} Democratic, {projected_r} Republican",
        f"- Expected (Mean) Seats: {expected_d:.1f} Democratic, {expected_r:.1f} Republican",
    ]

    if name == "US Senate":
        lines.append(
            f"- Probability of a 50-50 tie: {tie_prob * 100:.1f}% "
            "(Note: 50-50 tie results in Republican control via VP tie-break)"
        )
        dist = summary.get("seat_distribution", {})
        if dist:
            sorted_dist = sorted(dist.items(), key=lambda item: item[1], reverse=True)
            top_outcomes = [f"{key} ({value * 100:.1f}%)" for key, value in sorted_dist[:4]]
            lines.append(f"- Top 4 most likely seat outcomes: {', '.join(top_outcomes)}")

    lines.append("\nCompetitive/Notable Races Detail:")
    lines.extend(competitive_list[:30])
    return "\n".join(lines)


async def generate_chamber_analysis(chamber_name: str, context_text: str, *, model: str) -> dict[str, str]:
    system_prompt = (
        "You are a professional, nonpartisan election forecaster. "
        f"Output a JSON object containing forecast analysis for the {chamber_name} in the 2026 election cycle. "
        "Write like a short, sharp analyst note, not an AI report. Avoid generic filler and boilerplate.\n\n"
        "The JSON object must have EXACTLY these string keys:\n"
        "- narrative: 2-4 sentences summarizing control, closeness, key races, and what could change.\n"
        "- bottom_line: one sentence summarizing the projection.\n"
        "- why_party_favored: why the favored party is projected to win or control the chamber.\n"
        "- opposing_party_path: the realistic path for the opposing party to win control.\n"
        "- key_uncertainty: the key uncertainty or risk factors.\n\n"
        "Every field must name specific races or race groups from the context. Avoid vague text like "
        "'needs to win competitive races' unless immediately followed by examples. Explain the path through seats, "
        "ratings, and named contests.\n\n"
        "Output only the JSON object, with no markdown code blocks and no extra text."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Here is the aggregated forecast data for the {chamber_name}:\n\n{context_text}"},
    ]
    resp = await _call_openrouter(messages=messages, model=model)
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    parsed = json.loads(content)
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
