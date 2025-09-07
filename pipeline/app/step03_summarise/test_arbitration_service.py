"""Tests for the AI-driven ConsensusArbitrationEngine."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# TODO: Enable when full async LLM support is available (openai, anthropic, etc.)
pytest.skip("Consensus arbitration tests require full async LLM support", allow_module_level=True)

from pipeline.app.providers import ModelConfig, ModelTier, TaskType, registry
from pipeline.app.step03_summarise.consensus_arbitration_engine import ConsensusArbitrationEngine
from shared import ConfidenceLevel, Summary


class TestConsensusArbitrationEngine:
    """Tests for AI-driven arbitration consensus logic and bias detection."""

    @pytest.fixture
    def engine(self) -> ConsensusArbitrationEngine:
        engine = ConsensusArbitrationEngine(cheap_mode=True)
        return engine

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider for testing."""
        provider = AsyncMock()
        provider.name = "test_provider"
        provider.generate = AsyncMock()
        return provider

    @pytest.fixture
    def mock_model_config(self):
        """Create a mock model config for testing."""
        return ModelConfig(
            provider="test_provider", model_id="test-model", tier=ModelTier.MINI, tasks=[TaskType.ARBITRATE], enabled=True
        )

    def _make_summary(self, content: str, model: str = "gpt-4o") -> Summary:
        return Summary(
            content=content,
            model=model,
            confidence=ConfidenceLevel.HIGH,
            tokens_used=0,
            created_at=datetime.utcnow(),
            source_ids=[],
        )

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_arbitrate_summaries_ai_consensus(
        self, engine: ConsensusArbitrationEngine, mock_provider, mock_model_config
    ):
        """Test that AI-driven arbitration works with mocked responses."""

        consensus_text = "Candidate supports healthcare reform and economic growth."
        summaries = [
            self._make_summary(consensus_text),
            self._make_summary(consensus_text, model="claude-3.5"),
            self._make_summary(
                "Candidate focuses on education initiatives and environmental issues.",
                model="grok-3",
            ),
        ]

        # Structure summaries as the pipeline would
        all_summaries = {"race_summaries": summaries[:2], "candidate_summaries": [], "issue_summaries": [summaries[2]]}

        # Mock AI responses for bias detection, agreement analysis, and consensus generation
        mock_bias_response = json.dumps(
            {
                "bias_scores": [
                    {"summary_index": 0, "bias_level": "neutral", "severity": "low"},
                    {"summary_index": 1, "bias_level": "neutral", "severity": "low"},
                ]
            }
        )

        mock_agreement_response = json.dumps(
            {"consensus_groups": [[0, 1]], "agreement_strength": "high", "confidence_assessment": "high"}
        )

        mock_consensus_response = json.dumps(
            {
                "final_summary": "AI-generated consensus: Candidate supports healthcare reform and economic growth with some focus on education.",
                "confidence_level": "HIGH",
            }
        )

        # Mock the provider generate method to return these responses in sequence
        mock_provider.generate.side_effect = [
            mock_bias_response,
            mock_agreement_response,
            mock_consensus_response,
            # For issue summaries (single summary, no AI arbitration needed)
        ]

        # Mock the registry to return our mock provider and model
        with patch(
            "pipeline.app.step03_summarise.consensus_arbitration_engine.registry.get_triangulation_models"
        ) as mock_get_models:
            mock_get_models.return_value = [(mock_provider, mock_model_config)]

            result = await engine.arbitrate_summaries(all_summaries)

            # Check the result structure
            assert "consensus_data" in result
            assert "arbitrated_summaries" in result
            assert result["consensus_data"]["total_summaries_arbitrated"] == 3
            assert len(result["arbitrated_summaries"]) >= 1  # At least one category arbitrated

            # Check that race summaries were arbitrated
            race_arbitration = next((s for s in result["arbitrated_summaries"] if s["query_type"] == "race_summary"), None)
            assert race_arbitration is not None
            assert "AI-generated consensus" in race_arbitration["content"]
            assert race_arbitration["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_arbitrate_summaries_fallback_on_ai_failure(
        self, engine: ConsensusArbitrationEngine, mock_provider, mock_model_config
    ):
        """Test fallback behavior when AI calls fail."""

        summaries = [
            self._make_summary("Healthcare policies are a priority."),
            self._make_summary("Environmental protection is the main focus.", model="claude-3.5"),
        ]

        all_summaries = {"race_summaries": summaries, "candidate_summaries": [], "issue_summaries": []}

        # Mock AI call to raise an exception
        mock_provider.generate.side_effect = Exception("AI API failed")

        with patch(
            "pipeline.app.step03_summarise.consensus_arbitration_engine.registry.get_triangulation_models"
        ) as mock_get_models:
            mock_get_models.return_value = [(mock_provider, mock_model_config)]

            result = await engine.arbitrate_summaries(all_summaries)

            assert "consensus_data" in result
            assert "arbitrated_summaries" in result
            # Should have fallback arbitration for race summaries
            race_arbitration = next((s for s in result["arbitrated_summaries"] if s["query_type"] == "race_summary"), None)
            assert race_arbitration is not None
            assert race_arbitration["consensus_method"] == "ai_fallback"
            assert race_arbitration["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_bias_detection_affects_confidence(
        self, engine: ConsensusArbitrationEngine, mock_provider, mock_model_config
    ):
        """Test that detected bias affects final confidence level."""

        biased_text = "The radical liberal candidate pushes a biased agenda."
        summaries = [
            self._make_summary(biased_text),
            self._make_summary(biased_text + " More text for detail.", model="claude-3.5"),
        ]

        all_summaries = {"race_summaries": summaries, "candidate_summaries": [], "issue_summaries": []}

        # Mock AI responses showing high bias
        mock_bias_response = json.dumps(
            {
                "bias_scores": [
                    {"summary_index": 0, "bias_level": "left-leaning", "severity": "high", "examples": ["radical liberal"]},
                    {
                        "summary_index": 1,
                        "bias_level": "left-leaning",
                        "severity": "high",
                        "examples": ["radical liberal", "biased"],
                    },
                ]
            }
        )

        mock_agreement_response = json.dumps(
            {
                "consensus_groups": [[0, 1]],
                "agreement_strength": "high",
                "confidence_assessment": "medium",
            }
        )

        mock_consensus_response = json.dumps(
            {
                "final_summary": "Candidate has policy positions on various issues.",
                "confidence_level": "HIGH",  # Will be downgraded due to bias
            }
        )

        mock_provider.generate.side_effect = [
            mock_bias_response,
            mock_agreement_response,
            mock_consensus_response,
        ]

        with patch(
            "pipeline.app.step03_summarise.consensus_arbitration_engine.registry.get_triangulation_models"
        ) as mock_get_models:
            mock_get_models.return_value = [(mock_provider, mock_model_config)]

            result = await engine.arbitrate_summaries(all_summaries)

            # Confidence should be downgraded due to high bias
            race_arbitration = next((s for s in result["arbitrated_summaries"] if s["query_type"] == "race_summary"), None)
            assert race_arbitration is not None
            assert race_arbitration["confidence"] == "medium"
            assert "high bias" in race_arbitration["arbitration_notes"].lower()

    @pytest.mark.asyncio
    async def test_no_ai_models_available(self, engine: ConsensusArbitrationEngine):
        """Test behavior when no AI models are available for arbitration."""

        summaries = [
            self._make_summary("Healthcare policies are a priority."),
            self._make_summary("Environmental protection focus.", model="claude-3.5"),
        ]

        all_summaries = {"race_summaries": summaries, "candidate_summaries": [], "issue_summaries": []}

        # Mock registry to return no models
        with patch(
            "pipeline.app.step03_summarise.consensus_arbitration_engine.registry.get_triangulation_models"
        ) as mock_get_models:
            mock_get_models.return_value = []  # No models available

            result = await engine.arbitrate_summaries(all_summaries)

            assert "consensus_data" in result
            assert "arbitrated_summaries" in result
            race_arbitration = next((s for s in result["arbitrated_summaries"] if s["query_type"] == "race_summary"), None)
            assert race_arbitration is not None
            assert race_arbitration["consensus_method"] == "fallback_longest"
            assert race_arbitration["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_single_summary_handling(self, engine: ConsensusArbitrationEngine):
        """Test handling of single summary input per category."""

        summary = self._make_summary("Single summary content.")

        all_summaries = {"race_summaries": [summary], "candidate_summaries": [], "issue_summaries": []}

        result = await engine.arbitrate_summaries(all_summaries)

        assert "consensus_data" in result
        assert "arbitrated_summaries" in result
        race_arbitration = next((s for s in result["arbitrated_summaries"] if s["query_type"] == "race_summary"), None)
        assert race_arbitration is not None
        assert race_arbitration["content"] == summary.content
        assert race_arbitration["consensus_method"] == "single"

    @pytest.mark.asyncio
    async def test_empty_summaries_handling(self, engine: ConsensusArbitrationEngine):
        """Test handling of empty summaries."""

        all_summaries = {"race_summaries": [], "candidate_summaries": [], "issue_summaries": []}

        result = await engine.arbitrate_summaries(all_summaries)

        assert "consensus_data" in result
        assert "arbitrated_summaries" in result
        assert result["consensus_data"]["total_summaries_arbitrated"] == 0
        assert len(result["arbitrated_summaries"]) == 0
        assert result["consensus_data"]["arbitration_method"] == "error"

    @pytest.mark.asyncio
    async def test_ai_json_parsing_failure(self, engine: ConsensusArbitrationEngine, mock_provider, mock_model_config):
        """Test handling of invalid JSON responses from AI."""

        summaries = [
            self._make_summary("Content 1"),
            self._make_summary("Content 2", model="claude-3.5"),
        ]

        all_summaries = {"race_summaries": summaries, "candidate_summaries": [], "issue_summaries": []}

        # Mock AI call to return invalid JSON
        mock_provider.generate.return_value = "Invalid JSON response"

        with patch(
            "pipeline.app.step03_summarise.consensus_arbitration_engine.registry.get_triangulation_models"
        ) as mock_get_models:
            mock_get_models.return_value = [(mock_provider, mock_model_config)]

            result = await engine.arbitrate_summaries(all_summaries)

            # Should fall back due to JSON parsing failure
            assert "consensus_data" in result
            assert "arbitrated_summaries" in result
            race_arbitration = next((s for s in result["arbitrated_summaries"] if s["query_type"] == "race_summary"), None)
            assert race_arbitration is not None
            assert race_arbitration["consensus_method"] == "ai_fallback"
            assert race_arbitration["confidence"] == "low"
