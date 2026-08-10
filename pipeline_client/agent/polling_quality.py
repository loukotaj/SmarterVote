"""Deterministic semantic checks for race polling entries."""

from __future__ import annotations

from typing import Any, Optional

_PLACEHOLDER_POLLSTERS = {
    "example",
    "example poll",
    "unknown",
    "unknown pollster",
    "n/a",
    "none",
    "poll",
}
_ELECTION_RESULT_URL_MARKERS = (
    "electionresults.",
    "/election-results",
    "/elections/results",
    "/primary-election-results",
    "/results-",
    "/returns/",
)


def polling_semantic_problem(poll: Any, polling_note: Any = None) -> Optional[str]:
    """Return a publication-blocking reason when an entry is not an opinion poll."""
    if not isinstance(poll, dict):
        return "Polling entry is not an object."

    pollster = str(poll.get("pollster") or "").strip()
    if not pollster or pollster.casefold() in _PLACEHOLDER_POLLSTERS:
        return f"Pollster name {pollster!r} is missing or a placeholder."

    has_numeric_matchup = any(
        isinstance(matchup, dict) and bool(matchup.get("percentages")) for matchup in poll.get("matchups") or []
    )
    if not has_numeric_matchup:
        return None

    source_url = str(poll.get("source_url") or "").casefold()
    note = str(polling_note or "").casefold()
    if any(marker in source_url for marker in _ELECTION_RESULT_URL_MARKERS):
        return "Election returns or candidate vote totals cannot be stored as opinion polling."
    if "primary result" in note or "election result" in note:
        return "The polling note identifies this numeric entry as election results rather than an opinion poll."
    return None
