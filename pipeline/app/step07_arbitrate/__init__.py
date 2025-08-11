"""
Arbitration Service for SmarterVote Pipeline

This module provides a unified interface for arbitrating between multiple LLM responses.
"""

from .consensus_arbitration_engine import ConsensusArbitrationEngine

# Main service class for backwards compatibility
ArbitrationService = ConsensusArbitrationEngine

__all__ = ["ArbitrationService", "ConsensusArbitrationEngine"]
