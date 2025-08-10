"""Tests for the LLM Summarization Engine."""

import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

import sys
from pathlib import Path

# Add the pipeline root to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.summarise.llm_summarization_engine import LLMSummarizationEngine
from shared import (
    CanonicalIssue,
    ConfidenceLevel,
    ExtractedContent,
    Source,
    SourceType,
    Summary,
)


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
            return LLMSummarizationEngine()

    @pytest.fixture
    def engine_with_openai_key(self):
        """Create engine with OpenAI API key."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}):
            return LLMSummarizationEngine()

    @pytest.fixture
    def engine_with_all_keys(self):
        """Create engine with all API keys."""
        env_vars = {
            "OPENAI_API_KEY": "test-openai-key",
            "ANTHROPIC_API_KEY": "test-anthropic-key",
            "XAI_API_KEY": "test-xai-key",
        }
        with patch.dict(os.environ, env_vars):
            return LLMSummarizationEngine()

    def test_initialization_no_keys(self, engine_with_no_keys):
        """Test that engine initializes but warns when no API keys are provided."""
        assert all(not config["enabled"] for config in engine_with_no_keys.models.values())
        assert engine_with_no_keys.openai_api_key is None
        assert engine_with_no_keys.anthropic_api_key is None
        assert engine_with_no_keys.xai_api_key is None

    def test_initialization_with_keys(self, engine_with_all_keys):
        """Test that engine properly initializes with API keys."""
        assert engine_with_all_keys.openai_api_key == "test-openai-key"
        assert engine_with_all_keys.anthropic_api_key == "test-anthropic-key"
        assert engine_with_all_keys.xai_api_key == "test-xai-key"
        assert all(config["enabled"] for config in engine_with_all_keys.models.values())

    @pytest.mark.asyncio
    async def test_async_context_manager(self, engine_with_openai_key):
        """Test that engine works as async context manager."""
        async with engine_with_openai_key as engine:
            assert engine is not None
            assert hasattr(engine, "http_client")
        # After exiting context, client should be closed
        # (We can't easily test this without implementation details)

    @pytest.mark.asyncio
    async def test_generate_summaries_no_enabled_models(self, engine_with_no_keys, sample_extracted_content):
        """Test that generate_summaries returns empty list when no models are enabled."""
        summaries = await engine_with_no_keys.generate_summaries(
            "test-race-123", sample_extracted_content
        )
        assert summaries == []

    @pytest.mark.asyncio
    async def test_generate_summaries_empty_content(self, engine_with_openai_key):
        """Test that generate_summaries handles empty content gracefully."""
        summaries = await engine_with_openai_key.generate_summaries("test-race-123", [])
        assert summaries == []

    @pytest.mark.asyncio
    async def test_prepare_content_for_summarization(self, engine_with_openai_key, sample_extracted_content):
        """Test content preparation for summarization."""
        prepared = engine_with_openai_key._prepare_content_for_summarization(
            sample_extracted_content, "test-race-123"
        )
        
        assert "Candidate Official Page" in prepared
        assert "healthcare reform" in prepared
        assert "economic policies" in prepared
        assert "Source:" in prepared

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
        
        prepared = engine_with_openai_key._prepare_content_for_summarization(
            long_content, "test-race-123"
        )
        
        assert len(prepared) <= 15050  # Max content + truncation message
        assert "[Content truncated...]" in prepared

    @pytest.mark.asyncio
    async def test_openai_api_call_success(self, engine_with_openai_key):
        """Test successful OpenAI API call."""
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "This is a test summary from OpenAI."
                    }
                }
            ],
            "usage": {
                "total_tokens": 50
            }
        }
        
        with patch.object(engine_with_openai_key.http_client, 'post') as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.raise_for_status.return_value = None
            
            config = engine_with_openai_key.models["openai"]
            result = await engine_with_openai_key._call_openai_api(config, "Test prompt")
            
            assert result["content"] == "This is a test summary from OpenAI."
            assert result["tokens_used"] == 50

    @pytest.mark.asyncio
    async def test_openai_api_call_missing_key(self, engine_with_no_keys):
        """Test OpenAI API call with missing API key."""
        config = {"api_key": None}
        
        with pytest.raises(ValueError, match="OpenAI API key not configured"):
            await engine_with_no_keys._call_openai_api(config, "Test prompt")

    @pytest.mark.asyncio
    async def test_openai_api_call_rate_limit_retry(self, engine_with_openai_key):
        """Test OpenAI API call with rate limiting and retry logic."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.text = "Rate limit exceeded"
        
        success_response = MagicMock()
        success_response.json.return_value = {
            "choices": [{"message": {"content": "Success after retry"}}],
            "usage": {"total_tokens": 25}
        }
        success_response.raise_for_status.return_value = None
        
        with patch.object(engine_with_openai_key.http_client, 'post') as mock_post:
            # First call returns rate limit, second succeeds
            mock_post.side_effect = [
                httpx.HTTPStatusError("Rate limit", request=MagicMock(), response=rate_limit_response),
                success_response
            ]
            
            with patch('asyncio.sleep') as mock_sleep:  # Mock sleep to speed up test
                config = engine_with_openai_key.models["openai"]
                result = await engine_with_openai_key._call_openai_api(config, "Test prompt")
                
                assert result["content"] == "Success after retry"
                assert mock_sleep.called  # Verify sleep was called for retry

    @pytest.mark.asyncio
    async def test_anthropic_api_call_success(self, engine_with_all_keys):
        """Test successful Anthropic API call."""
        mock_response = {
            "content": [
                {
                    "text": "This is a test summary from Claude."
                }
            ],
            "usage": {
                "input_tokens": 20,
                "output_tokens": 30
            }
        }
        
        with patch.object(engine_with_all_keys.http_client, 'post') as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.raise_for_status.return_value = None
            
            config = engine_with_all_keys.models["anthropic"]
            result = await engine_with_all_keys._call_anthropic_api(config, "Test prompt")
            
            assert result["content"] == "This is a test summary from Claude."
            assert result["tokens_used"] == 50  # 20 + 30

    @pytest.mark.asyncio
    async def test_xai_api_call_success(self, engine_with_all_keys):
        """Test successful xAI API call."""
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "This is a test summary from Grok."
                    }
                }
            ],
            "usage": {
                "total_tokens": 40
            }
        }
        
        with patch.object(engine_with_all_keys.http_client, 'post') as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.raise_for_status.return_value = None
            
            config = engine_with_all_keys.models["xai"]
            result = await engine_with_all_keys._call_xai_api(config, "Test prompt")
            
            assert result["content"] == "This is a test summary from Grok."
            assert result["tokens_used"] == 40

    def test_assess_confidence_high(self, engine_with_openai_key):
        """Test confidence assessment for high-quality content."""
        high_quality_content = """
        According to verified documents and official campaign statements, the candidate has a comprehensive policy platform. 
        Based on evidence from multiple speeches and policy papers, they support healthcare reform with specific provisions for 
        expanding coverage. Research suggests their economic plan focuses on infrastructure investment confirmed by official 
        endorsements from major organizations.
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
        The candidate likely supports healthcare reform based on campaign statements. 
        Their economic policy generally indicates support for infrastructure spending,
        and they typically advocate for education funding increases. This suggests
        a progressive platform with expected focus on social programs.
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
            "tokens_used": 100
        }
        
        with patch.object(engine_with_openai_key, '_call_openai_api', return_value=mock_response):
            config = engine_with_openai_key.models["openai"]
            prompt = "Test prompt for {race_id}: {content}"
            content = "Test content"
            
            summary = await engine_with_openai_key._generate_single_summary(
                "openai", config, prompt, content, "test-race-123"
            )
            
            assert isinstance(summary, Summary)
            assert summary.content == mock_response["content"]
            assert summary.model == "gpt-4o"
            assert summary.tokens_used == 100
            assert summary.confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW]
            assert "test-race-123" in summary.source_ids

    @pytest.mark.asyncio
    async def test_generate_single_summary_api_failure(self, engine_with_openai_key):
        """Test single summary generation with API failure."""
        with patch.object(engine_with_openai_key, '_call_openai_api', side_effect=Exception("API Error")):
            config = engine_with_openai_key.models["openai"]
            prompt = "Test prompt"
            content = "Test content"
            
            with pytest.raises(Exception, match="API Error"):
                await engine_with_openai_key._generate_single_summary(
                    "openai", config, prompt, content, "test-race-123"
                )

    @pytest.mark.asyncio
    async def test_full_generate_summaries_workflow(self, engine_with_openai_key, sample_extracted_content):
        """Test the complete workflow of generating summaries."""
        mock_openai_response = {
            "content": "OpenAI summary with comprehensive analysis based on verified sources.",
            "tokens_used": 150
        }
        
        with patch.object(engine_with_openai_key, '_call_openai_api', return_value=mock_openai_response):
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
        mock_openai_response = {
            "content": "OpenAI summary content",
            "tokens_used": 100
        }
        
        with patch.object(engine_with_all_keys, '_call_openai_api', return_value=mock_openai_response):
            with patch.object(engine_with_all_keys, '_call_anthropic_api', side_effect=Exception("Anthropic Error")):
                with patch.object(engine_with_all_keys, '_call_xai_api', side_effect=Exception("xAI Error")):
                    summaries = await engine_with_all_keys.generate_summaries(
                        "test-race-123", sample_extracted_content
                    )
                    
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