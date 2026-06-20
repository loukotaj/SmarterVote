"""Queue forecast-only pipeline runs for published races.

This script is intentionally opt-in and does not publish drafts. It queues
existing published races with enabled_steps=["forecast"] and model_profile="quality".
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

MISSING_2026_GOVERNOR_RACES = ["me-governor-2026", "ne-governor-2026", "sc-governor-2026"]


def _load_local_published_ids(path: Path) -> list[str]:
    index_path = path / "summaries.json"
    if index_path.exists():
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return sorted(str(item["id"]) for item in payload if isinstance(item, dict) and item.get("id"))
    return sorted(file_path.stem for file_path in path.glob("*.json") if file_path.name != "summaries.json")


def _headers() -> dict[str, str]:
    token = os.getenv("ADMIN_API_KEY", "").strip()
    return {"X-Admin-Key": token} if token else {}


def queue_forecast_runs(api_base: str, race_ids: list[str], *, dry_run: bool, batch_size: int) -> list[dict[str, Any]]:
    options = {
        "enabled_steps": ["forecast"],
        "model_profile": "quality",
        "cheap_mode": False,
        "note": "Forecast backfill",
        "goal": "Generate race forecast from existing published data only.",
    }
    results: list[dict[str, Any]] = []
    for start in range(0, len(race_ids), batch_size):
        batch = race_ids[start : start + batch_size]
        payload = {"race_ids": batch, "options": options}
        if dry_run:
            results.append({"dry_run": True, "payload": payload})
            continue
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{api_base.rstrip('/')}/api/races/queue", json=payload, headers=_headers())
            response.raise_for_status()
            results.append(response.json())
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue forecast-only backfill runs.")
    parser.add_argument("--api-base", default=os.getenv("RACES_API_URL", "http://localhost:8080"))
    parser.add_argument("--data-dir", default="data/published")
    parser.add_argument("--race-id", action="append", dest="race_ids", help="Queue only this race ID; repeatable.")
    parser.add_argument("--include-missing-governors", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    race_ids = args.race_ids or _load_local_published_ids(Path(args.data_dir))
    if args.include_missing_governors:
        race_ids = sorted(set(race_ids).union(MISSING_2026_GOVERNOR_RACES))
    results = queue_forecast_runs(args.api_base, race_ids, dry_run=args.dry_run, batch_size=max(1, args.batch_size))
    print(json.dumps({"queued_batches": len(results), "race_count": len(race_ids), "results": results}, indent=2))


if __name__ == "__main__":
    main()
