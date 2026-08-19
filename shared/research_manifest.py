"""Protected research coverage and election-event manifest access."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

MANIFEST_PATH = Path(__file__).with_name("data") / "research_manifest_2026.json"
EXPECTED_CYCLE = 2026
EXPECTED_COVERAGE_COUNT = 507


class ResearchManifestError(RuntimeError):
    """Raised when the committed manifest is absent or internally inconsistent."""


@lru_cache(maxsize=1)
def load_research_manifest() -> Dict[str, Any]:
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchManifestError(f"Cannot load research manifest: {exc}") from exc

    races = payload.get("races")
    if payload.get("cycle") != EXPECTED_CYCLE or not isinstance(races, list):
        raise ResearchManifestError("Research manifest has an invalid cycle or races list")
    by_id = {
        str(row.get("race_id")): dict(row) for row in races if isinstance(row, dict) and str(row.get("race_id") or "").strip()
    }
    if len(races) != EXPECTED_COVERAGE_COUNT or len(by_id) != EXPECTED_COVERAGE_COUNT:
        raise ResearchManifestError(
            f"Research manifest must contain {EXPECTED_COVERAGE_COUNT} unique races; "
            f"found {len(races)} rows and {len(by_id)} unique IDs"
        )
    payload["by_id"] = by_id
    return payload


def get_research_manifest_entry(race_id: str) -> Dict[str, Any] | None:
    entry = load_research_manifest()["by_id"].get(str(race_id))
    return dict(entry) if isinstance(entry, dict) else None


def list_research_manifest_entries() -> list[Dict[str, Any]]:
    return [dict(row) for row in load_research_manifest()["races"]]


def excluded_race_reason(race_id: str) -> str | None:
    reason = load_research_manifest().get("excluded_races", {}).get(str(race_id))
    return str(reason) if reason else None


def clear_research_manifest_cache() -> None:
    """Test helper for validating failure modes against a patched manifest path."""
    load_research_manifest.cache_clear()
