"""
Corpus Service for SmarterVote Pipeline

This module provides a unified interface for vector database operations.
"""

try:  # pragma: no cover - optional chromadb dependency
    from .election_vector_database_manager import ElectionVectorDatabaseManager
    from .vector_database_manager import VectorDatabaseManager

    # Main service class for backwards compatibility
    CorpusService = ElectionVectorDatabaseManager

    __all__ = ["CorpusService", "VectorDatabaseManager", "ElectionVectorDatabaseManager"]
except Exception:  # noqa: BLE001
    __all__: list[str] = []
