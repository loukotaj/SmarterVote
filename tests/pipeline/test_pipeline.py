"""
Tests for the SmarterVote pipeline modules.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock

from pipeline.app.schema import Source, SourceType, ExtractedContent
from pipeline.app.discover import DiscoveryService
from pipeline.app.fetch import FetchService
from pipeline.app.extract import ExtractService


class TestDiscoveryService:
    """Tests for the DiscoveryService."""
    
    @pytest.fixture
    def discovery_service(self):
        return DiscoveryService()
    
    @pytest.mark.asyncio
    async def test_discover_sources_returns_list(self, discovery_service):
        """Test that discover_sources returns a list of sources."""
        race_id = "test-race-123"
        sources = await discovery_service.discover_sources(race_id)
        
        assert isinstance(sources, list)
        assert len(sources) > 0
        assert all(isinstance(source, Source) for source in sources)


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
                last_accessed=datetime.utcnow()
            )
        ]
    
    @pytest.mark.asyncio
    async def test_fetch_all_returns_content(self, fetch_service, mock_sources):
        """Test that fetch_all returns content for valid sources."""
        # Mock the HTTP client
        fetch_service._fetch_single_source = AsyncMock(return_value={
            "source": mock_sources[0],
            "content": "<html><body>Test content</body></html>",
            "content_type": "text/html",
            "status_code": 200,
            "fetched_at": datetime.utcnow(),
            "size_bytes": 100
        })
        
        content = await fetch_service.fetch_all(mock_sources)
        
        assert isinstance(content, list)
        assert len(content) == 1
        assert "content" in content[0]


class TestExtractService:
    """Tests for the ExtractService."""
    
    @pytest.fixture
    def extract_service(self):
        return ExtractService()
    
    @pytest.fixture
    def mock_raw_content(self):
        return [{
            "source": Source(
                url="https://example.com/test",
                type=SourceType.WEBSITE,
                title="Test Site",
                last_accessed=datetime.utcnow()
            ),
            "content": "<html><body><h1>Test Title</h1><p>Test content paragraph.</p></body></html>",
            "content_type": "text/html",
            "size_bytes": 100
        }]
    
    @pytest.mark.asyncio
    async def test_extract_all_returns_extracted_content(self, extract_service, mock_raw_content):
        """Test that extract_all returns ExtractedContent objects."""
        extracted = await extract_service.extract_all(mock_raw_content)
        
        assert isinstance(extracted, list)
        assert len(extracted) == 1
        assert isinstance(extracted[0], ExtractedContent)
        assert "Test Title" in extracted[0].text
        assert "Test content paragraph" in extracted[0].text
        assert extracted[0].word_count > 0
    
    def test_extract_from_html_removes_scripts(self, extract_service):
        """Test that HTML extraction removes script tags."""
        html_content = """
        <html>
            <head><script>alert('test');</script></head>
            <body>
                <h1>Title</h1>
                <p>Content</p>
                <script>console.log('test');</script>
            </body>
        </html>
        """
        
        text = extract_service._extract_from_html(html_content)
        
        assert "alert" not in text
        assert "console.log" not in text
        assert "Title" in text
        assert "Content" in text
