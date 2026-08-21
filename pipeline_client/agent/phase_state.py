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
    # A no-position result is terminal only when it carries the same evidence
    # that publication review requires. Otherwise a continuation must retry it;
    # treating the text alone as complete makes targeted provenance repairs skip
    # the exact issue they were queued to fix.
    if "no public position found" in stance.lower():
        if value.get("sources"):
            return True
        audit = value.get("research_audit")
        if not isinstance(audit, dict) or audit.get("status") != "completed":
            return False
        research_actions = int(audit.get("search_calls", 0) or 0) + int(audit.get("page_fetches", 0) or 0)
        return research_actions >= 2
    return bool(stance) and not _is_missing_stance_text(stance)


def issue_attempts(race_json: Dict[str, Any]) -> Dict[str, int]:
    state = race_json.setdefault("pipeline_state", {})
    attempts = state.get("issue_attempts")
    if not isinstance(attempts, dict):
        attempts = {}
    normalized = {str(unit): max(0, int(count or 0)) for unit, count in attempts.items()}
    state["issue_attempts"] = normalized
    return normalized


def race_identity_context(race_json: Dict[str, Any]) -> str:
    """Render the locked race-identity brief for injection into downstream prompts.

    Discovery and roster-sync record ``pipeline_state.race_identity`` (office,
    state, district, contest stage, election date, primary status, official
    roster source, known incumbent, known ineligible/not-running people) before
    candidate work begins. Every later phase — issue research, finance, polling,
    forecast, review, and iteration — should see this same locked identity so it
    cannot drift onto a different office, state, district, or election cycle
    partway through a run. Falls back to the race's own top-level fields when no
    identity brief has been recorded yet (e.g. a draft created before this field
    existed), and to an explicit "not recorded" notice when even those are empty.
    """
    state = race_json.get("pipeline_state")
    identity = state.get("race_identity") if isinstance(state, dict) else None
    if not isinstance(identity, dict):
        identity = {}

    office = identity.get("office") or race_json.get("office")
    state_name = identity.get("state") or race_json.get("state")
    district = identity.get("district") or race_json.get("district")
    contest_stage = identity.get("contest_stage") or race_json.get("contest_stage")
    election_date = identity.get("election_date") or race_json.get("election_date")
    primary_status = identity.get("primary_status")
    official_source = identity.get("official_roster_source_url")
    known_incumbent = identity.get("known_incumbent")
    ineligible = identity.get("known_ineligible_or_not_running")

    if not any(
        [
            office,
            state_name,
            district,
            contest_stage,
            election_date,
            primary_status,
            official_source,
            known_incumbent,
            ineligible,
        ]
    ):
        return (
            "Race identity: not yet locked. Do not attribute a fact, vote, donor, or "
            "candidacy from a different office, state, district, or election cycle to "
            "this race."
        )

    lines = ["Locked race identity (do not drift from this exact contest):"]
    if office:
        lines.append(f"- Office: {office}")
    if state_name:
        lines.append(f"- State: {state_name}")
    if district:
        lines.append(f"- District: {district}")
    if election_date:
        lines.append(f"- Election date: {election_date}")
    if known_incumbent:
        lines.append(f"- Known incumbent: {known_incumbent}")
    if ineligible:
        names = ", ".join(str(name) for name in ineligible if str(name).strip())
        if names:
            lines.append(f"- Known ineligible/not running (never re-add or attribute facts to these): {names}")
    if official_source:
        lines.append(f"- Official roster source: {official_source}")
    lines.append(
        "Every fact, source, vote, and dollar amount you record must belong to this "
        "exact office/state/district — not a different race in the same state or a "
        "different election cycle."
    )
    # Contest stage advances with the calendar, so it is deliberately NOT part of the
    # locked block above: presenting it as locked identity caused a stale "pre_primary"
    # to be re-asserted run after run long after the primary had been decided.
    if contest_stage or primary_status:
        lines.append("")
        lines.append("Time-sensitive status as last observed (re-verify against today's date; update it if it moved on):")
        if contest_stage:
            lines.append(f"- Contest stage was recorded as: {contest_stage}")
        if primary_status:
            lines.append(f"- Primary status was recorded as: {primary_status}")
        lines.append(
            "If a primary, runoff, or filing deadline has since concluded, record the current "
            "stage with set_race_identity instead of repeating the stored value."
        )
    return "\n".join(lines)


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
