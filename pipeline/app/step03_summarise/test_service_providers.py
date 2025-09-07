"""
Test for LLM Summarization Engine with Provider Registry

This file contains tests for the refactored provider-based summarization system.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# TODO: Enable when async LLM support and dependencies are available (openai, anthropic, etc.)
pytest.skip("LLM summarization provider tests require async LLM support", allow_module_level=True)

from shared import ConfidenceLevel, ExtractedContent, Source, SourceType, Summary

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from pipeline.app.step03_summarise.llm_summarization_engine import LLMSummarizationEngine


class TestLLMSummarizationEngineProviders:
    """Test the new provider-based LLM summarization engine."""

    @pytest.fixture
    def sample_extracted_content(self):
        """Sample extracted content for testing."""
        return [
            ExtractedContent(
                source=Source(
                    url="https://example.com/candidate-page",
                    type=SourceType.WEBSITE,
                    title="Candidate Official Page",
                    last_accessed=datetime.utcnow(),
                ),
                text="John Smith supports comprehensive healthcare reform including expanding access to affordable care.",
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
                text="In a recent interview, Jane Doe outlined her economic policies focusing on job creation and infrastructure investment.",
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
        assert engine_with_no_keys is not None
        assert hasattr(engine_with_no_keys, "cheap_mode")
        assert engine_with_no_keys.cheap_mode is True

    def test_initialization_with_keys(self, engine_with_all_keys):
        """Test that engine properly initializes with API keys."""
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
            assert hasattr(engine, "cheap_mode")

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_generate_summaries_no_enabled_models(self, engine_with_no_keys, sample_extracted_content):
        """Test that generate_summaries returns empty structure when no models are enabled."""
        summaries = await engine_with_no_keys.generate_summaries("test-race-123", sample_extracted_content)

        # Check the new response format
        assert isinstance(summaries, dict)
        assert "race_id" in summaries
        assert "generated_at" in summaries
        assert "content_stats" in summaries
        assert "summaries" in summaries
        assert "triangulation" in summaries

        # Check that all summary types are empty when no models are enabled
        assert summaries["summaries"]["race"] == []
        assert summaries["summaries"]["candidates"] == []
        assert summaries["summaries"]["issues"] == []

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

    # Provider-based functional tests

    @pytest.mark.asyncio
    async def test_provider_registry_integration(self):
        """Test that the engine properly integrates with the provider registry."""
        from ..providers import TaskType, registry

        # Check that we can get models for summarization
        models = registry.get_enabled_models(TaskType.SUMMARIZE)
        assert isinstance(models, list)

        # Check that providers are registered
        providers = registry.list_providers()
        assert len(providers) > 0
        assert "openai" in providers
        assert "anthropic" in providers
        assert "xai" in providers

    @pytest.mark.asyncio
    async def test_triangulation_models_selection(self):
        """Test that triangulation models are properly selected."""
        from ..providers import TaskType, registry

        triangulation_models = registry.get_triangulation_models(TaskType.SUMMARIZE)
        assert isinstance(triangulation_models, list)

        # Each item should be a tuple of (provider, model_config)
        for provider, model_config in triangulation_models:
            assert hasattr(provider, "name")
            assert hasattr(model_config, "model_id")
            assert hasattr(model_config, "provider")

    @pytest.mark.asyncio
    async def test_provider_availability_check(self):
        """Test provider availability checking."""
        from ..providers import registry

        for provider_name in registry.list_providers():
            provider = registry.get_provider(provider_name)
            # is_available() should not raise an exception
            availability = provider.is_available()
            assert isinstance(availability, bool)

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_generate_summaries_provider_integration(self, engine_with_all_keys, sample_extracted_content):
        """Test that generate_summaries works with the provider system."""
        # This test verifies the integration works end-to-end
        result = await engine_with_all_keys.generate_summaries("test-race", sample_extracted_content)

        # Should return the expected structure
        assert isinstance(result, dict)
        assert "race_id" in result
        assert "generated_at" in result
        assert "content_stats" in result
        assert "summaries" in result
        assert "triangulation" in result

        # Each summary type should be a list
        assert isinstance(result["summaries"]["race"], list)
        assert isinstance(result["summaries"]["candidates"], list)
        assert isinstance(result["summaries"]["issues"], list)

    @pytest.mark.asyncio
    async def test_summary_output_structure(self, engine_with_openai_key, sample_extracted_content):
        """Test that summaries include confidence and source information."""
        # Mock the provider to return structured output
        from ..providers import SummaryOutput, registry

        mock_summary_output = SummaryOutput(
            content="Test summary content",
            confidence="high",
            sources=["https://example.com/source1"],
            model_provider="openai",
            model_id="gpt-4o-mini",
            reasoning="High confidence due to multiple sources",
        )

        # Mock provider generate_summary method
        with patch.object(registry.get_provider("openai"), "generate_summary", return_value=mock_summary_output):
            result = await engine_with_openai_key.generate_summaries("test-race", sample_extracted_content)

            # Check that summaries have the expected structure
            if result["summaries"]["race"]:
                summary = result["summaries"]["race"][0]
                assert hasattr(summary, "content")
                assert hasattr(summary, "confidence")
                assert hasattr(summary, "model")
                assert hasattr(summary, "source_ids")
                assert hasattr(summary, "created_at")

    def test_content_filtering_methods(self, engine_with_openai_key, sample_extracted_content):
        """Test content filtering helper methods."""
        # Test candidate extraction
        candidates = engine_with_openai_key.content_processor.extract_candidates_from_content(sample_extracted_content)
        assert isinstance(candidates, list)
        assert len(candidates) > 0

        # Test candidate filtering
        if candidates:
            filtered = engine_with_openai_key.content_processor.filter_content_for_candidate(
                sample_extracted_content, candidates[0]
            )
            assert isinstance(filtered, list)

        # Test issue filtering
        filtered_issue = engine_with_openai_key.content_processor.filter_content_for_issue(
            sample_extracted_content, "Healthcare"
        )
        assert isinstance(filtered_issue, list)

    @pytest.mark.asyncio
    async def test_cheap_mode_vs_premium_mode(self):
        """Test that cheap mode and premium mode use different model tiers."""
        from ..providers import ModelTier, TaskType, registry

        # Test premium mode - explicitly set cheap mode to false
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "SMARTERVOTE_CHEAP_MODE": "false"}):
            # Reset registry to pick up new environment
            registry._cheap_mode = False

            premium_models = registry.get_enabled_models(TaskType.SUMMARIZE)
            premium_available = [m for m in premium_models if m.tier == ModelTier.PREMIUM]

            # Should have premium models when not in cheap mode
            assert (
                len(premium_available) > 0
            ), f"Expected premium models but got: {[(m.model_id, m.tier.value) for m in premium_models]}"

        # Test cheap mode
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "SMARTERVOTE_CHEAP_MODE": "true"}):
            # Reset registry to pick up new environment
            registry._cheap_mode = True

            cheap_models = registry.get_enabled_models(TaskType.SUMMARIZE)
            mini_available = [m for m in cheap_models if m.tier == ModelTier.MINI]

            # Should have mini models in cheap mode
            assert (
                len(mini_available) > 0
            ), f"Expected mini models in cheap mode but got: {[(m.model_id, m.tier.value) for m in cheap_models]}"

    def test_prepare_content_for_summarization(self, engine_with_openai_key, sample_extracted_content):
        """Test content preparation for summarization."""
        prepared = engine_with_openai_key.content_processor.prepare_content_for_summarization(
            sample_extracted_content, "test-race-123"
        )

        assert isinstance(prepared, str)
        assert len(prepared) > 0
        assert "test-race-123" in prepared.lower() or any(
            item.text.lower() in prepared.lower() for item in sample_extracted_content
        )
