"""Pydantic request/response models and input validation for races-api."""

import re
from datetime import date, datetime
from typing import List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from shared.pipeline_options import PipelineRunOptions

_RACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")


def validate_race_id(race_id: str) -> None:
    """Raise HTTP 400 if race_id doesn't match the canonical format."""
    if not _RACE_ID_RE.match(race_id):
        raise HTTPException(status_code=400, detail="Invalid race_id format")


class RunOptions(PipelineRunOptions):
    """API wire model; omitted values remain unset for queue defaulting."""


class RaceQueueRequest(BaseModel):
    race_ids: List[str]
    options: Optional[RunOptions] = None


class BatchPublishRequest(BaseModel):
    race_ids: List[str]


class RepairPlanRequest(BaseModel):
    race_ids: List[str]

    @field_validator("race_ids")
    @classmethod
    def validate_race_ids(cls, value: List[str]) -> List[str]:
        normalized = list(dict.fromkeys(str(race_id).strip() for race_id in value if str(race_id).strip()))
        if not normalized:
            raise ValueError("race_ids cannot be empty")
        if len(normalized) > 200:
            raise ValueError("race_ids cannot contain more than 200 races")
        for race_id in normalized:
            if not _RACE_ID_RE.match(race_id):
                raise ValueError(f"invalid race_id: {race_id}")
        return normalized


class AssetAuditRequest(RepairPlanRequest):
    persist: bool = False
    max_urls_per_race: int = Field(default=100, ge=1, le=300)


class CoverageOverrideRequest(BaseModel):
    official_source_url: HttpUrl
    reason: str = Field(min_length=10, max_length=1000)
    approved_by: str = Field(min_length=1, max_length=200)
    active: bool = True


class ResearchCheckpointRequest(BaseModel):
    result_state: Literal["waiting", "stabilizing", "stable", "runoff_pending", "manual_review"]
    official_result_url: Optional[HttpUrl] = None
    first_checked_at: Optional[datetime] = None
    second_checked_at: Optional[datetime] = None
    advancing_names: List[str] = Field(default_factory=list, max_length=100)
    event_type: Optional[str] = Field(default=None, max_length=100)
    event_date: Optional[date] = None
    operator: str = Field(min_length=1, max_length=200)
    blocker: Optional[str] = Field(default=None, max_length=1000)
    program_id: Optional[str] = Field(default=None, max_length=200)
    cohort_id: Optional[str] = Field(default=None, max_length=200)
    last_reviewed_discovery_fingerprint: Optional[str] = Field(default=None, max_length=128)
    coverage_override: Optional[CoverageOverrideRequest] = None

    @field_validator("advancing_names")
    @classmethod
    def normalize_advancing_names(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(name.strip() for name in value if name.strip()))

    @model_validator(mode="after")
    def validate_stable_evidence(self) -> "ResearchCheckpointRequest":
        if self.result_state != "stable":
            return self
        required = {
            "official_result_url": self.official_result_url,
            "first_checked_at": self.first_checked_at,
            "second_checked_at": self.second_checked_at,
            "advancing_names": self.advancing_names,
            "event_type": self.event_type,
            "event_date": self.event_date,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"stable checkpoints require: {', '.join(missing)}")
        assert self.first_checked_at is not None and self.second_checked_at is not None
        if self.first_checked_at.tzinfo is None or self.second_checked_at.tzinfo is None:
            raise ValueError("stable checkpoint timestamps must include a timezone offset")
        if (self.second_checked_at - self.first_checked_at).total_seconds() < 6 * 3600:
            raise ValueError("stable checkpoints require checks at least six hours apart")
        return self
