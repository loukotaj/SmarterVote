"""The holdover tables exist twice — once in Python, once in TypeScript.

`shared/forecast_summary.py` computes chamber control for the API and the agent;
`web/src/lib/utils/holdovers.ts` computes it again for the forecast page. Both
start from the same seats-not-up-this-cycle data, so if a cycle rollover updates
one copy and not the other, the site and the API report different parties in
control of the Senate — with no error anywhere to say so.

These tests parse the TypeScript source and compare it to the Python tables.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.forecast_summary import ABBR_TO_STATE, GOVERNOR_HOLDOVERS, SENATE_HOLDOVERS

HOLDOVERS_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "utils" / "holdovers.ts"
FORECAST_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "utils" / "forecast.ts"


def _table_body(source: str, name: str) -> str:
    """The `{ ... }` body of a const declaration, without its type annotation."""
    match = re.search(rf"^(?:export )?const {re.escape(name)}\b", source, re.MULTILINE)
    assert match, f"no const named {name} in the TypeScript source"
    start = match.start()
    brace = source.index("{", source.index("=", start))
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unbalanced braces in {name}")


def _parse_state_entries(body: str) -> dict[str, list[str]]:
    """Map each `State: "Party"` or `State: ["Party", ...]` entry to its parties."""
    entries: dict[str, list[str]] = {}
    for match in re.finditer(r'(?:"([^"]+)"|([A-Za-z]\w*))\s*:\s*(\[[^\]]*\]|"[^"]+")', body):
        state = match.group(1) or match.group(2)
        parties = re.findall(r'"(Democratic|Republican)"', match.group(3))
        assert parties, f"{state} has no party in the TypeScript table"
        entries[state] = parties
    return entries


@pytest.fixture(scope="module")
def ts_source() -> str:
    assert HOLDOVERS_TS.exists(), f"missing {HOLDOVERS_TS}"
    return HOLDOVERS_TS.read_text(encoding="utf-8")


def test_the_parser_actually_found_the_tables(ts_source):
    """Guard the guard: a parse that silently returns {} would pass everything."""
    assert len(_parse_state_entries(_table_body(ts_source, "SENATE_HOLDOVERS"))) > 40
    assert len(_parse_state_entries(_table_body(ts_source, "GOVERNOR_HOLDOVERS"))) > 10


def test_senate_holdovers_match_python(ts_source):
    ts_table = _parse_state_entries(_table_body(ts_source, "SENATE_HOLDOVERS"))
    assert ts_table == {state: list(parties) for state, parties in SENATE_HOLDOVERS.items()}


def test_governor_holdovers_match_python(ts_source):
    ts_table = _parse_state_entries(_table_body(ts_source, "GOVERNOR_HOLDOVERS"))
    assert ts_table == {state: [party] for state, party in GOVERNOR_HOLDOVERS.items()}


def test_state_abbreviation_tables_match():
    """`race_state` resolves a race's state from the ID prefix on both sides.

    A state missing from either table drops that state out of the holdover and
    active-state math for whichever side is missing it.
    """
    body = _table_body(FORECAST_TS.read_text(encoding="utf-8"), "ABBR_TO_STATE")
    ts_table = dict(re.findall(r'(\w+)\s*:\s*"([^"]+)"', body))
    assert len(ts_table) == 50, f"TypeScript ABBR_TO_STATE has {len(ts_table)} states"
    assert ts_table == ABBR_TO_STATE
