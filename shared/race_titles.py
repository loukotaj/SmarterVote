"""Canonical public race-title formatting shared by pipeline outputs."""

from __future__ import annotations

import re
from typing import Any, Mapping

STATE_NAMES = {
    "al": "Alabama",
    "ak": "Alaska",
    "az": "Arizona",
    "ar": "Arkansas",
    "ca": "California",
    "co": "Colorado",
    "ct": "Connecticut",
    "de": "Delaware",
    "fl": "Florida",
    "ga": "Georgia",
    "hi": "Hawaii",
    "id": "Idaho",
    "il": "Illinois",
    "in": "Indiana",
    "ia": "Iowa",
    "ks": "Kansas",
    "ky": "Kentucky",
    "la": "Louisiana",
    "me": "Maine",
    "md": "Maryland",
    "ma": "Massachusetts",
    "mi": "Michigan",
    "mn": "Minnesota",
    "ms": "Mississippi",
    "mo": "Missouri",
    "mt": "Montana",
    "ne": "Nebraska",
    "nv": "Nevada",
    "nh": "New Hampshire",
    "nj": "New Jersey",
    "nm": "New Mexico",
    "ny": "New York",
    "nc": "North Carolina",
    "nd": "North Dakota",
    "oh": "Ohio",
    "ok": "Oklahoma",
    "or": "Oregon",
    "pa": "Pennsylvania",
    "ri": "Rhode Island",
    "sc": "South Carolina",
    "sd": "South Dakota",
    "tn": "Tennessee",
    "tx": "Texas",
    "ut": "Utah",
    "vt": "Vermont",
    "va": "Virginia",
    "wa": "Washington",
    "wv": "West Virginia",
    "wi": "Wisconsin",
    "wy": "Wyoming",
    "dc": "District of Columbia",
}


def _ordinal(value: str) -> str:
    number = int(value)
    if 10 < number % 100 < 14:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def canonical_race_title(race: Mapping[str, Any], race_id: str | None = None) -> str | None:
    """Return a deterministic public title, retaining unsupported-office titles."""
    identifier = str(race_id or race.get("id") or "")
    parts = identifier.lower().split("-")
    year = next((part for part in parts if len(part) == 4 and part.isdigit()), None)
    state = str(race.get("state") or STATE_NAMES.get(parts[0], "")).strip()
    office = str(race.get("office") or "").lower()
    special = " Special" if "special" in parts else ""
    if not (year and state):
        return race.get("title") or None
    if "senate" in office:
        return f"{year} {state} U.S. Senate{special} Election"
    if "house" in office or "representative" in office:
        district_label = f'{race.get("district") or ""} {race.get("jurisdiction") or ""}'
        labeled_district = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+(?:Congressional\s+)?District\b", district_label, re.I)
        if re.search(r"\bat[- ]large\b", district_label, re.I) or {"at", "large"}.issubset(parts):
            district = "At-Large"
        elif labeled_district:
            district = _ordinal(labeled_district.group(1))
        else:
            numeric_district = next((part for part in parts if part != year and part.isdigit()), None)
            district = _ordinal(numeric_district) if numeric_district else "At-Large"
        return f"{year} {state}'s {district} Congressional District{special} Election"
    if "governor" in office or "gubernatorial" in office:
        if "lieutenant governor" in office:
            return f"{year} {state} Governor and Lieutenant Governor{special} Election"
        return f"{year} {state} Governor{special} Election"
    return race.get("title") or None


def apply_canonical_race_title(race: dict[str, Any], race_id: str | None = None) -> None:
    """Normalize the mutable race record in place when its office is supported."""
    title = canonical_race_title(race, race_id)
    if title:
        race["title"] = title
