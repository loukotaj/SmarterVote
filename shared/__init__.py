"""
SmarterVote shared schema package.
Contains Pydantic models used across pipeline and services.
"""

from .models import (
    AgentReview,
    Candidate,
    CandidateLink,
    CanonicalIssue,
    CareerEntry,
    ConfidenceLevel,
    EducationEntry,
    IssueStance,
    RaceJSON,
    ReviewFlag,
    Source,
    SourceType,
)

__version__ = "0.4.0"
__all__ = [
    "AgentReview",
    "Candidate",
    "CandidateLink",
    "CanonicalIssue",
    "CareerEntry",
    "ConfidenceLevel",
    "EducationEntry",
    "IssueStance",
    "RaceJSON",
    "ReviewFlag",
    "Source",
    "SourceType",
]
