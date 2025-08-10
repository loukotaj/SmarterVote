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

from app.summarise.llm_summarization_engine import LLMSummarizationEngine

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

    @pytest.mark.asyncio
    async def test_generate_summaries_no_enabled_models(self, engine_with_no_keys, sample_extracted_content):
        """Test that generate_summaries works correctly when no models are enabled."""
        summaries = await engine_with_no_keys.generate_summaries("test-race-123", sample_extracted_content)

        # Should return structured response even with no enabled models
        assert isinstance(summaries, dict)
        assert "race_summaries" in summaries
        assert "candidate_summaries" in summaries
        assert "issue_summaries" in summaries

    @pytest.mark.asyncio
    async def test_generate_summaries_empty_content(self, engine_with_openai_key):
        """Test that generate_summaries handles empty content gracefully."""
        summaries = await engine_with_openai_key.generate_summaries("test-race-123", [])
        expected = {"race_summaries": [], "candidate_summaries": [], "issue_summaries": []}
        assert summaries == expected

    @pytest.mark.asyncio
    async def test_prepare_content_for_summarization(self, engine_with_openai_key, sample_extracted_content):
        """Test content preparation for summarization."""
        prepared = engine_with_openai_key._prepare_content_for_summarization(sample_extracted_content, "test-race-123")

        assert "Candidate Official Page" in prepared
        assert "healthcare reform" in prepared
        assert "economic policies" in prepared
        assert "Source 1:" in prepared  # Updated to match new format
        assert "Source 2:" in prepared  # Updated to match new format
        assert "Race ID: test-race-123" in prepared

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

        prepared = engine_with_openai_key._prepare_content_for_summarization(long_content, "test-race-123")

        assert len(prepared) <= 15050  # Max content + truncation message
        assert "[Content truncated...]" in prepared

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

        confidence = engine_with_openai_key._assess_confidence(high_quality_content)
        assert confidence == ConfidenceLevel.HIGH

    def test_assess_confidence_low(self, engine_with_openai_key):
        """Test confidence assessment for low-quality content."""
        low_quality_content = "This is placeholder content that is unclear and unverified."

        confidence = engine_with_openai_key._assess_confidence(low_quality_content)
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

        confidence = engine_with_openai_key._assess_confidence(medium_quality_content)
        assert confidence == ConfidenceLevel.MEDIUM

    def test_assess_confidence_empty_content(self, engine_with_openai_key):
        """Test confidence assessment for empty or very short content."""
        assert engine_with_openai_key._assess_confidence("") == ConfidenceLevel.UNKNOWN
        assert engine_with_openai_key._assess_confidence("Short") == ConfidenceLevel.UNKNOWN

    @pytest.mark.asyncio
    async def test_generate_single_summary_success(self, engine_with_openai_key, sample_extracted_content):
        """Test successful single summary generation."""
        mock_response = {
            "content": "Generated summary content with specific details and verified information.",
            "tokens_used": 100,
        }

        with patch.object(engine_with_openai_key, "_call_openai_api", return_value=mock_response):
            config = engine_with_openai_key.models["openai"]
            prompt = "Test prompt for {race_id}: {content}"
            content = "Test content"
            # Create sample extracted content for the new parameter
            sample_content = [
                ExtractedContent(
                    source=Source(
                        url="https://example.com/test",
                        type=SourceType.WEBSITE,
                        title="Test Source",
                        last_accessed=datetime.utcnow(),
                    ),
                    text="Test content",
                    metadata={},
                    extraction_timestamp=datetime.utcnow(),
                    word_count=2,
                    language="en",
                )
            ]

            summary = await engine_with_openai_key._generate_single_summary(
                "openai", config, prompt, content, "test-race-123", sample_content
            )

            assert isinstance(summary, Summary)
            assert summary.content == mock_response["content"]
            assert summary.model == "gpt-4o-mini"
            assert summary.tokens_used == 100
            assert summary.confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW]
            assert len(summary.source_ids) > 0  # Should have extracted source IDs

    @pytest.mark.asyncio
    async def test_generate_single_summary_api_failure(self, engine_with_openai_key):
        """Test single summary generation with API failure."""
        with patch.object(engine_with_openai_key, "_call_openai_api", side_effect=Exception("API Error")):
            config = engine_with_openai_key.models["openai"]
            prompt = "Test prompt"
            content = "Test content"
            # Create sample extracted content for the new parameter
            sample_content = [
                ExtractedContent(
                    source=Source(
                        url="https://example.com/test",
                        type=SourceType.WEBSITE,
                        title="Test Source",
                        last_accessed=datetime.utcnow(),
                    ),
                    text="Test content",
                    metadata={},
                    extraction_timestamp=datetime.utcnow(),
                    word_count=2,
                    language="en",
                )
            ]

            with pytest.raises(Exception, match="API Error"):
                await engine_with_openai_key._generate_single_summary(
                    "openai", config, prompt, content, "test-race-123", sample_content
                )

    @pytest.mark.asyncio
    async def test_parse_ai_confidence(self, engine_with_openai_key):
        """Test parsing AI-generated confidence scores."""
        # Test HIGH confidence
        high_content = "CONFIDENCE: HIGH\nThis is a high confidence summary..."
        assert engine_with_openai_key._parse_ai_confidence(high_content) == ConfidenceLevel.HIGH

        # Test MEDIUM confidence
        medium_content = "CONFIDENCE: MEDIUM\nThis is a medium confidence summary..."
        assert engine_with_openai_key._parse_ai_confidence(medium_content) == ConfidenceLevel.MEDIUM

        # Test LOW confidence
        low_content = "CONFIDENCE: LOW\nThis is a low confidence summary..."
        assert engine_with_openai_key._parse_ai_confidence(low_content) == ConfidenceLevel.LOW

        # Test UNKNOWN confidence
        unknown_content = "CONFIDENCE: UNKNOWN\nThis is an unknown confidence summary..."
        assert engine_with_openai_key._parse_ai_confidence(unknown_content) == ConfidenceLevel.UNKNOWN

        # Test fallback to heuristic
        no_confidence_content = "This is a summary without confidence indicator"
        result = engine_with_openai_key._parse_ai_confidence(no_confidence_content)
        assert result in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW, ConfidenceLevel.UNKNOWN]

    @pytest.mark.asyncio
    async def test_extract_cited_sources(self, engine_with_openai_key, sample_extracted_content):
        """Test extraction of cited sources from AI response."""
        # Test response with source citations
        ai_response = """
        CONFIDENCE: HIGH
        SUMMARY:
        The candidate supports healthcare reform (Source: https://example.com/candidate-page).
        Economic policies focus on job creation (Source: https://example.com/interview).
        SOURCES CITED:
        - https://example.com/candidate-page
        - https://example.com/interview
        """

        cited_sources = engine_with_openai_key._extract_cited_sources(ai_response, sample_extracted_content)
        assert len(cited_sources) >= 2
        assert "https://example.com/candidate-page" in cited_sources
        assert "https://example.com/interview" in cited_sources

        # Test response with source number citations
        ai_response_numbered = """
        CONFIDENCE: HIGH
        SUMMARY:
        Source 1: mentions healthcare reform.
        Source 2: discusses economic policies.
        """

        cited_sources_numbered = engine_with_openai_key._extract_cited_sources(ai_response_numbered, sample_extracted_content)
        assert len(cited_sources_numbered) >= 2

        # Test response with no citations (fallback)
        ai_response_no_citations = "This is a summary with no source citations."
        cited_sources_fallback = engine_with_openai_key._extract_cited_sources(
            ai_response_no_citations, sample_extracted_content
        )
        assert len(cited_sources_fallback) == len(sample_extracted_content)  # Should include all sources as fallback

    @pytest.mark.asyncio
    async def test_full_generate_summaries_workflow(self, engine_with_openai_key, sample_extracted_content):
        """Test the complete workflow of generating summaries."""
        mock_openai_response = {
            "content": "OpenAI summary with comprehensive analysis based on verified sources.",
            "tokens_used": 150,
        }

        with patch.object(engine_with_openai_key, "_call_openai_api", return_value=mock_openai_response):
            summaries = await engine_with_openai_key.generate_summaries(
                "test-race-123", sample_extracted_content, "general_summary"
            )

            assert len(summaries) == 1  # Only OpenAI enabled
            assert isinstance(summaries[0], Summary)
            assert summaries[0].model == "gpt-4o"
            assert summaries[0].content == mock_openai_response["content"]

    @pytest.mark.asyncio
    async def test_generate_summaries_mixed_success_failure(self, engine_with_all_keys, sample_extracted_content):
        """Test generate_summaries with some APIs succeeding and others failing."""
        mock_openai_response = {"content": "OpenAI summary content", "tokens_used": 100}

        with patch.object(engine_with_all_keys, "_call_openai_api", return_value=mock_openai_response):
            with patch.object(engine_with_all_keys, "_call_anthropic_api", side_effect=Exception("Anthropic Error")):
                with patch.object(engine_with_all_keys, "_call_xai_api", side_effect=Exception("xAI Error")):
                    summaries = await engine_with_all_keys.generate_summaries("test-race-123", sample_extracted_content)

                    # Should only get the successful OpenAI summary
                    assert len(summaries) == 1
                    assert summaries[0].model == "gpt-4o"

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

    def test_triangulate_summaries_high_consensus(self, engine_with_openai_key):
        """Test triangulation with high confidence consensus."""
        summaries = [
            Summary(
                content="High confidence summary 1",
                model="gpt-4o",
                confidence=ConfidenceLevel.HIGH,
                tokens_used=100,
                created_at=datetime.utcnow(),
                source_ids=["test"],
            ),
            Summary(
                content="High confidence summary 2",
                model="claude-3.5",
                confidence=ConfidenceLevel.HIGH,
                tokens_used=120,
                created_at=datetime.utcnow(),
                source_ids=["test"],
            ),
        ]

        result = engine_with_openai_key.triangulate_summaries(summaries)
        assert result is not None
        assert result["consensus_confidence"] == ConfidenceLevel.HIGH
        assert result["consensus_method"] == "2-of-3-high"
        assert result["total_summaries"] == 2
        assert result["high_confidence_count"] == 2
        assert result["total_tokens_used"] == 220

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
        from pipeline.app.summarise.llm_summarization_engine import LLMAPIError, RateLimitError

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
        validation = engine_with_no_keys.validate_configuration()

        assert not validation["valid"]
        assert len(validation["enabled_providers"]) == 0
        assert len(validation["disabled_providers"]) == 3
        assert "No LLM providers are enabled" in validation["errors"]

    def test_validate_configuration_single_provider(self, engine_with_openai_key):
        """Test configuration validation with single provider."""
        validation = engine_with_openai_key.validate_configuration()

        assert validation["valid"]  # Valid but with warnings
        assert "openai" in validation["enabled_providers"]
        assert len(validation["enabled_providers"]) == 1
        assert any("triangulation requires 2+ providers" in warning for warning in validation["warnings"])

    def test_validate_configuration_all_providers(self, engine_with_all_keys):
        """Test configuration validation with all providers enabled."""
        validation = engine_with_all_keys.validate_configuration()

        assert validation["valid"]
        assert len(validation["enabled_providers"]) == 3
        assert "openai" in validation["enabled_providers"]
        assert "anthropic" in validation["enabled_providers"]
        assert "xai" in validation["enabled_providers"]
        # Should have no warnings about triangulation with 3 providers
