"""Shared test fixtures for the SmarterVote test suite."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_wikipedia_image_lookup():
    """Prevent real HTTP calls to the Wikipedia API during unit tests.

    _lookup_wikipedia_image is called during image resolution for every
    candidate. Without this mock, tests that include candidates would make
    live network requests and could either fail (no connectivity) or
    unexpectedly resolve images, breaking assertions about image_url=None.
    """
    with patch(
        "pipeline_client.agent.images._lookup_wikipedia_image",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield
