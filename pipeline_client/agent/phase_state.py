"""Durable state helpers shared by pipeline phase orchestration."""

from __future__ import annotations

from typing import Any, Dict, List


def completed_units(race_json: Dict[str, Any]) -> set[str]:
    state = race_json.get("pipeline_state")
    if not isinstance(state, dict):
        state = {}
        race_json["pipeline_state"] = state
    units = state.get("completed_units")
    if not isinstance(units, list):
        units = []
        state["completed_units"] = units
    return {str(unit) for unit in units}


def mark_unit_complete(race_json: Dict[str, Any], unit: str) -> None:
    state = race_json.setdefault("pipeline_state", {})
    units = state.setdefault("completed_units", [])
    if unit not in units:
        units.append(unit)


def issue_stance_is_complete(value: Any) -> bool:
    from pipeline_client.agent.agent import _is_missing_stance_text

    if not isinstance(value, dict):
        return False
    stance = str(value.get("stance") or "").strip()
    return bool(stance) and not _is_missing_stance_text(stance)


def issue_attempts(race_json: Dict[str, Any]) -> Dict[str, int]:
    state = race_json.setdefault("pipeline_state", {})
    attempts = state.get("issue_attempts")
    if not isinstance(attempts, dict):
        attempts = {}
    normalized = {str(unit): max(0, int(count or 0)) for unit, count in attempts.items()}
    state["issue_attempts"] = normalized
    return normalized


def build_handoff_context(
    handoffs: List[Dict[str, Any]],
    cached_info: Dict[str, Any] | None,
) -> str:
    parts: List[str] = []
    if handoffs:
        parts.append("Previous stances already written for this candidate:")
        for handoff in handoffs:
            parts.append(f"  - {handoff['issue']}: {handoff['stance'][:120]} [{handoff['confidence']}]")
        parts.append("")

    if cached_info:
        searches = cached_info.get("searches", [])
        if searches:
            parts.append(f"Cached search queries available (results served instantly, {len(searches)} total):")
            for search in searches[:5]:
                parts.append(f"  - \"{search['query']}\"")
            parts.append("")

    return "\n".join(parts) if parts else "No prior context available."
