from typing import Literal

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
    party_probabilities: dict[str, float] = Field(default_factory=dict)
    margin_estimate: float | None = None
    rating: str | None = None
    confidence: str | None = None
    rationale: str | None = None
    takeaway: str | None = None
    key_reasons: list[str] = Field(default_factory=list)
    uncertainty: str | None = None
    based_on_poll_count: int = 0
    generated_at: str | None = None
    model: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    market_signals: list[dict] = Field(default_factory=list)


class RaceSummary(BaseModel):
    """Summary of race for search and listing purposes."""

    id: str
    title: str | None = None
    office: str | None = None
    jurisdiction: str | None = None
    state: str | None = None
    contest_stage: str | None = None
    election_date: str
    updated_utc: str
    candidates: list[CandidateSummary]
    quality_grade: Literal["A", "B", "C", "D", "F"] | None = None
    agent_metrics: AgentMetricsSummary | None = None
    forecast: RaceForecastSummary | None = None
