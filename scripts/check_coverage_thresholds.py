"""Enforce risk-based per-file coverage floors from a coverage.py JSON report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_THRESHOLDS = {
    "pipeline_client/backend/race_manager.py": 33.0,
    "pipeline_client/worker.py": 37.0,
    "smartervote_mcp/server.py": 65.0,
}


def _normalized_files(report: dict) -> dict[str, dict]:
    return {name.replace("\\", "/"): data for name, data in report.get("files", {}).items()}


def check_report(report_path: Path, thresholds: dict[str, float]) -> list[str]:
    files = _normalized_files(json.loads(report_path.read_text(encoding="utf-8")))
    failures: list[str] = []
    for filename, minimum in thresholds.items():
        data = files.get(filename)
        if data is None:
            failures.append(f"{filename}: missing from coverage report")
            continue
        actual = float(data.get("summary", {}).get("percent_covered", 0.0))
        if actual < minimum:
            failures.append(f"{filename}: {actual:.1f}% is below {minimum:.1f}%")
        else:
            print(f"ok    {filename}: {actual:.1f}% >= {minimum:.1f}%")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="coverage.json", type=Path)
    args = parser.parse_args()
    failures = check_report(args.report, DEFAULT_THRESHOLDS)
    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
