"""Live adjudicator judgments against evidence that really broke the regexes.

These cases are the ones prose-grading got wrong in production. They cost a few
cents to run and need a real ``OPENROUTER_API_KEY``, so they skip in CI (which
mocks network) and run locally when someone has a key.

They are not redundant with tests/test_roster_adjudicator.py, which mocks the
provider and covers wiring. Only these can catch a prompt regression — the first
draft of the COMPLETENESS question blocked Ballotpedia's standard full-field
sentence, reproducing the exact ne-house-02-2026 failure the adjudicator exists
to fix, and no mocked test could have noticed.

    PYTHONPATH=. python -m pytest tests/test_roster_adjudicator_live.py -v
"""

from __future__ import annotations

import asyncio
import os

import pytest

from pipeline_client.agent.roster_adjudicator import Claim, adjudicate

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="live adjudicator check needs a real OPENROUTER_API_KEY",
)


NJ_CERTIFIED_LIST = {
    "url": "https://www.nj.gov/state/elections/assets/pdf/2026-official-list-candidates-us-senate.pdf",
    "title": "Official List Candidates for US Senate For GENERAL ELECTION 11/03/2026",
    "evidence": (
        "Official List Candidates for US Senate For GENERAL ELECTION 11/03/2026. "
        "DEMOCRATIC: Andy Kim. REPUBLICAN: Curtis Bashaw. LIBERTARIAN: Joanne Kuniansky."
    ),
    "published_at": "2026-06-10",
}

BALLOTPEDIA_FULL_FIELD = {
    "url": "https://ballotpedia.org/Nebraska%27s_2nd_Congressional_District_election,_2026",
    "title": "Nebraska's 2nd Congressional District election, 2026",
    "evidence": (
        "General election candidates: Don Bacon (R) and Tony Vargas (D) are running in the "
        "general election for U.S. House Nebraska District 2 on November 3, 2026."
    ),
    "published_at": "2026-07-20",
}

NE_SPREADSHEET_ROW = {
    "url": "https://sos.nebraska.gov/sites/default/files/doc/2026-general-candidates.xlsx",
    "title": "2026 General Election Candidates — Nebraska Secretary of State",
    "evidence": "CONGRESSIONAL DISTRICTS | District 2 | Tony Vargas | Democratic | Omaha, NE | Filed 2026-02-17",
    "published_at": "2026-02-20",
}

AL_STATE_HOUSE = {
    "url": "https://www.legislature.state.al.us/house/district2",
    "title": "Alabama House of Representatives District 2",
    "evidence": "Napoleon Bracy represents District 2 in the Alabama House of Representatives.",
    "published_at": "2026-03-01",
}

BLOCKED_PAGE = {
    "url": "https://ballotpedia.org/Nebraska%27s_2nd_Congressional_District_election,_2026",
    "title": "403 Forbidden",
    "evidence": "Access denied. Please enable JavaScript to continue.",
    "published_at": "2026-07-20",
}

PRIOR_CYCLE_ARTICLE = {
    "url": "https://example.com/2022-race",
    "title": "Bacon wins re-election in Nebraska's 2nd District",
    "evidence": "Don Bacon defeated Tony Vargas in the 2022 election for Nebraska's 2nd Congressional District.",
    "published_at": "2022-11-09",
}

GA_DIFFERENT_OFFICE = {
    "url": "https://sos.ga.gov/candidates/2026",
    "title": "Georgia 2026 Qualified Candidates",
    "evidence": "Jane Roe qualified as a candidate for Georgia Secretary of State in the 2026 general election.",
    "published_at": "2026-03-10",
}

NE_CONTEST = "ne-house-02-2026 (U.S. House, Nebraska District 2, 2026)"

CASES = [
    # --- must be ACCEPTED: real evidence the regexes wrongly rejected ----------
    (
        "nj-certified-list-phrasing",
        Claim.COMPLETENESS,
        "Andy Kim",
        "nj-senate-2026 (U.S. Senate, New Jersey, 2026)",
        NJ_CERTIFIED_LIST,
        True,
    ),
    ("ballotpedia-full-field-sentence", Claim.COMPLETENESS, "Don Bacon", NE_CONTEST, BALLOTPEDIA_FULL_FIELD, True),
    ("ne-spreadsheet-district-row", Claim.MEMBERSHIP, "Tony Vargas", NE_CONTEST, NE_SPREADSHEET_ROW, True),
    (
        "genuine-wrong-contest",
        Claim.WRONG_CONTEST,
        "Jane Roe",
        "ga-governor-2026 (Governor, Georgia, 2026)",
        GA_DIFFERENT_OFFICE,
        True,
    ),
    # --- must be BLOCKED: the holes the regexes existed to close ---------------
    (
        "state-house-district-number-collision",
        Claim.MEMBERSHIP,
        "Napoleon Bracy",
        "al-house-02-2026 (U.S. House, Alabama District 2, 2026)",
        AL_STATE_HOUSE,
        False,
    ),
    ("blocked-page-as-omission-proof", Claim.OMISSION, "Don Bacon", NE_CONTEST, BLOCKED_PAGE, False),
    ("prior-cycle-as-current-membership", Claim.MEMBERSHIP, "Don Bacon", NE_CONTEST, PRIOR_CYCLE_ARTICLE, False),
    (
        "absence-of-evidence-as-withdrawal",
        Claim.WITHDRAWAL,
        "Jane Doe",
        "ga-senate-2026 (U.S. Senate, Georgia, 2026)",
        {"evidence": "Not found in credible sources; no evidence this person is a real candidate."},
        False,
    ),
]


@pytest.mark.parametrize("name,claim,subject,contest,source,expected", CASES, ids=[case[0] for case in CASES])
def test_live_adjudication(name, claim, subject, contest, source, expected):
    verdict = asyncio.run(adjudicate(claim=claim, subject=subject, contest=contest, source=source))
    assert not verdict.unavailable, f"{name}: adjudicator unavailable — {verdict.reason}"
    assert verdict.supports is expected, (
        f"{name}: expected {'accept' if expected else 'block'}, got "
        f"{'accept' if verdict.supports else 'block'} — {verdict.reason}"
    )
