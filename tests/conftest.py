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
