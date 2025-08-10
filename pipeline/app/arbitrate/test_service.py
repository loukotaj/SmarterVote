"""Tests for the ConsensusArbitrationEngine."""

from datetime import datetime

import pytest

from pipeline.app.arbitrate.consensus_arbitration_engine import ConsensusArbitrationEngine
from shared import ConfidenceLevel, Summary


class TestConsensusArbitrationEngine:
    """Tests for arbitration consensus logic and bias detection."""

    @pytest.fixture
    def engine(self) -> ConsensusArbitrationEngine:
        return ConsensusArbitrationEngine()

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
    async def test_arbitrate_summaries_two_agree(self, engine: ConsensusArbitrationEngine):
        """Two similar summaries should form a consensus."""

        consensus_text = "Candidate supports healthcare reform and economic growth."
        summaries = [
            self._make_summary(consensus_text),
            self._make_summary(consensus_text, model="claude-3.5"),
            self._make_summary(
                "Candidate focuses on education initiatives and environmental issues.",
                model="grok-4",
            ),
        ]

        result = await engine.arbitrate_summaries(summaries)

        assert result.consensus_method == "2-of-3"
        assert result.confidence in {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM}
        assert len(result.llm_responses) == 2

    @pytest.mark.asyncio
    async def test_arbitrate_summaries_no_consensus(self, engine: ConsensusArbitrationEngine):
        """Completely different summaries should fall back to single model."""

        summaries = [
            self._make_summary("Healthcare policies are a priority."),
            self._make_summary("Environmental protection is the main focus.", model="claude-3.5"),
            self._make_summary("Education reform tops the agenda.", model="grok-4"),
        ]

        result = await engine.arbitrate_summaries(summaries)

        assert result.consensus_method == "fallback_best_model"
        assert result.confidence == ConfidenceLevel.LOW

    @pytest.mark.asyncio
    async def test_bias_detection_lowers_confidence(self, engine: ConsensusArbitrationEngine):
        """Biased language should reduce final confidence and be noted."""

        biased_text = "The radical liberal candidate pushes a biased agenda."
        summaries = [
            self._make_summary(biased_text),
            self._make_summary(biased_text + " More text for detail.", model="claude-3.5"),
            self._make_summary("Focuses on bipartisan economic policies.", model="grok-4"),
        ]

        result = await engine.arbitrate_summaries(summaries)

        assert result.confidence == ConfidenceLevel.LOW
        assert "bias" in result.arbitration_notes.lower()
