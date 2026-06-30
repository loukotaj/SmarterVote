"""
SmarterVote shared schema package.
Contains Pydantic models used across pipeline and services.
"""

from .models import (
    LEGACY_ISSUE_NAMES,
    AgentReview,
    Candidate,
    CandidateLink,
    CandidateRosterSource,
    CanonicalIssue,
    CareerEntry,
    ConfidenceLevel,
    ContestStage,
    EducationEntry,
    IssueStance,
    RaceIdentityBrief,
    RaceJSON,
    ReviewFlag,
    RosterSourceType,
    RunAudit,
    Source,
    SourceType,
)

__version__ = "0.4.0"
__all__ = [
    "AgentReview",
    "Candidate",
    "CandidateLink",
    "CandidateRosterSource",
    "CanonicalIssue",
    "CareerEntry",
    "ConfidenceLevel",
    "ContestStage",
    "EducationEntry",
    "IssueStance",
    "LEGACY_ISSUE_NAMES",
    "RaceJSON",
    "RaceIdentityBrief",
    "ReviewFlag",
    "RosterSourceType",
    "RunAudit",
    "Source",
    "SourceType",
]
