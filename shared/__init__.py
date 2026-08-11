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

#: Version of this shared package. Keep in step with ``version`` in
#: ``shared/pyproject.toml`` — that file is what ``pip install -e shared/``
#: reads, and the two silently disagreed for a while (metadata said 0.2.0 while
#: this said 0.4.0, and a now-deleted ``setup.py`` said 0.3.0).
#:
#: Distinct from ``RaceJSON.schema_version``, which versions the on-disk race
#: document format and moves only with a data migration.
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
