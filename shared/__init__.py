"""
SmarterVote shared schema package.
Contains Pydantic models used across pipeline and services.
"""

from .models import (
    ArbitrationResult,
    Candidate,
    CanonicalIssue,
    ChromaChunk,
    ConfidenceLevel,
    ExtractedContent,
    FreshSearchQuery,
    IssueStance,
    LLMResponse,
    ProcessingJob,
    ProcessingStatus,
    RaceJSON,
    RaceMetadata,
    RAGQuery,
    Source,
    SourceType,
    Summary,
    TopDonor,
    TriangulatedSummary,
    VectorDocument,
)

__version__ = "0.2.0"
__all__ = [
    "RaceJSON",
    "RaceMetadata",
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
