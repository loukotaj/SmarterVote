"""Tests for the FetchService."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from ..schema import Source, SourceType
from . import FetchService


class TestFetchService:
    """Tests for the FetchService."""

    @pytest.fixture
    def fetch_service(self):
        return FetchService()

    @pytest.fixture
    def mock_sources(self):
        return [
            Source(
                url="https://example.com/test",
                type=SourceType.WEBSITE,
                title="Test Site",
                last_accessed=datetime.utcnow(),
            )
        ]

    @pytest.mark.asyncio
    async def test_fetch_all_returns_content(self, fetch_service, mock_sources):
        """Test that fetch_content returns content for valid sources."""
        # Mock the HTTP client
        fetch_service._fetch_single_source = AsyncMock(
            return_value={
                "source": mock_sources[0],
                "content": "<html><body>Test content</body></html>",
                "content_type": "text/html",
                "status_code": 200,
                "fetched_at": datetime.utcnow(),
                "size_bytes": 100,
            }
        )

        content = await fetch_service.fetch_content(mock_sources)

        assert isinstance(content, list)
        assert len(content) == 1
        assert "content" in content[0]
