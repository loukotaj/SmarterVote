from typing import Dict, List

from pydantic import BaseModel, Field


class CandidateSummary(BaseModel):
    """Summary of candidate for search purposes."""

    name: str
    party: str | None = None
    incumbent: bool
    image_url: str | None = None


class AgentMetricsSummary(BaseModel):
    estimated_usd: float | None = None
    model: str | None = None
    total_tokens: int | None = None


class RaceForecastSummary(BaseModel):
    predicted_winner_name: str | None = None
    predicted_winner_party: str | None = None
    win_probability: float | None = None
    party_probabilities: Dict[str, float] = Field(default_factory=dict)
    margin_estimate: float | None = None
    rating: str | None = None
    confidence: str | None = None
    rationale: str | None = None
    based_on_poll_count: int = 0
    generated_at: str | None = None
    model: str | None = None
    source_urls: List[str] = Field(default_factory=list)


class RaceSummary(BaseModel):
    """Summary of race for search and listing purposes."""

    id: str
    title: str | None = None
    office: str | None = None
    jurisdiction: str | None = None
    state: str | None = None
    election_date: str
    updated_utc: str
    candidates: List[CandidateSummary]
    agent_metrics: AgentMetricsSummary | None = None
    forecast: RaceForecastSummary | None = None
