"""
Pydantic models for SmarterVote data structures.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl


class SourceType(str, Enum):
    """Types of data sources."""
    WEBSITE = "website"
    PDF = "pdf"
    API = "api"
    SOCIAL_MEDIA = "social_media"
    NEWS = "news"


class ConfidenceLevel(str, Enum):
    """Confidence levels for processed data."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    """Status of data processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Source(BaseModel):
    """Data source information."""
    url: HttpUrl
    type: SourceType
    title: Optional[str] = None
    description: Optional[str] = None
    last_accessed: datetime
    checksum: Optional[str] = None


class ExtractedContent(BaseModel):
    """Content extracted from a source."""
    source: Source
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    extraction_timestamp: datetime
    word_count: int
    language: Optional[str] = None


class Summary(BaseModel):
    """AI-generated summary of content."""
    content: str
    confidence: ConfidenceLevel
    model_used: str
    tokens_used: Optional[int] = None
    created_at: datetime
    source_references: List[str] = Field(default_factory=list)


class Position(BaseModel):
    """Candidate position on an issue."""
    topic: str
    stance: str
    summary: str
    confidence: ConfidenceLevel
    sources: List[Source] = Field(default_factory=list)
    last_updated: datetime


class Candidate(BaseModel):
    """Candidate information."""
    name: str
    party: Optional[str] = None
    incumbent: bool = False
    website: Optional[HttpUrl] = None
    biography: Optional[str] = None
    positions: List[Position] = Field(default_factory=list)
    social_media: Dict[str, HttpUrl] = Field(default_factory=dict)
    endorsements: List[str] = Field(default_factory=list)
    funding_sources: List[str] = Field(default_factory=list)
    last_updated: datetime


class Race(BaseModel):
    """Electoral race information."""
    id: str = Field(..., description="Unique identifier for the race")
    title: str
    office: str
    jurisdiction: str
    election_date: datetime
    candidates: List[Candidate] = Field(default_factory=list)
    description: Optional[str] = None
    key_issues: List[str] = Field(default_factory=list)
    status: ProcessingStatus = ProcessingStatus.PENDING
    sources: List[Source] = Field(default_factory=list)
    created_at: datetime
    last_updated: datetime
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN


class ProcessingJob(BaseModel):
    """Job for processing a race."""
    job_id: str
    race_id: str
    status: ProcessingStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


class SearchQuery(BaseModel):
    """Search query for discovering content."""
    race_id: str
    candidate_name: Optional[str] = None
    topic: Optional[str] = None
    jurisdiction: str
    keywords: List[str] = Field(default_factory=list)
    date_range: Optional[tuple[datetime, datetime]] = None


class VectorDocument(BaseModel):
    """Document stored in vector database."""
    id: str
    race_id: str
    candidate_name: Optional[str] = None
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    source: Source
