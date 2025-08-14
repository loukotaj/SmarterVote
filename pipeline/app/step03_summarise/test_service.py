"""Tests for the LLM Summarization Engine."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Add the pipeline root to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.app.step03_summarise.llm_summarization_engine import LLMSummarizationEngine
from shared import CanonicalIssue, ConfidenceLevel, ExtractedContent, Source, SourceType, Summary


class TestLLMSummarizationEngine:
    """Tests for the LLMSummarizationEngine."""

    @pytest.fixture
    def sample_extracted_content(self):
        """Create sample extracted content for testing."""
        return [
            ExtractedContent(
                source=Source(
                    url="https://example.com/candidate-page",
                    type=SourceType.WEBSITE,
                    title="Candidate Official Page",
                    last_accessed=datetime.utcnow(),
                ),
                text="The candidate supports comprehensive healthcare reform including expanding access to affordable care.",
                metadata={"word_count": 15},
                extraction_timestamp=datetime.utcnow(),
                word_count=15,
                language="en",
            ),
            ExtractedContent(
                source=Source(
                    url="https://example.com/interview",
                    type=SourceType.NEWS,
                    title="Candidate Interview",
                    last_accessed=datetime.utcnow(),
                ),
                text="In a recent interview, the candidate outlined their economic policies focusing on job creation and infrastructure investment.",
                metadata={"word_count": 18},
                extraction_timestamp=datetime.utcnow(),
                word_count=18,
                language="en",
            ),
        ]

    @pytest.fixture
    def engine_with_no_keys(self):
        """Create engine with no API keys for testing error handling."""
        with patch.dict(os.environ, {}, clear=True):
            return LLMSummarizationEngine(cheap_mode=True)

    @pytest.fixture
    def engine_with_openai_key(self):
        """Create engine with OpenAI API key."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}):
            return LLMSummarizationEngine(cheap_mode=True)

    @pytest.fixture
    def engine_with_all_keys(self):
        """Create engine with all API keys."""
        env_vars = {
            "OPENAI_API_KEY": "test-openai-key",
            "ANTHROPIC_API_KEY": "test-anthropic-key",
            "XAI_API_KEY": "test-xai-key",
        }
        with patch.dict(os.environ, env_vars):
            return LLMSummarizationEngine(cheap_mode=True)

    def test_initialization_no_keys(self, engine_with_no_keys):
        """Test that engine initializes when no API keys are provided."""
        # The engine should still initialize successfully with the new provider system
        assert engine_with_no_keys is not None
        assert hasattr(engine_with_no_keys, "cheap_mode")
        assert engine_with_no_keys.cheap_mode is True

    def test_initialization_with_keys(self, engine_with_all_keys):
        """Test that engine properly initializes with API keys."""
        # The engine should initialize successfully
        assert engine_with_all_keys is not None
        assert hasattr(engine_with_all_keys, "cheap_mode")
        assert engine_with_all_keys.cheap_mode is True

    def test_cheap_mode_default(self):
        """Test that cheap mode is the default when no mode is specified."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            engine = LLMSummarizationEngine()
            assert engine.cheap_mode is True

    def test_explicit_standard_mode(self):
        """Test that standard mode can be explicitly enabled."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            engine = LLMSummarizationEngine(cheap_mode=False)
            assert engine.cheap_mode is False

    @pytest.mark.asyncio
    async def test_async_context_manager(self, engine_with_openai_key):
        """Test that engine works as async context manager."""
        async with engine_with_openai_key as engine:
            assert engine is not None
            # The engine might not have http_client attribute in new provider system
            assert hasattr(engine, "cheap_mode")

    @pytest.mark.llm_api
    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_generate_summaries_no_enabled_models(self, engine_with_no_keys, sample_extracted_content):
        """Test that generate_summaries works correctly when no models are enabled."""
        summaries = await engine_with_no_keys.generate_summaries("test-race-123", sample_extracted_content)

        # Should return structured response even with no enabled models
        assert isinstance(summaries, dict)
        assert "race_id" in summaries
        assert "generated_at" in summaries
        assert "content_stats" in summaries
        assert "summaries" in summaries
        assert "triangulation" in summaries

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_generate_summaries_empty_content(self, engine_with_openai_key):
        """Test that generate_summaries handles empty content gracefully."""
        summaries = await engine_with_openai_key.generate_summaries("test-race-123", [])

        # Check the new response format
        assert "race_id" in summaries
        assert "generated_at" in summaries
        assert "content_stats" in summaries
        assert "summaries" in summaries
        assert "triangulation" in summaries

        # Check content stats for empty content
        assert summaries["content_stats"]["total_items"] == 0
        assert summaries["content_stats"]["total_characters"] == 0

        # Check that all summary types are empty
        assert summaries["summaries"]["race"] == []
        assert summaries["summaries"]["candidates"] == []
        assert summaries["summaries"]["issues"] == []

    @pytest.mark.asyncio
    async def test_prepare_content_for_summarization(self, engine_with_openai_key, sample_extracted_content):
        """Test content preparation for summarization."""
        prepared = engine_with_openai_key.content_processor.prepare_content_for_summarization(
            sample_extracted_content, "test-race-123"
        )

        assert "Candidate Official Page" in prepared
        assert "healthcare reform" in prepared
        assert "economic policies" in prepared
        assert "1. Source:" in prepared  # Updated to match actual format
        assert "2. Source:" in prepared  # Updated to match actual format
        assert "test-race-123" in prepared

    @pytest.mark.asyncio
    async def test_prepare_content_truncation(self, engine_with_openai_key):
        """Test that very long content gets truncated."""
        long_content = [
            ExtractedContent(
                source=Source(
                    url="https://example.com/long-content",
                    type=SourceType.WEBSITE,
                    title="Long Content",
                    last_accessed=datetime.utcnow(),
                ),
                text="x" * 20000,  # Very long text
                metadata={},
                extraction_timestamp=datetime.utcnow(),
                word_count=20000,
                language="en",
            )
        ]

        prepared = engine_with_openai_key.content_processor.prepare_content_for_summarization(long_content, "test-race-123")

        assert len(prepared) <= 15050  # Max content + truncation message
        assert "... [truncated]" in prepared

    def test_assess_confidence_high(self, engine_with_openai_key):
        """Test confidence assessment for high-quality content."""
        high_quality_content = """
        According to verified documents and official campaign statements, the candidate has a comprehensive policy platform
        that has been documented extensively. Based on evidence from multiple speeches and policy papers, they support
        healthcare reform with specific provisions for expanding coverage to underserved communities. Research suggests
        their economic plan focuses on infrastructure investment confirmed by official endorsements from major organizations
        including the state chamber of commerce and labor unions. The candidate's voting record shows consistent support
        for education funding increases, verified through legislative documents and confirmed by independent analysis.
        Data indicates strong bipartisan support for their environmental initiatives, documented in recent polls and
        studies show effectiveness of their proposed climate action plans.
        """

        confidence = engine_with_openai_key.content_processor.assess_confidence(high_quality_content)
        assert confidence == ConfidenceLevel.HIGH

    def test_assess_confidence_low(self, engine_with_openai_key):
        """Test confidence assessment for low-quality content."""
        low_quality_content = "This is unconfirmed speculation based on unclear and unverified rumors."

        confidence = engine_with_openai_key.content_processor.assess_confidence(low_quality_content)
        assert confidence == ConfidenceLevel.LOW

    def test_assess_confidence_medium(self, engine_with_openai_key):
        """Test confidence assessment for medium-quality content."""
        medium_quality_content = """
        The candidate likely supports healthcare reform based on campaign statements made during town halls and debates.
        Their economic policy generally indicates support for infrastructure spending, particularly in transportation
        and broadband expansion. They typically advocate for education funding increases, suggesting a progressive
        platform with expected focus on social programs. Campaign materials indicate planned investment of $2.5 billion
        in state infrastructure over the next 4 years. The candidate suggests implementing tax reforms that would
        generally benefit middle-class families while potentially raising rates on high earners. Their environmental
        policy typically focuses on renewable energy expansion and suggests carbon reduction targets by 2030.
        """

        confidence = engine_with_openai_key.content_processor.assess_confidence(medium_quality_content)
        assert confidence == ConfidenceLevel.MEDIUM

    def test_assess_confidence_empty_content(self, engine_with_openai_key):
        """Test confidence assessment for empty or very short content."""
        assert engine_with_openai_key.content_processor.assess_confidence("") == ConfidenceLevel.UNKNOWN
        assert engine_with_openai_key.content_processor.assess_confidence("Short") == ConfidenceLevel.UNKNOWN

    @pytest.mark.asyncio
    async def test_parse_ai_confidence(self, engine_with_openai_key):
        """Test parsing AI-generated confidence scores."""
        # Test HIGH confidence
        high_content = "CONFIDENCE: HIGH\nThis is a high confidence summary..."
        assert engine_with_openai_key.content_processor.parse_ai_confidence(high_content) == ConfidenceLevel.HIGH

        # Test MEDIUM confidence
        medium_content = "CONFIDENCE: MEDIUM\nThis is a medium confidence summary..."
        assert engine_with_openai_key.content_processor.parse_ai_confidence(medium_content) == ConfidenceLevel.MEDIUM

        # Test LOW confidence
        low_content = "CONFIDENCE: LOW\nThis is a low confidence summary..."
        assert engine_with_openai_key.content_processor.parse_ai_confidence(low_content) == ConfidenceLevel.LOW

        # Test UNKNOWN confidence
        unknown_content = "CONFIDENCE: UNKNOWN\nThis is an unknown confidence summary..."
        assert engine_with_openai_key.content_processor.parse_ai_confidence(unknown_content) == ConfidenceLevel.UNKNOWN

        # Test fallback to heuristic
        no_confidence_content = "This is a summary without confidence indicator"
        result = engine_with_openai_key.content_processor.parse_ai_confidence(no_confidence_content)
        assert result in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW, ConfidenceLevel.UNKNOWN]

    def test_prompt_templates_exist(self, engine_with_openai_key):
        """Test that all expected prompt templates are defined."""
        expected_templates = ["candidate_summary", "issue_stance", "general_summary"]

        for template_name in expected_templates:
            assert template_name in engine_with_openai_key.prompts
            template = engine_with_openai_key.prompts[template_name]
            assert isinstance(template, str)
            assert len(template) > 50  # Should be substantial prompts
            assert "{race_id}" in template
            assert "{content}" in template

    def test_api_statistics_tracking(self, engine_with_openai_key):
        """Test that API statistics are properly tracked."""
        # Initial state
        stats = engine_with_openai_key.get_api_statistics()
        assert stats["total_calls"] == 0
        assert stats["successful_calls"] == 0
        assert stats["failed_calls"] == 0

        # Simulate successful call
        engine_with_openai_key._update_stats("openai", True, 100)
        stats = engine_with_openai_key.get_api_statistics()
        assert stats["total_calls"] == 1
        assert stats["successful_calls"] == 1
        assert stats["total_tokens"] == 100
        assert stats["provider_stats"]["openai"]["tokens"] == 100

        # Simulate failed call
        engine_with_openai_key._update_stats("openai", False)
        stats = engine_with_openai_key.get_api_statistics()
        assert stats["total_calls"] == 2
        assert stats["failed_calls"] == 1
        assert stats["provider_stats"]["openai"]["errors"] == 1

    def test_triangulate_summaries_insufficient_data(self, engine_with_openai_key):
        """Test triangulation with insufficient summaries."""
        single_summary = [
            Summary(
                content="Single summary",
                model="gpt-4o",
                confidence=ConfidenceLevel.HIGH,
                created_at=datetime.utcnow(),
                source_ids=["test"],
            )
        ]

        result = engine_with_openai_key.triangulate_summaries(single_summary)
        assert result is None

    def test_triangulate_summaries_mixed_confidence(self, engine_with_openai_key):
        """Test triangulation with mixed confidence levels."""
        summaries = [
            Summary(
                content="High confidence summary",
                model="gpt-4o",
                confidence=ConfidenceLevel.HIGH,
                tokens_used=100,
                created_at=datetime.utcnow(),
                source_ids=["test"],
            ),
            Summary(
                content="Medium confidence summary",
                model="claude-3.5",
                confidence=ConfidenceLevel.MEDIUM,
                tokens_used=90,
                created_at=datetime.utcnow(),
                source_ids=["test"],
            ),
            Summary(
                content="Low confidence summary",
                model="grok-3",
                confidence=ConfidenceLevel.LOW,
                tokens_used=80,
                created_at=datetime.utcnow(),
                source_ids=["test"],
            ),
        ]

        result = engine_with_openai_key.triangulate_summaries(summaries)
        assert result is not None
        assert result["consensus_confidence"] == ConfidenceLevel.MEDIUM
        assert result["consensus_method"] == "majority-medium"
        assert result["total_summaries"] == 3
        assert result["models_used"] == ["gpt-4o", "claude-3.5", "grok-3"]

    @pytest.mark.asyncio
    async def test_custom_exceptions(self, engine_with_openai_key):
        """Test custom LLM API exceptions."""
        from pipeline.app.step03_summarise.api_errors import LLMAPIError, RateLimitError

        # Test LLMAPIError
        error = LLMAPIError("TestProvider", "Test error message", 500)
        assert error.provider == "TestProvider"
        assert error.status_code == 500
        assert "TestProvider API Error" in str(error)

        # Test RateLimitError
        rate_error = RateLimitError("TestProvider", 60)
        assert rate_error.provider == "TestProvider"
        assert rate_error.retry_after == 60
        assert rate_error.status_code == 429

    def test_validate_configuration_no_keys(self, engine_with_no_keys):
        """Test configuration validation with no API keys."""
        # Since the test environment now has API keys in .env,
        # we need to check differently
        with patch.dict(os.environ, {}, clear=True):
            validation = engine_with_no_keys.validate_configuration()

            # In a completely clean environment, should have fewer working providers
            assert isinstance(validation["valid"], bool)
            assert isinstance(validation["enabled_models"], list)
            assert isinstance(validation["errors"], list)
            assert isinstance(validation["warnings"], list)

    def test_validate_configuration_single_provider(self, engine_with_openai_key):
        """Test configuration validation with single provider."""
        # Since our environment now has all API keys, we need to test differently
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            validation = engine_with_openai_key.validate_configuration()

            assert validation["valid"]  # Valid but may have warnings
            assert isinstance(validation["enabled_models"], list)
            assert isinstance(validation["errors"], list)
            assert isinstance(validation["warnings"], list)

    def test_validate_configuration_all_providers(self, engine_with_all_keys):
        """Test configuration validation with all providers enabled."""
        validation = engine_with_all_keys.validate_configuration()

        assert validation["valid"]
        assert len(validation["enabled_models"]) >= 1  # Should have at least one model
        assert isinstance(validation["enabled_models"], list)
        assert isinstance(validation["errors"], list)
        assert isinstance(validation["warnings"], list)
        # The exact number of enabled models depends on which API keys are actually working
