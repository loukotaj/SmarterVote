"""Tests for the ExtractService."""

from datetime import datetime

import pytest

from ..schema import ExtractedContent, Source, SourceType
from . import ExtractService


class TestExtractService:
    """Tests for the ExtractService."""

    @pytest.fixture
    def extract_service(self):
        return ExtractService()

    @pytest.fixture
    def mock_raw_content(self):
        return [
            {
                "source": Source(
                    url="https://example.com/test",
                    type=SourceType.WEBSITE,
                    title="Test Site",
                    last_accessed=datetime.utcnow(),
                ),
                "content": """<html><body>
                    <h1>Test Title</h1>
                    <p>Test content paragraph with sufficient length to meet quality standards. This is a detailed article about a political candidate or issue that provides meaningful information for voters. The content includes multiple sentences and covers relevant topics that would be useful for political analysis and summarization.</p>
                    <p>This second paragraph ensures we have enough content to pass the minimum length requirements while maintaining realistic test data that reflects actual website content structure.</p>
                </body></html>""",
                "content_type": "text/html",
                "size_bytes": 500,
            }
        ]

    @pytest.mark.asyncio
    async def test_extract_all_returns_extracted_content(self, extract_service, mock_raw_content):
        """Test that extract_content returns ExtractedContent objects."""
        extracted = await extract_service.extract_content(mock_raw_content)

        assert isinstance(extracted, list)
        assert len(extracted) == 1
        assert isinstance(extracted[0], ExtractedContent)
        assert "Test Title" in extracted[0].text
        assert "sufficient length" in extracted[0].text
        assert extracted[0].word_count > 0
        assert "usefulness_ai" in extracted[0].metadata

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

        text, metadata = extract_service._extract_from_html(html_content)

        assert "alert" not in text
        assert "console.log" not in text
        assert "Title" in text
        assert "Content" in text
