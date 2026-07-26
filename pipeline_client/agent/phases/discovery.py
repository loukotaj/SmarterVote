"""Deterministic roster sanitization and Ballotpedia advisory sync.

These helpers run before and around the discovery/roster-sync model calls in
``fresh_run.py`` and ``update_run.py`` to keep the candidate roster sane
(dropping ineligible/withdrawn entries, capping size, reconciling against an
authoritative source) without relying on the model to police itself.
"""

import re
from typing import Any, Dict, List

from .. import roster
from ._common import _candidate_name

_TERM_LIMITED_NON_CANDIDATE_RE = re.compile(
    r"\b(term[- ]limited|cannot run|can't run|cannot seek|not seeking re-?election|"
    r"not running|ineligible|not eligible|from running again)\b",
    re.IGNORECASE,
)


def _normalize_candidate_entries(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop malformed candidate entries before phase fan-out touches them."""
    roster.normalize_candidate_entries(race_json, log)


def _candidate_roster_text(candidate: Dict[str, Any]) -> str:
    """Return searchable text from candidate fields used for roster sanity checks."""
    pieces: List[str] = []
    for field in ("name", "summary"):
        value = candidate.get(field)
        if isinstance(value, str):
            pieces.append(value)
    for source in candidate.get("summary_sources") or []:
        if isinstance(source, dict):
            title = source.get("title")
            if isinstance(title, str):
                pieces.append(title)
    return " ".join(pieces)


def _remove_ineligible_officeholders(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop current officeholders the discovery output says cannot run in this race."""
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return

    kept: List[Any] = []
    removed: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            kept.append(candidate)
            continue
        text = _candidate_roster_text(candidate)
        if candidate.get("incumbent") is True and _TERM_LIMITED_NON_CANDIDATE_RE.search(text):
            removed.append(str(candidate.get("name") or "unknown"))
            continue
        kept.append(candidate)

    if removed:
        race_json["candidates"] = kept
        if log:
            log(
                "warning",
                "Removed ineligible incumbent/non-candidate entries from discovery roster: " + ", ".join(removed),
            )


def _remove_inactive_candidates(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop candidates explicitly marked withdrawn by the roster tools.

    Do not infer inactive status from free-text summaries here. Roster repair
    agents sometimes mention historical primary losses or stale Ballotpedia
    snippets in candidate text; pruning on that text can delete valid current
    candidates. Exit decisions must go through ``remove_candidate`` guards.
    """
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return

    kept: List[Any] = []
    removed: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            kept.append(candidate)
            continue

        if candidate.get("withdrawn") is True:
            removed.append(str(candidate.get("name") or "unknown"))
            continue

        kept.append(candidate)

    if removed:
        race_json["candidates"] = kept
        if log:
            log("warning", "Removed inactive candidates from discovery roster: " + ", ".join(removed))


def _norm_name_for_match(name: str) -> str:
    return roster.normalize_name(name)


def _names_likely_same(left: str, right: str) -> bool:
    return roster.names_likely_same(left, right)


def _candidate_matches_any(name: str, roster: List[Dict[str, Any]]) -> bool:
    return any(_names_likely_same(name, str(candidate.get("name") or "")) for candidate in roster)


def _party_tag(party: Any) -> str:
    """Normalize a party value to a simple tag for balance checks."""
    return roster.party_tag(party)


def _reconcile_candidates_with_authoritative_roster(
    race_json: Dict[str, Any],
    authoritative_candidates: List[Dict[str, Any]],
    log: Any | None = None,
) -> None:
    """Remove stale candidates missing from Ballotpedia's current election roster.

    Candidates whose party is NOT represented in the authoritative roster at all are
    preserved — this prevents removing an incumbent of one party when Ballotpedia
    returned only the other party's primary page (a common pre-primary lookup pattern).
    """
    if not authoritative_candidates:
        return
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return

    # Collect the set of party tags present in the Ballotpedia roster.
    authoritative_party_tags: set = {_party_tag(c.get("party")) for c in authoritative_candidates if isinstance(c, dict)}

    kept: List[Any] = []
    removed: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            kept.append(candidate)
            continue
        name = _candidate_name(candidate)
        if not name or _candidate_matches_any(name, authoritative_candidates):
            kept.append(candidate)
            continue

        # If the candidate's party has NO representatives in the BP roster, the BP
        # page is likely a single-party primary page, not the full general election
        # roster.  Keep candidates of the missing party to avoid stripping the other
        # side of the ballot.
        tag = _party_tag(candidate.get("party"))
        if tag not in authoritative_party_tags:
            if log:
                log(
                    "debug",
                    f"  Kept {name} ({tag}) — party absent from BP roster (possible primary-only page)",
                )
            kept.append(candidate)
            continue

        removed.append(name)

    if removed:
        if not any(isinstance(candidate, dict) and _candidate_name(candidate) for candidate in kept):
            if log:
                log(
                    "warning",
                    "Skipped authoritative roster removal because it would leave the race with no candidates: "
                    + ", ".join(removed),
                )
            return
        race_json["candidates"] = kept
        if log:
            log(
                "warning",
                "Removed candidates absent from current Ballotpedia election roster: " + ", ".join(removed),
            )


def _add_candidates_from_authoritative_roster(
    race_json: Dict[str, Any],
    authoritative_candidates: List[Dict[str, Any]],
    log: Any | None = None,
) -> None:
    """Add missing candidates from an authoritative election roster."""
    if not authoritative_candidates:
        return
    candidates = race_json.setdefault("candidates", [])
    if not isinstance(candidates, list):
        race_json["candidates"] = []
        candidates = race_json["candidates"]

    added: List[str] = []
    current_candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
    for authoritative in authoritative_candidates:
        name = _candidate_name(authoritative)
        if not name or _candidate_matches_any(name, current_candidates):
            continue
        candidate = {
            "name": name,
            "party": authoritative.get("party") or "Unknown",
            "incumbent": bool(authoritative.get("incumbent")),
            "summary": "",
            "summary_sources": [],
            "image_url": authoritative.get("image_url"),
            "website": None,
            "social_media": {},
            "career_history": [],
            "education": [],
            "donor_summary": None,
            "donor_source_url": None,
            "donor_sources": [],
            "voting_summary": None,
            "voting_source_url": None,
            "voting_sources": [],
            "links": [],
            "issues": {},
        }
        candidates.append(candidate)
        current_candidates.append(candidate)
        added.append(name)

    if added and log:
        log("info", "Added candidates from current Ballotpedia election roster: " + ", ".join(added))


async def _sync_ballotpedia_roster(race_json: Dict[str, Any], race_id: str, log: Any | None = None) -> None:
    """Fetch Ballotpedia roster data as advisory evidence only.

    Election and district pages can contain stale primary tables or unrelated
    navigation tables.  The model-backed roster phase can inspect this result
    alongside official sources, but an unreviewed scrape must never add or
    remove candidates from an existing researched profile.

    Lazy import: ``_ballotpedia_election_lookup`` is imported from the
    ``phases`` package (not ``..ballotpedia`` directly) so tests that patch
    ``pipeline_client.agent.phases._ballotpedia_election_lookup`` still take
    effect regardless of which submodule this function lives in.
    """
    from . import _ballotpedia_election_lookup

    try:
        bp_result = await _ballotpedia_election_lookup(race_id)
    except Exception as exc:
        if log:
            log("debug", f"  Ballotpedia roster sync failed: {exc}")
        return

    if not isinstance(bp_result, dict) or not bp_result.get("found"):
        return
    bp_candidates = bp_result.get("candidates")
    if isinstance(bp_candidates, list) and log:
        names = [_candidate_name(candidate) for candidate in bp_candidates if _candidate_name(candidate)]
        if names:
            log("debug", f"  Ballotpedia roster lookup returned {len(names)} advisory candidate(s); no automatic edits")


def _backfill_source_timestamps(race_json: Dict[str, Any]) -> None:
    """Backfill missing last_accessed on legacy source objects loaded from checkpoints.

    Old data saved before the last_accessed field was made required will fail schema
    validation.  This sets a fallback ISO-8601 timestamp so validation passes.
    """
    roster.backfill_source_timestamps(race_json)


_ROSTER_CAP = roster.ROSTER_CAP


def _cap_roster(race_json: Dict[str, Any], log: Any | None = None, limit: int = _ROSTER_CAP) -> None:
    """Hard-cap the roster to *limit* candidates, balanced across major parties.

    The roster-sync prompt asks the model to keep the field tight, but the
    economy model and the Ballotpedia/search paths can still balloon a roster to
    dozens of entries. This deterministic trim keeps incumbents and the
    highest-signal major-party contenders (up to 4 Democratic + 4 Republican),
    filling any remaining slots with the next best candidates.
    """
    roster.cap_roster(race_json, log, limit)


def _remove_known_ineligible_candidates(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Drop candidates the model itself recorded as ineligible / not running.

    The discovery and roster-sync prompts populate
    ``pipeline_state.race_identity.known_ineligible_or_not_running`` with people
    who are term-limited, retiring, the state's off-cycle senator, or prior-cycle
    candidates. The economy model is decent at *listing* them there but often
    fails to *remove* them from ``candidates``; enforce the removal here.
    """
    state = race_json.get("pipeline_state")
    identity = state.get("race_identity") if isinstance(state, dict) else None
    if not isinstance(identity, dict):
        return
    banned = identity.get("known_ineligible_or_not_running")
    if not isinstance(banned, list) or not banned:
        return
    banned_norm = {str(name).strip().lower() for name in banned if isinstance(name, str) and str(name).strip()}
    if not banned_norm:
        return
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return
    kept: List[Dict[str, Any]] = []
    removed: List[str] = []
    for candidate in candidates:
        name = _candidate_name(candidate) if isinstance(candidate, dict) else ""
        if name and name.strip().lower() in banned_norm:
            removed.append(name)
        else:
            kept.append(candidate)
    if removed:
        race_json["candidates"] = kept
        if log:
            log("info", f"    Removed known-ineligible/not-running candidate(s): {', '.join(removed)}")


def _sanitize_roster(race_json: Dict[str, Any], log: Any | None = None) -> None:
    """Apply deterministic roster constraints before downstream fan-out."""
    _normalize_candidate_entries(race_json, log)
    _remove_ineligible_officeholders(race_json, log)
    _remove_inactive_candidates(race_json, log)
    _remove_known_ineligible_candidates(race_json, log)
    _cap_roster(race_json, log)
    race_json.pop("candidate_limit_note", None)
