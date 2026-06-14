"""Pydantic request/response models and input validation for races-api."""

import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, field_validator, model_validator

_RACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
_PIPELINE_STEPS = {
    "discovery",
    "images",
    "issues",
    "finance",
    "refinement",
    "polling",
    "voter_resources",
    "review",
    "iteration",
}


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

    @field_validator("enabled_steps")
    @classmethod
    def validate_enabled_steps(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized = [step.strip() for step in value if isinstance(step, str) and step.strip()]
        if not normalized:
            raise ValueError("enabled_steps cannot be empty when provided")
        deduped = list(dict.fromkeys(normalized))
        invalid = [step for step in deduped if step not in _PIPELINE_STEPS]
        if invalid:
            raise ValueError(f"Unknown enabled_steps: {', '.join(invalid)}")
        return deduped

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
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"economy", "balanced", "quality", "custom"}:
            raise ValueError("model_profile must be one of: economy, balanced, quality, custom")
        return normalized

    @field_validator("review_providers")
    @classmethod
    def validate_review_providers(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized = [provider.strip().lower() for provider in value if isinstance(provider, str) and provider.strip()]
        deduped = list(dict.fromkeys(normalized))
        invalid = [provider for provider in deduped if provider not in {"claude", "gemini", "grok"}]
        if invalid:
            raise ValueError(f"Unknown review_providers: {', '.join(invalid)}")
        return deduped

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
