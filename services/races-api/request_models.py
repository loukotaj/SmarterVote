"""Pydantic request/response models and input validation for races-api."""

import re
from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

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
