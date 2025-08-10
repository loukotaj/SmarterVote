"""Tests for the AI-driven ConsensusArbitrationEngine."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.app.arbitrate.consensus_arbitration_engine import ConsensusArbitrationEngine
from shared import ConfidenceLevel, Summary


class TestConsensusArbitrationEngine:
    """Tests for AI-driven arbitration consensus logic and bias detection."""

    @pytest.fixture
    def engine(self) -> ConsensusArbitrationEngine:
        engine = ConsensusArbitrationEngine(cheap_mode=True)
        # Mock the HTTP client to avoid real API calls
        engine.http_client = AsyncMock()
        engine.enabled_models = ["openai"]  # Mock having at least one model
        return engine

    def _make_summary(self, content: str, model: str = "gpt-4o") -> Summary:
        return Summary(
            content=content,
            model=model,
            confidence=ConfidenceLevel.HIGH,
            tokens_used=0,
            created_at=datetime.utcnow(),
            source_ids=[],
        )

    @pytest.mark.asyncio
    async def test_arbitrate_summaries_ai_consensus(self, engine: ConsensusArbitrationEngine):
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

        # Mock AI responses for bias detection, agreement analysis, and consensus generation
        mock_bias_response = {
            "bias_scores": [
                {"summary_index": 0, "bias_level": "neutral", "severity": "low"},
                {"summary_index": 1, "bias_level": "neutral", "severity": "low"},
                {"summary_index": 2, "bias_level": "neutral", "severity": "low"},
            ]
        }

        mock_agreement_response = {"consensus_groups": [[0, 1]], "agreement_strength": "high", "confidence_assessment": "high"}

        mock_consensus_response = {
            "final_summary": "AI-generated consensus: Candidate supports healthcare reform and economic growth with some focus on education.",
            "confidence_level": "HIGH",
        }

        # Mock the API calls to return these responses
        with patch.object(engine, "_call_random_ai_model") as mock_ai_call:
            mock_ai_call.side_effect = [
                {"content": json.dumps(mock_bias_response), "model": "gpt-4o"},
                {"content": json.dumps(mock_agreement_response), "model": "gpt-4o"},
                {"content": json.dumps(mock_consensus_response), "model": "gpt-4o"},
            ]

            result = await engine.arbitrate_summaries(summaries)

            assert result.consensus_method == "ai_2_of_3_consensus"
            assert result.confidence == ConfidenceLevel.HIGH
            assert "AI-generated consensus" in result.final_content
            assert "AI-driven arbitration" in result.arbitration_notes

    @pytest.mark.asyncio
    async def test_arbitrate_summaries_fallback_on_ai_failure(self, engine: ConsensusArbitrationEngine):
        """Test fallback behavior when AI calls fail."""

        summaries = [
            self._make_summary("Healthcare policies are a priority."),
            self._make_summary("Environmental protection is the main focus.", model="claude-3.5"),
        ]

        # Mock AI call to raise an exception
        with patch.object(engine, "_call_random_ai_model") as mock_ai_call:
            mock_ai_call.side_effect = Exception("AI API failed")

            result = await engine.arbitrate_summaries(summaries)

            assert result.consensus_method == "ai_fallback"  # Changed from "fallback_longest"
            assert result.confidence == ConfidenceLevel.LOW
            assert "AI consensus failed" in result.arbitration_notes

    @pytest.mark.asyncio
    async def test_bias_detection_affects_confidence(self, engine: ConsensusArbitrationEngine):
        """Test that detected bias affects final confidence level."""

        biased_text = "The radical liberal candidate pushes a biased agenda."
        summaries = [
            self._make_summary(biased_text),
            self._make_summary(biased_text + " More text for detail.", model="claude-3.5"),
        ]

        # Mock AI responses showing high bias
        mock_bias_response = {
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

        mock_agreement_response = {
            "consensus_groups": [[0, 1]],
            "agreement_strength": "high",
            "confidence_assessment": "medium",
        }

        mock_consensus_response = {
            "final_summary": "Candidate has policy positions on various issues.",
            "confidence_level": "HIGH",  # Will be downgraded due to bias
        }

        with patch.object(engine, "_call_random_ai_model") as mock_ai_call:
            mock_ai_call.side_effect = [
                {"content": json.dumps(mock_bias_response), "model": "gpt-4o"},
                {"content": json.dumps(mock_agreement_response), "model": "gpt-4o"},
                {"content": json.dumps(mock_consensus_response), "model": "gpt-4o"},
            ]

            result = await engine.arbitrate_summaries(summaries)

            # Confidence should be downgraded due to high bias
            assert result.confidence == ConfidenceLevel.MEDIUM
            assert "high bias" in result.arbitration_notes.lower()

    @pytest.mark.asyncio
    async def test_no_ai_models_available(self, engine: ConsensusArbitrationEngine):
        """Test behavior when no AI models are available for arbitration."""

        engine.enabled_models = []  # No models available

        summaries = [
            self._make_summary("Healthcare policies are a priority."),
            self._make_summary("Environmental protection focus.", model="claude-3.5"),
        ]

        result = await engine.arbitrate_summaries(summaries)

        assert result.consensus_method == "fallback_longest"
        assert result.confidence == ConfidenceLevel.LOW
        assert "Fallback arbitration used" in result.arbitration_notes

    @pytest.mark.asyncio
    async def test_single_summary_handling(self, engine: ConsensusArbitrationEngine):
        """Test handling of single summary input."""

        summary = self._make_summary("Single summary content.")
        summaries = [summary]

        result = await engine.arbitrate_summaries(summaries)

        assert result.consensus_method == "single"
        assert result.final_content == summary.content
        assert result.confidence == summary.confidence
        assert "Only one summary available" in result.arbitration_notes

    @pytest.mark.asyncio
    async def test_empty_summaries_handling(self, engine: ConsensusArbitrationEngine):
        """Test handling of empty summaries list."""

        summaries = []

        result = await engine.arbitrate_summaries(summaries)

        assert result.consensus_method == "error"
        assert result.final_content == ""
        assert result.confidence == ConfidenceLevel.LOW
        assert "No summaries to arbitrate" in result.arbitration_notes

    @pytest.mark.asyncio
    async def test_ai_json_parsing_failure(self, engine: ConsensusArbitrationEngine):
        """Test handling of invalid JSON responses from AI."""

        summaries = [
            self._make_summary("Content 1"),
            self._make_summary("Content 2", model="claude-3.5"),
        ]

        # Mock AI call to return invalid JSON
        with patch.object(engine, "_call_random_ai_model") as mock_ai_call:
            mock_ai_call.return_value = {"content": "Invalid JSON response", "model": "gpt-4o"}

            result = await engine.arbitrate_summaries(summaries)

            # Should fall back due to JSON parsing failure
            assert result.consensus_method == "ai_fallback"  # Changed from "fallback_longest"
            assert result.confidence == ConfidenceLevel.LOW
