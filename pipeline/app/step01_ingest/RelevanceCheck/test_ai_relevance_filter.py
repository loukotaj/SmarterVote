"""Tests for AIRelevanceFilter."""

import asyncio
from datetime import datetime

import pytest

from ...schema import ExtractedContent, Source, SourceType
from .ai_relevance_filter import AIRelevanceFilter


def test_filter_content_filters_irrelevant():
    filt = AIRelevanceFilter(threshold=0.5)
    doc1 = ExtractedContent(
        source=Source(url="https://a", type=SourceType.WEBSITE, last_accessed=datetime.utcnow()),
        text="The candidate discussed election policy yesterday",
        metadata={},
        extraction_timestamp=datetime.utcnow(),
        word_count=7,
    )
    doc2 = ExtractedContent(
        source=Source(url="https://b", type=SourceType.WEBSITE, last_accessed=datetime.utcnow()),
        text="Completely unrelated text",
        metadata={},
        extraction_timestamp=datetime.utcnow(),
        word_count=3,
    )
    out = asyncio.run(
        filt.filter_content(
            [doc1, doc2],
            "Test Election",
            ["Test Candidate", "Other"],
        )
    )
    assert doc1 in out
    assert doc2 not in out
    assert "relevance" in doc1.metadata
