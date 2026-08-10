"""Run the recorded roster-evidence fixtures as tests.

The fixtures in scripts/fixtures/roster_evidence are payloads captured verbatim
from real worker runs, each recording a tool call an agent actually made and
whether it should be accepted. They exist so guard changes can be checked in
under a second locally, and they run here so a guard that regresses on an
already-fixed case fails in CI rather than in production.
"""

from __future__ import annotations

import json

import pytest

from scripts.replay_roster_evidence import FIXTURE_DIR, _run_case


def _all_cases():
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        for case in fixture["cases"]:
            yield pytest.param(case, id=f"{path.stem}-{case['name'].replace(' ', '_')[:48]}")


@pytest.mark.parametrize("case", list(_all_cases()))
def test_recorded_roster_evidence_case(case):
    accepted, detail = _run_case(case)
    expected = bool(case["expect_accepted"])
    assert accepted == expected, (
        f"{case['name']}: expected {'accept' if expected else 'block'}, got "
        f"{'accept' if accepted else 'block'} — {detail[:300]}"
    )


def test_fixtures_are_present():
    """A silently empty fixture directory would make this suite vacuous."""
    assert list(FIXTURE_DIR.glob("*.json")), "no roster evidence fixtures found"
