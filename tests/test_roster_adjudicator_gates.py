"""Production behaviour of the roster gates: a missing verdict blocks.

The rest of the suite runs under conftest's permissive adjudication stub, so
structural tests can exercise URL shape, tier grading and corroboration without
hand-writing verdicts. These tests opt out of that stub with the
``real_adjudication_gate`` marker and assert what actually happens in production
when no verdict is present — which is the property that makes an unreachable
adjudicator fail closed rather than waving evidence through.
"""

from __future__ import annotations

import pytest

from pipeline_client.agent.agent import _make_editing_handlers

pytestmark = pytest.mark.real_adjudication_gate


def _official_source(race_id="ne-house-02-2026", url="https://sos.nebraska.gov/candidates"):
    return {
        "url": url,
        "type": "official",
        "title": "2026 General Election Candidates",
        "evidence": "CONGRESSIONAL DISTRICTS | District 2 | Tony Vargas | Democratic | Filed 2026-02-17",
        "published_at": "2026-02-20",
        "race_id": race_id,
        "evidence_tier": 1,
        "retrieval_status": "content",
    }


def test_add_candidate_blocks_without_a_verdict():
    """Structurally perfect evidence is still not enough on its own."""
    race_json = {"id": "ne-house-02-2026", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["add_candidate"]({"name": "Tony Vargas", "party": "Democratic", "roster_sources": [_official_source()]})

    assert "Blocked adding" in result
    assert race_json["candidates"] == []


def test_withdrawal_blocks_without_a_verdict():
    race_json = {"id": "ga-senate-2026", "candidates": [{"name": "Alice"}, {"name": "Bob"}]}
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["remove_candidate"]({"name": "Alice", "reason": "Withdrew from the race on June 2, 2026."})

    assert "blocked" in result.lower()
    assert race_json["candidates"][0].get("withdrawn") is not True


def test_unavailable_adjudicator_blocks_and_says_so():
    """The fail-closed path must reach the model as a readable reason, not a silent no."""
    race_json = {"id": "ne-house-02-2026", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda *_: None)
    source = _official_source()

    result = handlers["add_candidate"](
        {
            "name": "Tony Vargas",
            "party": "Democratic",
            "roster_sources": [source],
            "_adjudications": {
                "membership": {
                    source["url"]: {
                        "supports": False,
                        "reason": "evidence could not be adjudicated (RuntimeError); the roster gate fails closed",
                        "model": "gpt-5.6-luna",
                        "unavailable": True,
                    }
                }
            },
        }
    )

    assert "Blocked adding" in result
    assert "fails closed" in result
    assert race_json["candidates"] == []


def test_supporting_verdict_lets_a_structurally_valid_source_through():
    """The gate must not be unconditionally closed — that would be its own outage."""
    race_json = {"id": "ne-house-02-2026", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda *_: None)
    source = _official_source()

    result = handlers["add_candidate"](
        {
            "name": "Tony Vargas",
            "party": "Democratic",
            "roster_sources": [source],
            "_adjudications": {
                "membership": {
                    source["url"]: {
                        "supports": True,
                        "reason": "names Tony Vargas under Congressional District 2 for 2026",
                        "model": "gpt-5.6-luna",
                    }
                }
            },
        }
    )

    assert "Blocked" not in result
    assert [c["name"] for c in race_json["candidates"]] == ["Tony Vargas"]


def test_accepted_source_carries_its_verdict_into_the_profile():
    """A published draft must record why each source was accepted."""
    race_json = {"id": "ne-house-02-2026", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda *_: None)
    source = _official_source()
    handlers["add_candidate"](
        {
            "name": "Tony Vargas",
            "party": "Democratic",
            "roster_sources": [source],
            "_adjudications": {
                "membership": {
                    source["url"]: {"supports": True, "reason": "names the district and cycle", "model": "gpt-5.6-luna"}
                }
            },
        }
    )

    stored = race_json["candidates"][0].get("roster_sources") or []
    assert stored, "candidate was added with no roster_sources recorded"
    audit = stored[0].get("adjudication")
    assert audit and audit["reason"] == "names the district and cycle"
    assert audit["model"] == "gpt-5.6-luna"
