"""
Summarize & Arbitrate Services for SmarterVote Pipeline

This module provides a unified interface for AI-powered summarization and
consensus arbitration using multiple LLM providers.
"""

from .consensus_arbitration_engine import ConsensusArbitrationEngine
from .llm_summarization_engine import LLMSummarizationEngine

# Main service classes for backwards compatibility
SummarizeService = LLMSummarizationEngine
ArbitrationService = ConsensusArbitrationEngine

__all__ = [
    "SummarizeService",
    "LLMSummarizationEngine",
    "ArbitrationService",
    "ConsensusArbitrationEngine",
]
