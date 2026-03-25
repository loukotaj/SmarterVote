"""
SmarterVote shared schema package.
Contains Pydantic models used across pipeline and services.
"""

from .models import (
    AgentReview,
    Candidate,
    CanonicalIssue,
    CareerEntry,
    ConfidenceLevel,
    EducationEntry,
    IssueStance,
    RaceJSON,
    ReviewFlag,
    Source,
    SourceType,
    TopDonor,
    VotingRecord,
)

__version__ = "0.3.0"
__all__ = [
    "AgentReview",
    "Candidate",
    "CanonicalIssue",
    "CareerEntry",
    "ConfidenceLevel",
    "EducationEntry",
    "IssueStance",
    "RaceJSON",
    "ReviewFlag",
    "Source",
    "SourceType",
    "TopDonor",
    "VotingRecord",
]
