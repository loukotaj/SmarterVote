"""Shared test fixtures for the SmarterVote test suite."""

import asyncio
import sys
from unittest.mock import AsyncMock, patch

import pytest

# On Windows, the default ProactorEventLoop can disrupt pytest-asyncio teardown.
# Use the SelectorEventLoop for consistent local and CI behavior.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def mock_wikipedia_image_lookup():
    """Prevent every candidate-image fast path from making real HTTP calls."""
    with (
        patch("pipeline_client.agent.images._lookup_wikipedia_image", new_callable=AsyncMock, return_value=None),
        patch("pipeline_client.agent.images._lookup_ballotpedia_image", new_callable=AsyncMock, return_value=None),
        patch("pipeline_client.agent.images._lookup_known_page_image", new_callable=AsyncMock, return_value=None),
        patch("pipeline_client.agent.images._lookup_serper_image", new_callable=AsyncMock, return_value=None),
    ):
        yield


@pytest.fixture(autouse=True)
def mock_ballotpedia_election_lookup():
    """Prevent real HTTP calls to Ballotpedia during unit tests."""
    with patch(
        "pipeline_client.agent.phases._ballotpedia_election_lookup",
        new_callable=AsyncMock,
        return_value={"found": False, "candidates": [], "page_url": None, "description": None},
    ):
        yield


@pytest.fixture(autouse=True)
def stub_roster_adjudication(request):
    """Supply a permissive verdict when a test calls an editing handler directly.

    In production the agent loop resolves every roster judgment before dispatch
    and injects it under ``_adjudications``; a handler that finds none blocks,
    which is what makes the gate fail closed. Tests call the handlers directly,
    so without this they would all block.

    Stubbing here is deliberate rather than convenient. ``test_editing_tools``
    exercises the *structural* contract — URL shape, race_id match, tier grading,
    corroboration, roster caps. Whether a page's prose supports a claim is a
    separate concern covered by ``test_roster_adjudicator`` (mocked) and
    ``test_roster_adjudicator_live`` (real model, real cases). Making every
    structural test hand-write verdicts would have them assert two things at once
    and hide which one broke.

    A test carrying its own ``_adjudications`` still wins — the real lookup runs
    first, so a test can inject a blocking verdict to exercise a rejection path.
    Mark a test ``@pytest.mark.real_adjudication_gate`` to opt out entirely and
    see production's fail-closed behaviour; ``test_roster_adjudicator_gates``
    uses that to prove absence blocks.
    """
    if request.node.get_closest_marker("real_adjudication_gate"):
        yield
        return

    from pipeline_client.agent import handlers

    real_verdict_for = handlers._verdict_for

    def _permissive(args, claim, url=""):
        supplied = real_verdict_for(args, claim, url)
        if supplied is not None:
            return supplied
        return {"supports": True, "reason": "stubbed by test fixture", "model": "test-stub"}

    with patch.object(handlers, "_verdict_for", _permissive):
        yield
