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

from shared.forecast_summary import ABBR_TO_STATE, GOVERNOR_HOLDOVERS, INCUMBENT_FALLBACKS, SENATE_HOLDOVERS

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


def _ts_abbr_to_state() -> dict[str, str]:
    body = _table_body(FORECAST_TS.read_text(encoding="utf-8"), "ABBR_TO_STATE")
    return dict(re.findall(r'(\w+)\s*:\s*"([^"]+)"', body))


def _all_state_tables() -> dict[str, dict[str, str]]:
    """The four independently-maintained abbreviation-to-name tables.

    `smartervote_mcp` deliberately imports nothing from `shared` — it is a
    standalone client that talks to the races-api over HTTP and ships its own
    requirements — so its copy cannot simply import the shared one. The same
    goes for the TypeScript bundle. Keeping four copies is the accepted cost;
    letting them disagree is not, which is what this checks.
    """
    from pipeline_client.agent.ballotpedia import _STATE_NAMES
    from smartervote_mcp.server import _US_STATES

    return {
        "shared.forecast_summary.ABBR_TO_STATE": {k.lower(): v for k, v in ABBR_TO_STATE.items()},
        "ballotpedia._STATE_NAMES": {k.lower(): v for k, v in _STATE_NAMES.items()},
        "smartervote_mcp.server._US_STATES": {k.lower(): v for k, v in _US_STATES.items()},
        "web/.../forecast.ts ABBR_TO_STATE": {k.lower(): v for k, v in _ts_abbr_to_state().items()},
    }


def test_state_abbreviation_tables_match():
    """`race_state` resolves a race's state from the ID prefix on both sides.

    A state missing from either table drops that state out of the holdover and
    active-state math for whichever side is missing it — Indiana was missing
    from the Python copy, so every Indiana race without an explicit `state`
    field resolved to None.
    """
    ts_table = _ts_abbr_to_state()
    assert len(ts_table) == 50, f"TypeScript ABBR_TO_STATE has {len(ts_table)} states"
    assert ts_table == ABBR_TO_STATE


def test_no_state_table_disagrees_with_another_about_a_name():
    """A differing spelling is worse than a missing entry: the lookup succeeds
    and returns a name that will not match the other side's."""
    tables = _all_state_tables()
    for abbr in set().union(*(set(table) for table in tables.values())):
        names = {name: owner for owner, table in tables.items() for key, name in table.items() if key == abbr}
        assert len(names) == 1, f"{abbr!r} is spelled differently across tables: {names}"


def test_every_state_table_covers_all_fifty_states():
    fifty = set(ABBR_TO_STATE)
    for owner, table in _all_state_tables().items():
        missing = fifty - set(table)
        assert not missing, f"{owner} is missing {sorted(missing)}"


def test_only_the_lookup_tables_carry_dc():
    """DC has no voting Senate or House seat, so it must never reach chamber
    control math — but it does have Ballotpedia pages and races in the catalog.
    The split is deliberate; this pins which side each table is on so a
    well-meaning "add the missing state" does not quietly add a 51st seat."""
    tables = _all_state_tables()
    assert "dc" in tables["ballotpedia._STATE_NAMES"]
    assert "dc" in tables["smartervote_mcp.server._US_STATES"]
    assert "dc" not in tables["shared.forecast_summary.ABBR_TO_STATE"]
    assert "dc" not in tables["web/.../forecast.ts ABBR_TO_STATE"]


def test_incumbent_fallbacks_match_python():
    """The last-resort party guess for an unforecasted race, maintained twice.

    Both sides fall back to this table when the candidate roster says nothing, so
    a state present on one side only makes the page and the API guess different
    parties for the same race.
    """
    body = _table_body(FORECAST_TS.read_text(encoding="utf-8"), "INCUMBENT_FALLBACKS")
    ts_table: dict[str, dict[str, str]] = {}
    for chamber_match in re.finditer(r"(\w+)\s*:\s*\{([^}]*)\}", body):
        chamber = chamber_match.group(1)
        ts_table[chamber] = {
            (state_match.group(1) or state_match.group(2)): state_match.group(3)
            for state_match in re.finditer(
                r'(?:"([^"]+)"|([A-Za-z]\w*))\s*:\s*"(Democratic|Republican)"',
                chamber_match.group(2),
            )
        }
    assert set(ts_table) == set(INCUMBENT_FALLBACKS), "chambers differ between the two tables"
    assert ts_table == {chamber: dict(states) for chamber, states in INCUMBENT_FALLBACKS.items()}
