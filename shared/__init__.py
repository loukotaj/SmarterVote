"""
SmarterVote shared schema package.
Contains Pydantic models used across pipeline and services.
"""

from .models import (
    RaceJSON,
    Candidate,
    IssueStance,
    CanonicalIssue,
    ConfidenceLevel,
    SourceType,
    ProcessingJob,
    ProcessingStatus,
    Source,
    TopDonor,
    LLMResponse,
    TriangulatedSummary,
    Summary,
    VectorDocument,
    ExtractedContent,
    ChromaChunk,
    FreshSearchQuery,
    RAGQuery,
    ArbitrationResult,
)

__version__ = "0.2.0"
__all__ = [
    "RaceJSON",
    "Candidate",
    "IssueStance",
    "CanonicalIssue",
    "ConfidenceLevel",
    "SourceType",
    "ProcessingJob",
    "ProcessingStatus",
    "Source",
    "TopDonor",
    "LLMResponse",
    "TriangulatedSummary",
    "Summary",
    "VectorDocument",
    "ExtractedContent",
    "ChromaChunk",
    "FreshSearchQuery",
    "RAGQuery",
    "ArbitrationResult",
]
