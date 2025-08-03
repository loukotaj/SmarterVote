"""
Corpus Service for SmarterVote Pipeline

This module provides a unified interface for vector database operations.
"""

from .vector_database_manager import VectorDatabaseManager

# Main service class for backwards compatibility
CorpusService = VectorDatabaseManager

__all__ = ["CorpusService", "VectorDatabaseManager"]
