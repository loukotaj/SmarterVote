"""Shared pipeline enums, limits, and validation helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Mapping

from shared.models import CanonicalIssue

PIPELINE_STEP_ORDER: tuple[str, ...] = (
    "discovery",
    "images",
    "issues",
    "finance",
    "refinement",
    "polling",
    "voter_resources",
    "review",
    "iteration",
)
PIPELINE_STEP_IDS = frozenset(PIPELINE_STEP_ORDER)

PIPELINE_STEP_LABELS: dict[str, str] = {
    "discovery": "Discovery",
    "images": "Image Resolution",
    "issues": "Issue Research",
    "finance": "Finance & Voting",
    "refinement": "Refinement",
    "polling": "Polling",
    "voter_resources": "Voter Resources",
    "review": "AI Review",
    "iteration": "Review Iteration",
}

# Weights for progress computation. These must sum to 100.
PIPELINE_STEP_WEIGHTS: dict[str, int] = {
    "discovery": 12,
    "images": 4,
    "issues": 30,
    "finance": 9,
    "refinement": 12,
    "polling": 8,
    "voter_resources": 5,
    "review": 12,
    "iteration": 8,
}

MODEL_PROFILES = frozenset({"economy", "balanced", "quality", "custom"})
MODEL_ROLES = frozenset({"primary", "small", "review_claude", "review_gemini", "review_grok"})
REVIEW_PROVIDERS: tuple[str, ...] = ("claude", "gemini", "grok")
REVIEW_PROVIDER_IDS = frozenset(REVIEW_PROVIDERS)

CANONICAL_ISSUE_COUNT = len(CanonicalIssue)


def _env_int(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(value, maximum)
    return value


@dataclass(frozen=True)
class PipelineRuntimeConfig:
    """Runtime limits that used to be scattered as literals or raw env reads."""

    max_review_cycles: int = 1
    issue_concurrency: int = 3
    issue_max_attempts: int = 3
    iteration_min_iterations: int = 14
    quality_critical_issue_stances: int = CANONICAL_ISSUE_COUNT // 2
    quality_warning_issue_stances: int = (CANONICAL_ISSUE_COUNT * 2) // 3

    @classmethod
    def from_env(cls) -> "PipelineRuntimeConfig":
        critical = _env_int("PIPELINE_QUALITY_CRITICAL_ISSUE_STANCES", CANONICAL_ISSUE_COUNT // 2, 1, CANONICAL_ISSUE_COUNT)
        warning = _env_int(
            "PIPELINE_QUALITY_WARNING_ISSUE_STANCES",
            (CANONICAL_ISSUE_COUNT * 2) // 3,
            critical,
            CANONICAL_ISSUE_COUNT,
        )
        return cls(
            max_review_cycles=_env_int("PIPELINE_MAX_REVIEW_CYCLES", 1, 1, 3),
            issue_concurrency=_env_int("PIPELINE_ISSUE_CONCURRENCY", 3, 1, 8),
            issue_max_attempts=_env_int("PIPELINE_ISSUE_MAX_ATTEMPTS", 3, 1, None),
            iteration_min_iterations=_env_int("PIPELINE_ITERATION_MIN_ITERATIONS", 14, 1, None),
            quality_critical_issue_stances=critical,
            quality_warning_issue_stances=warning,
        )


@dataclass(frozen=True)
class RetentionConfig:
    """Operational retention and log bounding defaults."""

    live_run_logs_days: int = 30
    completed_queue_days: int = 14
    debug_artifacts_days: int = 30
    continuation_checkpoints_days: int = 7
    search_cache_ttl_hours: int = 168
    page_cache_ttl_hours: int = 24
    live_log_buffer_size: int = 1000
    run_log_buffer_size: int = 1000
    firestore_log_batch_size: int = 25
    max_log_message_chars: int = 4000

    @classmethod
    def from_env(cls) -> "RetentionConfig":
        return cls(
            live_run_logs_days=_env_int("PIPELINE_LIVE_RUN_LOG_RETENTION_DAYS", 30, 1, None),
            completed_queue_days=_env_int("PIPELINE_COMPLETED_QUEUE_RETENTION_DAYS", 14, 1, None),
            debug_artifacts_days=_env_int("PIPELINE_DEBUG_ARTIFACT_RETENTION_DAYS", 30, 1, None),
            continuation_checkpoints_days=_env_int("PIPELINE_CHECKPOINT_RETENTION_DAYS", 7, 1, None),
            search_cache_ttl_hours=_env_int("PIPELINE_SEARCH_CACHE_TTL_HOURS", 168, 1, None),
            page_cache_ttl_hours=_env_int("PIPELINE_PAGE_CACHE_TTL_HOURS", 24, 1, None),
            live_log_buffer_size=_env_int("PIPELINE_LIVE_LOG_BUFFER_SIZE", 1000, 1, None),
            run_log_buffer_size=_env_int("PIPELINE_RUN_LOG_BUFFER_SIZE", 1000, 1, None),
            firestore_log_batch_size=_env_int("PIPELINE_FIRESTORE_LOG_BATCH_SIZE", 25, 1, 500),
            max_log_message_chars=_env_int("PIPELINE_MAX_LOG_MESSAGE_CHARS", 4000, 256, None),
        )


@dataclass(frozen=True)
class FreshnessConfig:
    """Race data freshness thresholds in days."""

    fresh_days: int = 7
    recent_days: int = 14
    aging_days: int = 30
    stale_days: int = 180
    alert_warning_days: int = 14
    alert_critical_days: int = 30

    @classmethod
    def from_env(cls) -> "FreshnessConfig":
        fresh = _env_int("PIPELINE_FRESHNESS_FRESH_DAYS", 7, 0, None)
        recent = _env_int("PIPELINE_FRESHNESS_RECENT_DAYS", 14, fresh, None)
        aging = _env_int("PIPELINE_FRESHNESS_AGING_DAYS", 30, recent, None)
        stale = _env_int("PIPELINE_FRESHNESS_STALE_DAYS", 180, aging, None)
        warning = _env_int("PIPELINE_FRESHNESS_ALERT_WARNING_DAYS", recent, 1, None)
        critical = _env_int("PIPELINE_FRESHNESS_ALERT_CRITICAL_DAYS", aging, warning, None)
        return cls(
            fresh_days=fresh,
            recent_days=recent,
            aging_days=aging,
            stale_days=stale,
            alert_warning_days=warning,
            alert_critical_days=critical,
        )


def normalize_pipeline_steps(value: Iterable[str] | None) -> list[str] | None:
    if value is None:
        return None
    normalized = [step.strip() for step in value if isinstance(step, str) and step.strip()]
    if not normalized:
        raise ValueError("enabled_steps cannot be empty when provided")
    deduped = list(dict.fromkeys(normalized))
    invalid = [step for step in deduped if step not in PIPELINE_STEP_IDS]
    if invalid:
        raise ValueError(f"Unknown enabled_steps: {', '.join(invalid)}")
    return deduped


def normalize_review_providers(value: Iterable[str] | None) -> list[str] | None:
    if value is None:
        return None
    normalized = [provider.strip().lower() for provider in value if isinstance(provider, str) and provider.strip()]
    deduped = list(dict.fromkeys(normalized))
    if not deduped:
        raise ValueError("review_providers cannot be empty when provided")
    invalid = [provider for provider in deduped if provider not in REVIEW_PROVIDER_IDS]
    if invalid:
        raise ValueError(f"Unknown review_providers: {', '.join(invalid)}")
    return deduped


def normalize_model_profile(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in MODEL_PROFILES:
        raise ValueError("model_profile must be one of: economy, balanced, quality, custom")
    return normalized


def validate_model_override_keys(value: Mapping[str, str] | None) -> dict[str, str] | None:
    if value is None:
        return None
    invalid = [str(key) for key in value if str(key) not in MODEL_ROLES]
    if invalid:
        raise ValueError(f"Unknown model_overrides roles: {', '.join(invalid)}")
    return dict(value)
