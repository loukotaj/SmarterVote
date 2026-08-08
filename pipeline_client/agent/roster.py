"""Deterministic candidate-roster normalization and selection rules."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List

ROSTER_CAP = 8


def candidate_name(candidate: Any) -> str:
    if not isinstance(candidate, dict):
        return ""
    return str(candidate.get("name") or "").strip()


def normalize_candidate_entries(race_json: Dict[str, Any], log: Any | None = None) -> None:
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list):
        return
    kept: List[Dict[str, Any]] = []
    dropped = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            dropped += 1
            continue
        name = candidate_name(candidate)
        if not name:
            dropped += 1
            continue
        candidate["name"] = name
        # A blank string is not a valid URL. One stored in website/image_url fails
        # RaceJSON validation for the whole race, so a single cleared field blocks
        # publication of an otherwise complete profile. Clearing means null.
        for url_field in ("website", "image_url", "voting_source_url", "donor_source_url"):
            value = candidate.get(url_field)
            if isinstance(value, str) and not value.strip():
                candidate[url_field] = None
        kept.append(candidate)
    if dropped:
        race_json["candidates"] = kept
        if log:
            suffix = "y" if dropped == 1 else "ies"
            log("warning", f"Dropped {dropped} malformed candidate entr{suffix} before processing")


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def names_likely_same(left: str, right: str) -> bool:
    left_norm = normalize_name(left)
    right_norm = normalize_name(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    left_parts = left_norm.split()
    right_parts = right_norm.split()
    if len(left_parts) < 2 or len(right_parts) < 2 or left_parts[-1] != right_parts[-1]:
        return False
    return left_parts[0].startswith(right_parts[0]) or right_parts[0].startswith(left_parts[0])


def party_tag(party: Any) -> str:
    value = str(party or "").lower()
    if "democrat" in value or value in ("d", "dfl"):
        return "dem"
    if "republican" in value or value in ("r", "gop"):
        return "rep"
    return "other"


def backfill_source_timestamps(race_json: Dict[str, Any], *, now: datetime | None = None) -> None:
    fallback = (now or datetime.now(timezone.utc)).isoformat()
    for candidate in race_json.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        for key in ("summary_sources", "donor_sources", "voting_sources"):
            for source in candidate.get(key) or []:
                if isinstance(source, dict) and not source.get("last_accessed"):
                    source["last_accessed"] = fallback
        for issue_data in (candidate.get("issues") or {}).values():
            if not isinstance(issue_data, dict):
                continue
            for source in issue_data.get("sources") or []:
                if isinstance(source, dict) and not source.get("last_accessed"):
                    source["last_accessed"] = fallback


#: Contests where the leading candidates advance regardless of party, so
#: reserving roster slots per major party misdescribes the race.
PARTY_AGNOSTIC_CONTEST_STAGES = frozenset({"top_two", "top_four_rcv"})


def _party_balance_applies(race_json: Dict[str, Any]) -> bool:
    stage = str(race_json.get("contest_stage") or "").strip().lower()
    return stage not in PARTY_AGNOSTIC_CONTEST_STAGES


def cap_roster(race_json: Dict[str, Any], log: Any | None = None, limit: int = ROSTER_CAP) -> None:
    candidates = race_json.get("candidates")
    if not isinstance(candidates, list) or len(candidates) <= limit:
        return

    def signal(candidate: Dict[str, Any]) -> int:
        return (
            (100 if candidate.get("incumbent") else 0)
            + (10 if str(candidate.get("summary") or "").strip() else 0)
            + (5 if candidate.get("roster_sources") else 0)
            + (1 if candidate.get("image_url") else 0)
        )

    def party_group(candidate: Dict[str, Any]) -> str:
        tag = party_tag(candidate.get("party"))
        return "D" if tag == "dem" else "R" if tag == "rep" else "O"

    groups: Dict[str, List[int]] = {"D": [], "R": [], "O": []}
    for index, candidate in enumerate(candidates):
        if isinstance(candidate, dict):
            groups[party_group(candidate)].append(index)
    for indices in groups.values():
        indices.sort(key=lambda index: (-signal(candidates[index]), index))

    kept: set[int] = set()

    # An incumbent is never a casualty of balancing. The reserved slots below
    # are keyed on party, so an independent incumbent — Vermont's and Maine's
    # senators, a governor elected outside both parties — used to be dropped
    # before signal was consulted at all, despite incumbency outweighing every
    # other signal a hundred to one.
    kept.update(
        index for index, candidate in enumerate(candidates) if isinstance(candidate, dict) and candidate.get("incumbent")
    )

    if not _party_balance_applies(race_json):
        # Top-two and top-four contests advance the leading candidates whatever
        # their party, so reserving seats for the two major parties describes a
        # contest that is not being held. Alaska's top-four governor field —
        # twelve Republicans, two Democrats, three independents — filled the cap
        # with six Republicans and dropped every independent.
        ranked = sorted(range(len(candidates)), key=lambda index: (-signal(candidates[index]), index))
        for index in ranked:
            if len(kept) >= limit:
                break
            kept.add(index)
    else:
        for party in ("D", "R"):
            for index in groups[party][:4]:
                if len(kept) >= limit:
                    break
                kept.add(index)
        rest = groups["D"][4:] + groups["R"][4:] + groups["O"]
        rest.sort(key=lambda index: (-signal(candidates[index]), index))
        for index in rest:
            if len(kept) >= limit:
                break
            kept.add(index)

    kept_indices = sorted(kept)[:limit]
    kept_set = set(kept_indices)
    dropped = [candidate_name(candidates[index]) for index in range(len(candidates)) if index not in kept_set]
    race_json["candidates"] = [candidates[index] for index in kept_indices]
    if log:
        log(
            "info",
            f"    Capped roster {len(candidates)} -> {len(kept_indices)} candidates "
            f"(dropped: {', '.join(name for name in dropped[:12] if name)}).",
        )
