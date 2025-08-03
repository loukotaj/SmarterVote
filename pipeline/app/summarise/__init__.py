"""
Summarize Service for SmarterVote Pipeline

This module provides a unified interface for AI-powered summarization using multiple LLM providers.
"""

from .llm_summarization_engine import LLMSummarizationEngine

# Main service class for backwards compatibility
SummarizeService = LLMSummarizationEngine

__all__ = ["SummarizeService", "LLMSummarizationEngine"]
