"""
Corpus Service for SmarterVote Pipeline

This module provides a unified interface for vector database operations.
"""

from .election_vector_database_manager import ElectionVectorDatabaseManager
from .vector_database_manager import VectorDatabaseManager

# Main service class for backwards compatibility
CorpusService = VectorDatabaseManager

__all__ = ["CorpusService", "VectorDatabaseManager", "ElectionVectorDatabaseManager"]
