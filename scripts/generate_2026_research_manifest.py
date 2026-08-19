"""Generate the protected 2026 research-coverage manifest.

The published summaries provide the reconciled race IDs and display metadata;
the schedule below is curated from the FEC/NCSL 2026 calendars. Generation is
deliberately offline and deterministic. Runtime code reads the committed result
and never expands coverage from Firestore.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "published" / "summaries.json"
OUTPUT = ROOT / "shared" / "data" / "research_manifest_2026.json"

NCSL_URL = "https://www.ncsl.org/elections-and-campaigns/2026-state-primary-election-dates"
FEC_URL = "https://www.fec.gov/resources/cms-content/documents/2026pdates.pdf"
SENATE_CLASS_III_URL = "https://www.senate.gov/senators/Class_III.htm"
UTAH_FILINGS_URL = "https://vote.utah.gov/2026-candidate-filings/"

EXCLUDED = {
    "nd-senate-2026": "North Dakota regular Senate seat is Class III",
    "vt-senate-2026": "Vermont regular Senate seat is Class III",
    "ut-governor-2026": "Utah has no regular 2026 governor election",
    "ut-senate-2026": "Utah regular Senate seat is Class III",
}

# Statewide/default primary and possible runoff dates. Alabama and Louisiana
# office-specific exceptions are applied below.
STATE_EVENTS: dict[str, tuple[str, str | None]] = {
    "Alabama": ("2026-05-19", "2026-06-16"),
    "Alaska": ("2026-08-18", None),
    "Arizona": ("2026-07-21", None),
    "Arkansas": ("2026-03-03", "2026-03-31"),
    "California": ("2026-06-02", None),
    "Colorado": ("2026-06-30", None),
    "Connecticut": ("2026-08-11", None),
    "Delaware": ("2026-09-15", None),
    "Florida": ("2026-08-18", None),
    "Georgia": ("2026-05-19", "2026-06-16"),
    "Hawaii": ("2026-08-08", None),
    "Idaho": ("2026-05-19", None),
    "Illinois": ("2026-03-17", None),
    "Indiana": ("2026-05-05", None),
    "Iowa": ("2026-06-02", None),
    "Kansas": ("2026-08-04", None),
    "Kentucky": ("2026-05-19", None),
    "Louisiana": ("2026-05-16", "2026-06-27"),
    "Maine": ("2026-06-09", None),
    "Maryland": ("2026-06-23", None),
    "Massachusetts": ("2026-09-01", None),
    "Michigan": ("2026-08-04", None),
    "Minnesota": ("2026-08-11", None),
    "Mississippi": ("2026-03-10", "2026-04-07"),
    "Missouri": ("2026-08-04", None),
    "Montana": ("2026-06-02", None),
    "Nebraska": ("2026-05-12", None),
    "Nevada": ("2026-06-09", None),
    "New Hampshire": ("2026-09-08", None),
    "New Jersey": ("2026-06-02", None),
    "New Mexico": ("2026-06-02", None),
    "New York": ("2026-06-23", None),
    "North Carolina": ("2026-03-03", "2026-05-12"),
    "North Dakota": ("2026-06-09", None),
    "Ohio": ("2026-05-05", None),
    "Oklahoma": ("2026-06-16", "2026-08-25"),
    "Oregon": ("2026-05-19", None),
    "Pennsylvania": ("2026-05-19", None),
    "Rhode Island": ("2026-09-09", None),
    "South Carolina": ("2026-06-09", "2026-06-23"),
    "South Dakota": ("2026-06-02", "2026-07-28"),
    "Tennessee": ("2026-08-06", None),
    "Texas": ("2026-03-03", "2026-05-26"),
    "Utah": ("2026-06-23", None),
    "Vermont": ("2026-08-11", None),
    "Virginia": ("2026-08-04", None),
    "Washington": ("2026-08-04", None),
    "West Virginia": ("2026-05-12", None),
    "Wisconsin": ("2026-08-11", None),
    "Wyoming": ("2026-08-18", None),
}

STATE_BY_ABBR = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


def _office_kind(summary: dict[str, Any]) -> str:
    race_id = str(summary.get("id") or "")
    office = str(summary.get("office") or "").casefold()
    if race_id == "ar-supreme-court-2026":
        return "state_supreme_court"
    if "governor" in office or "governor" in race_id:
        return "governor"
    if "senate" in office or "senate" in race_id:
        return "us_senate"
    if "house" in office or "house" in race_id:
        return "us_house"
    raise ValueError(f"Unsupported office for {race_id}: {summary.get('office')}")


def _event(summary: dict[str, Any], office_kind: str) -> tuple[str, str | None, str | None]:
    race_id = str(summary["id"])
    state = STATE_BY_ABBR.get(race_id[:2].upper(), "")
    if race_id == "ar-supreme-court-2026":
        return "nonpartisan_general", None, None
    try:
        primary_date, runoff_date = STATE_EVENTS[state]
    except KeyError as exc:
        raise ValueError(f"No 2026 event calendar entry for {race_id} ({state})") from exc
    if state == "Alabama" and office_kind == "us_house":
        district_match = re.search(r"house-(\d{2})", race_id)
        if district_match and district_match.group(1) in {"01", "02", "06", "07"}:
            return "regular_primary", "2026-08-11", None
    if state == "Louisiana" and office_kind == "us_house":
        return "open_primary", "2026-11-03", "2026-12-12"
    return "regular_primary", primary_date, runoff_date


def build_manifest() -> dict[str, Any]:
    summaries = json.loads(INPUT.read_text(encoding="utf-8"))
    entries = []
    for summary in summaries:
        race_id = str(summary.get("id") or "")
        if race_id in EXCLUDED:
            continue
        office_kind = _office_kind(summary)
        event_type, primary_date, runoff_date = _event(summary, office_kind)
        state = STATE_BY_ABBR.get(race_id[:2].upper())
        if not state:
            raise ValueError(f"No state mapping for {race_id}")
        election_date = (
            "2026-03-03" if race_id == "ar-supreme-court-2026" else str(summary.get("election_date") or "2026-11-03")
        )
        if state == "Louisiana" and office_kind == "us_house":
            election_date = "2026-12-12"
        entries.append(
            {
                "race_id": race_id,
                "state": state,
                "office": office_kind,
                "event_type": event_type,
                "primary_date": primary_date,
                "runoff_date": runoff_date,
                "general_election_date": election_date,
                "schedule_source_url": FEC_URL if office_kind in {"us_house", "us_senate"} else NCSL_URL,
            }
        )
    entries.sort(key=lambda row: row["race_id"])
    ids = [row["race_id"] for row in entries]
    if len(ids) != 507 or len(set(ids)) != len(ids):
        raise ValueError(f"Expected 507 unique races, found {len(ids)} rows / {len(set(ids))} unique")
    return {
        "schema_version": 1,
        "cycle": 2026,
        "coverage_count": len(entries),
        "sources": {
            "congressional_schedule": FEC_URL,
            "state_schedule": NCSL_URL,
            "senate_class_audit": SENATE_CLASS_III_URL,
            "utah_filings_audit": UTAH_FILINGS_URL,
        },
        "excluded_races": EXCLUDED,
        "races": entries,
    }


def main() -> None:
    manifest = build_manifest()
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Wrote {manifest['coverage_count']} races to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
