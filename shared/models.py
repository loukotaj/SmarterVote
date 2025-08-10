"""
Core Pydantic models for SmarterVote data structures.
Extracted from pipeline for shared use across services.
RaceJSON v0.2 - Corpus-First Design
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class SourceType(str, Enum):
    """Types of data sources."""

    WEBSITE = "website"
    PDF = "pdf"
    API = "api"
    SOCIAL_MEDIA = "social_media"
    NEWS = "news"
    GOVERNMENT = "government"
    FRESH_SEARCH = "fresh_search"  # From issue-specific Google searches


class ConfidenceLevel(str, Enum):
    """Confidence levels for processed data."""

    HIGH = "high"  # 2-of-3 LLM agreement
    MEDIUM = "medium"  # Partial consensus
    LOW = "low"  # No consensus, minority view stored
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    """Status of data processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CanonicalIssue(str, Enum):
    """The 11 canonical issues for consistent comparison across races."""

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


class Source(BaseModel):
    """Data source information."""

    url: HttpUrl
    type: SourceType
    title: Optional[str] = None
    description: Optional[str] = None
    last_accessed: datetime
    checksum: Optional[str] = None
    is_fresh: bool = False  # Flag for fresh issue search results


class ChromaChunk(BaseModel):
    """Document chunk stored in ChromaDB corpus."""

    id: str
    race_id: str
    candidate_name: Optional[str] = None
    issue_tag: Optional[CanonicalIssue] = None
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source: Source
    created_at: datetime
    is_fresh: bool = False  # From fresh issue search


class ExtractedContent(BaseModel):
    """Content extracted from a source."""

    source: Source
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    extraction_timestamp: datetime
    word_count: int
    language: Optional[str] = None


class VectorDocument(BaseModel):
    """Document retrieved from vector search."""

    id: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    similarity_score: Optional[float] = None
    source: Source


class Summary(BaseModel):
    """AI-generated summary of content."""

    content: str
    model: Literal["gpt-4o", "claude-3.5", "grok-4"]
    confidence: ConfidenceLevel
    tokens_used: Optional[int] = None
    created_at: datetime
    source_ids: List[str] = Field(default_factory=list)


class LLMResponse(BaseModel):
    """Response from a single LLM."""

    model: Literal["gpt-4o", "claude-3.5", "grok-4"]
    content: str
    tokens_used: Optional[int] = None
    created_at: datetime


class TriangulatedSummary(BaseModel):
    """Summary triangulated from 3 LLMs."""

    final_content: str
    confidence: ConfidenceLevel
    llm_responses: List[LLMResponse]
    consensus_method: str  # "2-of-3" or "minority_view"
    arbitration_notes: Optional[str] = None


class IssueStance(BaseModel):
    """Candidate's stance on a canonical issue."""

    issue: CanonicalIssue
    stance: str
    confidence: ConfidenceLevel
    sources: List[Source] = Field(default_factory=list)  # Source objects with detailed information


class TopDonor(BaseModel):
    """Top campaign donor information."""

    name: str
    amount: Optional[float] = None
    organization: Optional[str] = None
    source: Source  # Source object with detailed information


class Candidate(BaseModel):
    """Candidate information for RaceJSON v0.2."""

    name: str
    party: Optional[str] = None
    incumbent: bool = False
    summary: str  # Triangulated summary from 3 LLMs
    issues: Dict[CanonicalIssue, IssueStance] = Field(default_factory=dict)
    top_donors: List[TopDonor] = Field(default_factory=list)
    website: Optional[HttpUrl] = None
    social_media: Dict[str, HttpUrl] = Field(default_factory=dict)


class RaceJSON(BaseModel):
    """RaceJSON v0.2 - Final output format."""

    id: str = Field(..., description="Race slug like 'mo-senate-2024'")
    election_date: datetime
    candidates: List[Candidate]
    updated_utc: datetime
    generator: List[Literal["gpt-4o", "claude-3.5", "grok-4"]] = Field(default_factory=list)

    # Optional metadata
    title: Optional[str] = None
    office: Optional[str] = None
    jurisdiction: Optional[str] = None


class ProcessingJob(BaseModel):
    """Job for processing a race through the corpus-first pipeline."""

    job_id: str
    race_id: str
    status: ProcessingStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # Pipeline step tracking
    step_discover: bool = False
    step_fetch: bool = False
    step_extract: bool = False
    step_corpus: bool = False
    step_fresh_search: bool = False
    step_rag_summary: bool = False
    step_arbitrate: bool = False
    step_publish: bool = False


class FreshSearchQuery(BaseModel):
    """Query for fresh issue-specific Google searches."""

    race_id: str
    candidate_name: str
    issue: CanonicalIssue = None
    query_terms: List[str]
    max_results: int = 5


class RAGQuery(BaseModel):
    """Query for RAG-based summary generation."""

    race_id: str
    query_type: Literal["candidate_summary", "issue_stance"]
    candidate_name: Optional[str] = None
    issue: Optional[CanonicalIssue] = None
    max_chunks: int = 25  # 25 for candidate summary, 12 for issue stance


class ArbitrationResult(BaseModel):
    """Result of LLM triangulation and arbitration."""

    content: str
    confidence: ConfidenceLevel
    consensus_method: str
    llm_responses: List[LLMResponse]
    minority_view: Optional[str] = None  # Stored when confidence is LOW
