"""
Core Pydantic models for SmarterVote data structures.
RaceJSON v0.3 — Multi-phase AI Agent Design
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceType(str, Enum):
    """Types of data sources."""

    WEBSITE = "website"
    PDF = "pdf"
    API = "api"
    SOCIAL_MEDIA = "social_media"
    NEWS = "news"
    GOVERNMENT = "government"
    FRESH_SEARCH = "fresh_search"


class ConfidenceLevel(str, Enum):
    """Confidence levels for processed data."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class CanonicalIssue(str, Enum):
    """The 12 canonical issues for consistent comparison across races."""

    HEALTHCARE = "Healthcare"
    ECONOMY = "Economy"
    CLIMATE_ENERGY = "Climate/Energy"
    REPRODUCTIVE_RIGHTS = "Reproductive Rights"
    IMMIGRATION = "Immigration"
    GUNS_SAFETY = "Guns & Safety"
    FOREIGN_POLICY = "Foreign Policy"
    SOCIAL_JUSTICE = "Social Justice"
    EDUCATION = "Education"
    TECH_AI = "Tech & AI"
    ELECTION_REFORM = "Election Reform"
    LOCAL_ISSUES = "Local Issues"


# ---------------------------------------------------------------------------
# Source & Issue models
# ---------------------------------------------------------------------------


class Source(BaseModel):
    """Data source information."""

    url: HttpUrl
    type: SourceType
    title: Optional[str] = None
    description: Optional[str] = None
    last_accessed: datetime
    published_at: Optional[datetime] = None
    checksum: Optional[str] = None
    is_fresh: bool = False
    is_official_campaign: Optional[bool] = None


class IssueStance(BaseModel):
    """Candidate's stance on a canonical issue."""

    issue: CanonicalIssue
    stance: str
    confidence: ConfidenceLevel
    sources: List[Source] = Field(default_factory=list)


class TopDonor(BaseModel):
    """Top campaign donor information."""

    name: str
    amount: Optional[float] = None
    organization: Optional[str] = None
    source: Optional[Source] = None


# ---------------------------------------------------------------------------
# Career & record models (new in v0.3)
# ---------------------------------------------------------------------------


class CareerEntry(BaseModel):
    """A single entry in a candidate's career history."""

    title: str
    organization: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    description: Optional[str] = None
    source: Optional[Source] = None


class EducationEntry(BaseModel):
    """A single education credential."""

    institution: str
    degree: Optional[str] = None
    field: Optional[str] = None
    year: Optional[int] = None
    source: Optional[Source] = None


class VotingRecord(BaseModel):
    """A notable vote cast by the candidate."""

    bill_name: str
    bill_description: Optional[str] = None
    vote: Literal["yes", "no", "abstain", "absent"]
    date: Optional[str] = None
    source: Optional[Source] = None


# ---------------------------------------------------------------------------
# Multi-LLM review (new in v0.3)
# ---------------------------------------------------------------------------


class ReviewFlag(BaseModel):
    """A single flag raised by a review agent."""

    field: str
    concern: str
    suggestion: Optional[str] = None
    severity: Literal["info", "warning", "error"] = "warning"


class AgentReview(BaseModel):
    """Result from a secondary review agent (Claude / Gemini)."""

    model: str
    reviewed_at: datetime
    verdict: Literal["approved", "needs_revision", "flagged"]
    flags: List[ReviewFlag] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    """Candidate information for RaceJSON v0.3."""

    name: str
    party: Optional[str] = None
    incumbent: bool = False
    summary: str = ""
    summary_sources: List[Source] = Field(default_factory=list)
    image_url: Optional[str] = None

    # Policy positions
    issues: Dict[CanonicalIssue, IssueStance] = Field(default_factory=dict)

    # Background
    career_history: List[CareerEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    voting_record: List[VotingRecord] = Field(default_factory=list)

    # Financial
    top_donors: List[TopDonor] = Field(default_factory=list)

    # Web presence
    website: Optional[HttpUrl] = None
    social_media: Dict[str, HttpUrl] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


class PollMatchup(BaseModel):
    """A head-to-head matchup within a poll."""

    candidates: List[str] = Field(default_factory=list)
    percentages: List[float] = Field(default_factory=list)


class PollEntry(BaseModel):
    """A single opinion poll for a race."""

    pollster: str
    date: Optional[str] = None
    sample_size: Optional[int] = None
    matchups: List[PollMatchup] = Field(default_factory=list)
    source_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Race (top-level output)
# ---------------------------------------------------------------------------


class RaceJSON(BaseModel):
    """RaceJSON v0.3 — Final output format."""

    id: str = Field(..., description="Race slug like 'mo-senate-2024'")
    election_date: str = Field(..., description="Election date in YYYY-MM-DD or ISO format")
    candidates: List[Candidate]
    updated_utc: str = Field(..., description="Last updated timestamp in ISO format")
    generator: List[str] = Field(default_factory=list)

    # Metadata
    title: Optional[str] = None
    office: Optional[str] = None
    jurisdiction: Optional[str] = None
    description: Optional[str] = None

    # Polling data
    polling: List[PollEntry] = Field(default_factory=list)

    # Multi-LLM reviews
    reviews: List[AgentReview] = Field(default_factory=list)
