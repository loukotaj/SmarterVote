"""
Core Pydantic models for SmarterVote data structures.
RaceJSON v0.3 — Multi-phase AI Agent Design
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceType(str, Enum):
    """Types of data sources."""

    WEBSITE = "website"
    FINANCE = "finance"
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
    """The canonical issues for consistent comparison across races."""

    HEALTHCARE = "Healthcare"
    ECONOMY = "Economy"
    CLIMATE_ENERGY = "Climate/Energy"
    ABORTION_REPRODUCTIVE_HEALTH = "Abortion & Reproductive Health"
    IMMIGRATION = "Immigration"
    FIREARMS_SECOND_AMENDMENT = "Firearms & Second Amendment"
    FOREIGN_POLICY = "Foreign Policy"
    CIVIL_RIGHTS_EQUALITY = "Civil Rights & Equality"
    EDUCATION = "Education"
    TECH_AI = "Tech & AI"
    ELECTION_POLICY = "Election Policy"
    LOCAL_ISSUES = "Local Issues"


# Maps legacy (biased) issue names to their current neutral names.
# Used to migrate old published JSON files transparently.
LEGACY_ISSUE_NAMES: dict[str, str] = {
    "Reproductive Rights": "Abortion & Reproductive Health",
    "Guns & Safety": "Firearms & Second Amendment",
    "Social Justice": "Civil Rights & Equality",
    "Election Reform": "Election Policy",
}


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

    issue: Optional[CanonicalIssue] = None
    stance: str
    confidence: ConfidenceLevel
    sources: List[Source] = Field(default_factory=list)

    @field_validator("issue", mode="before")
    @classmethod
    def migrate_legacy_issue_field(cls, v: Any) -> Any:
        """Migrate legacy issue name in the issue field itself."""
        if isinstance(v, str):
            return LEGACY_ISSUE_NAMES.get(v, v)
        return v


class CandidateLink(BaseModel):
    """A notable reference link for a candidate (Ballotpedia, Wikipedia, finance, etc.)."""

    url: str
    title: str
    type: Literal[
        "finance", "ballotpedia", "wiki", "official", "legislature", "votesmart", "govtrack", "news", "other"
    ] = "other"


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
    score: Optional[int] = Field(None, ge=0, le=100, description="Quality score 0-100")
    flags: List[ReviewFlag] = Field(default_factory=list)
    summary: str = ""


class ValidationGrade(BaseModel):
    """Aggregate validation grade computed from multi-LLM reviews."""

    grade: Literal["A", "B", "C", "D", "F"]
    score: int = Field(..., ge=0, le=100, description="Average score across reviewers")
    passed: bool = Field(..., description="Whether the grade meets the quality threshold (B or above)")
    summary: str = Field("", description="Brief explanation of the grade")


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    """Candidate information for RaceJSON v0.3."""

    name: str = Field(..., min_length=1)
    party: Optional[str] = None
    incumbent: bool = False
    summary: str = ""
    summary_sources: List[Source] = Field(default_factory=list)
    image_url: Optional[str] = None

    # Policy positions
    issues: Dict[CanonicalIssue, IssueStance] = Field(default_factory=dict)

    @field_validator("issues", mode="before")
    @classmethod
    def migrate_legacy_issue_names(cls, v: Any) -> Any:
        """Transparently rename legacy (biased) issue keys to current neutral names."""
        if not isinstance(v, dict):
            return v
        return {LEGACY_ISSUE_NAMES.get(k, k): val for k, val in v.items()}

    # Background
    career_history: List[CareerEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)

    # Voting summary (narrative + link; raw record list removed in v0.4)
    voting_summary: Optional[str] = None
    voting_source_url: Optional[str] = None
    voting_sources: List[Source] = Field(default_factory=list)

    # Financial (narrative + link; raw donor list removed in v0.4)
    donor_summary: Optional[str] = None
    donor_source_url: Optional[str] = None
    donor_sources: List[Source] = Field(default_factory=list)

    # Reference links (Ballotpedia, Wikipedia, OpenSecrets, etc.)
    links: List[CandidateLink] = Field(default_factory=list)

    # Web presence
    website: Optional[HttpUrl] = None
    social_media: Dict[str, HttpUrl] = Field(default_factory=dict)

    # Withdrawal status — set when a candidate exits the race; data is preserved
    withdrawn: bool = False
    withdrawal_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


class PollMatchup(BaseModel):
    """A head-to-head matchup within a poll."""

    candidates: List[str] = Field(default_factory=list)
    percentages: List[float] = Field(default_factory=list)

    @field_validator("percentages", mode="before")
    @classmethod
    def coerce_missing_percentages(cls, v: Any) -> Any:
        """Treat omitted/null percentages as an empty list."""
        if v is None:
            return []
        return v

    @model_validator(mode="after")
    def validate_parallel_arrays(self) -> "PollMatchup":
        if self.candidates and self.percentages and len(self.candidates) != len(self.percentages):
            raise ValueError("candidates and percentages must have the same length")
        for pct in self.percentages:
            if not (0 <= pct <= 100):
                raise ValueError(f"percentage {pct} out of range 0-100")
        return self


class PollEntry(BaseModel):
    """A single opinion poll for a race."""

    pollster: str
    date: Optional[str] = None
    sample_size: Optional[int] = Field(None, ge=0)
    matchups: List[PollMatchup] = Field(default_factory=list)
    source_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Race (top-level output)
# ---------------------------------------------------------------------------


class RaceJSON(BaseModel):
    """RaceJSON v0.3 — Final output format."""

    schema_version: str = Field(default="0.3", description="RaceJSON schema version")
    id: str = Field(..., description="Race slug like 'mo-senate-2024'")
    election_date: str = Field(..., description="Election date in YYYY-MM-DD or ISO format")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,99}$", v):
            raise ValueError("race id must match ^[a-z0-9][a-z0-9_-]{0,99}$")
        return v

    candidates: List[Candidate]
    updated_utc: str = Field(..., description="Last updated timestamp in ISO format")
    generator: List[str] = Field(default_factory=list)

    # Metadata
    title: Optional[str] = None
    office: Optional[str] = None
    jurisdiction: Optional[str] = None  # Full geographic scope (e.g. "Missouri's 1st Congressional District", "United States")
    state: Optional[str] = None  # US state name for map highlighting (e.g. "Missouri"); null for national races
    district: Optional[str] = None
    description: Optional[str] = None

    # Polling data
    polling: List[PollEntry] = Field(default_factory=list)
    polling_note: Optional[str] = None  # set when no public polls are found

    # Voter action links
    ballotpedia_url: Optional[str] = Field(None, description="URL to the Ballotpedia election page")
    register_to_vote_url: Optional[str] = Field(None, description="URL for voter registration (state-specific)")
    how_to_vote_url: Optional[str] = Field(None, description="URL for voting instructions (state-specific)")

    # Multi-LLM reviews
    reviews: List[AgentReview] = Field(default_factory=list)
    validation_grade: Optional[ValidationGrade] = None

    # Post-run pipeline analysis (Gemini)
    post_run_analysis: Optional[Dict[str, Any]] = None
