"""Pydantic request/response models and input validation for races-api."""

import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, field_validator

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


class AdminChatMessage(BaseModel):
    role: str
    content: str


class AdminChatRequest(BaseModel):
    messages: List[AdminChatMessage]
    race_context: Optional[List[Dict[str, Any]]] = None


class AdminAgentMessageRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content cannot be empty")
        if len(normalized) > 12000:
            raise ValueError("content cannot exceed 12000 characters")
        return normalized
