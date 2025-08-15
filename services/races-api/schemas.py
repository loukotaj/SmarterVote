from typing import List

from pydantic import BaseModel


class CandidateSummary(BaseModel):
    """Summary of candidate for search purposes."""

    name: str
    party: str | None = None
    incumbent: bool


class RaceSummary(BaseModel):
    """Summary of race for search and listing purposes."""

    id: str
    title: str | None = None
    office: str | None = None
    jurisdiction: str | None = None
    election_date: str
    updated_utc: str
    candidates: List[CandidateSummary]
