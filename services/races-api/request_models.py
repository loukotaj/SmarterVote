"""Pydantic request/response models and input validation for races-api."""

import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, field_validator, model_validator

from shared.pipeline_config import (
    normalize_model_profile,
    normalize_pipeline_steps,
    normalize_review_providers,
    validate_model_override_keys,
)

_RACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")


def validate_race_id(race_id: str) -> None:
    """Raise HTTP 400 if race_id doesn't match the canonical format."""
    if not _RACE_ID_RE.match(race_id):
        raise HTTPException(status_code=400, detail="Invalid race_id format")


class RunOptions(BaseModel):
    cheap_mode: Optional[bool] = None
    force_fresh: Optional[bool] = None
    save_artifact: Optional[bool] = None
    enabled_steps: Optional[List[str]] = None
    research_model: Optional[str] = None
    claude_model: Optional[str] = None
    gemini_model: Optional[str] = None
    grok_model: Optional[str] = None
    model_profile: Optional[str] = None
    model_overrides: Optional[Dict[str, str]] = None
    review_providers: Optional[List[str]] = None
    max_candidates: Optional[int] = None
    candidate_names: Optional[List[str]] = None
    target_no_info: Optional[bool] = None
    note: Optional[str] = None
    goal: Optional[str] = None
    runner: Optional[str] = None

    @field_validator("runner")
    @classmethod
    def validate_runner(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized not in {"cf", "local"}:
            raise ValueError("runner must be 'cf' or 'local'")
        return normalized

    @field_validator("enabled_steps")
    @classmethod
    def validate_enabled_steps(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return normalize_pipeline_steps(value)

    @field_validator("max_candidates")
    @classmethod
    def validate_max_candidates(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 1:
            raise ValueError("max_candidates must be at least 1 when provided")
        return value

    @field_validator("model_overrides")
    @classmethod
    def validate_model_overrides(cls, value: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        return validate_model_override_keys(value)

    @field_validator("candidate_names")
    @classmethod
    def normalize_candidate_names(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized = [name.strip() for name in value if isinstance(name, str) and name.strip()]
        return list(dict.fromkeys(normalized)) or None

    @field_validator("model_profile")
    @classmethod
    def validate_model_profile(cls, value: Optional[str]) -> Optional[str]:
        return normalize_model_profile(value)

    @field_validator("review_providers")
    @classmethod
    def validate_review_providers(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return normalize_review_providers(value)

    @model_validator(mode="after")
    def validate_step_dependencies(self) -> "RunOptions":
        if self.enabled_steps and "iteration" in self.enabled_steps and "review" not in self.enabled_steps:
            raise ValueError("'iteration' requires 'review' in enabled_steps")
        return self


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
