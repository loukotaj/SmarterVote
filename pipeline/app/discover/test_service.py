"""Tests for the DiscoveryService."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from ..schema import Source, SourceType
from . import DiscoveryService


class TestDiscoveryService:
    """Tests for the DiscoveryService."""

    @pytest.fixture
    def discovery_service(self):
        return DiscoveryService()

    @pytest.mark.asyncio
    async def test_discover_all_sources_returns_list(self, discovery_service):
        """Test that discover_all_sources returns a list of sources."""
        # Mock the underlying methods to avoid external dependencies
        discovery_service.discover_seed_sources = AsyncMock(
            return_value=[
                Source(
                    url="https://ballotpedia.org/test-race",
                    type=SourceType.WEBSITE,
                    title="Test Race - Ballotpedia",
                    last_accessed=datetime.utcnow(),
                )
            ]
        )
        discovery_service.discover_fresh_issue_sources = AsyncMock(
            return_value=[
                Source(
                    url="https://example.com/fresh-content",
                    type=SourceType.WEBSITE,
                    title="Fresh Test Content",
                    last_accessed=datetime.utcnow(),
                )
            ]
        )

        race_id = "test-race-123"
        sources = await discovery_service.discover_all_sources(race_id)

        assert isinstance(sources, list)
        assert len(sources) > 0
        assert all(isinstance(source, Source) for source in sources)
