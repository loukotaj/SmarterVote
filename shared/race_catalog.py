from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from shared.pipeline_config import FreshnessConfig


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def compute_freshness(updated_utc: Any) -> str | None:
    updated_at = _coerce_datetime(updated_utc)
    if updated_at is None:
        return None
    config = FreshnessConfig.from_env()
    age_days = (datetime.now(timezone.utc) - updated_at).days
    if age_days <= config.aging_days:
        return "recent"
    if age_days <= config.stale_days:
        return "stale"
    return "old"


def extract_quality_grade(race_data: Dict[str, Any]) -> str | None:
    validation_grade = race_data.get("validation_grade")
    if not isinstance(validation_grade, dict):
        return None
    grade = validation_grade.get("grade")
    return str(grade) if grade else None


def build_candidate_summaries(race_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = race_data.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [
        {
            "name": candidate.get("name", ""),
            "party": candidate.get("party"),
            "incumbent": candidate.get("incumbent", False),
            "image_url": candidate.get("image_url"),
        }
        for candidate in candidates
        if isinstance(candidate, dict)
    ]


def build_agent_metrics_summary(race_data: Dict[str, Any]) -> Dict[str, Any] | None:
    agent_metrics = race_data.get("agent_metrics")
    if not isinstance(agent_metrics, dict):
        return None
    return {
        "estimated_usd": agent_metrics.get("estimated_usd"),
        "model": agent_metrics.get("model"),
        "total_tokens": agent_metrics.get("total_tokens"),
    }


def build_forecast_summary(race_data: Dict[str, Any]) -> Dict[str, Any] | None:
    forecast = race_data.get("forecast")
    if not isinstance(forecast, dict):
        return None
    return {
        "predicted_winner_name": forecast.get("predicted_winner_name"),
        "predicted_winner_party": forecast.get("predicted_winner_party"),
        "win_probability": forecast.get("win_probability"),
        "party_probabilities": forecast.get("party_probabilities") or {},
        "margin_estimate": forecast.get("margin_estimate"),
        "rating": forecast.get("rating"),
        "confidence": forecast.get("confidence"),
        "rationale": forecast.get("rationale"),
        "takeaway": forecast.get("takeaway"),
        "key_reasons": forecast.get("key_reasons") or [],
        "uncertainty": forecast.get("uncertainty"),
        "based_on_poll_count": forecast.get("based_on_poll_count", 0),
        "generated_at": forecast.get("generated_at"),
        "model": forecast.get("model"),
        "source_urls": forecast.get("source_urls") or [],
    }


def build_race_summary_fields(race_id: str, race_data: Dict[str, Any]) -> Dict[str, Any]:
    candidates = build_candidate_summaries(race_data)
    updated_utc = race_data.get("updated_utc")
    return {
        "race_id": race_data.get("id") or race_id,
        "title": race_data.get("title"),
        "office": race_data.get("office"),
        "jurisdiction": race_data.get("jurisdiction"),
        "state": race_data.get("state"),
        "election_date": race_data.get("election_date"),
        "updated_utc": updated_utc,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "quality_grade": extract_quality_grade(race_data),
        "freshness": compute_freshness(updated_utc),
        "agent_metrics": build_agent_metrics_summary(race_data),
        "forecast": build_forecast_summary(race_data),
    }


def build_versioned_catalog_fields(prefix: str, race_data: Dict[str, Any]) -> Dict[str, Any]:
    candidates = build_candidate_summaries(race_data)
    updated_utc = race_data.get("updated_utc")
    return {
        f"{prefix}_updated_utc": updated_utc,
        f"{prefix}_candidate_count": len(candidates),
        f"{prefix}_quality_grade": extract_quality_grade(race_data),
    }
