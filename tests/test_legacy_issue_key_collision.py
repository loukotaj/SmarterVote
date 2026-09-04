"""A legacy issue key colliding with its canonical name must not lose sources."""

import pytest

from shared.models import Candidate

SOURCED = {
    "issue": "Reproductive Rights",
    "stance": "Supports protecting reproductive rights and access to abortion care.",
    "confidence": "high",
    "sources": [{"url": "https://example.com/policy", "type": "website", "last_accessed": "2026-09-02T00:00:00Z"}],
}
UNSOURCED = {
    "issue": "Abortion & Reproductive Health",
    "stance": "Supports protecting reproductive rights and access to abortion care.",
    "confidence": "high",
    "sources": [],
}


def _candidate(issues):
    return Candidate.model_validate({"name": "Test Candidate", "party": "Democratic", "issues": issues})


@pytest.mark.parametrize(
    "issues",
    [
        {"Reproductive Rights": SOURCED, "Abortion & Reproductive Health": UNSOURCED},
        {"Abortion & Reproductive Health": UNSOURCED, "Reproductive Rights": SOURCED},
    ],
    ids=["legacy-first", "canonical-first"],
)
def test_collision_keeps_the_sourced_entry_whatever_the_order(issues):
    """Insertion order used to decide it, so the same data could keep 1 source or 0."""
    candidate = _candidate(issues)

    assert len(candidate.issues) == 1
    (stance,) = candidate.issues.values()
    assert len(stance.sources) == 1, "the sourced entry must win regardless of key order"


def test_a_real_stance_beats_an_empty_one():
    empty = {"issue": "Reproductive Rights", "stance": "", "confidence": "low", "sources": []}
    candidate = _candidate({"Reproductive Rights": empty, "Abortion & Reproductive Health": UNSOURCED})

    (stance,) = candidate.issues.values()
    assert stance.stance.startswith("Supports protecting")


def test_legacy_rename_still_happens_without_a_collision():
    candidate = _candidate(
        {
            "Guns & Safety": {
                "issue": "Guns & Safety",
                "stance": "Supports background checks.",
                "confidence": "medium",
                "sources": [],
            }
        }
    )

    assert [key.value for key in candidate.issues] == ["Firearms & Second Amendment"]
