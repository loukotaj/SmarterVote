"""Replay real roster tool payloads against the local evidence guards.

The slow loop for roster-guard work is merge -> rebuild the worker -> queue a run
-> wait ten minutes -> read logs. This runs the same guards in-process against
payloads captured from real runs, so a guard change can be checked in under a
second before anything is committed.

Payloads live in ``scripts/fixtures/roster_evidence/*.json`` and are lifted
verbatim from worker logs. Each case records the tool call an agent actually made
and whether it should be accepted, so a guard that regresses on a case we already
fixed fails here instead of in production.

    python scripts/replay_roster_evidence.py                 # all fixtures
    python scripts/replay_roster_evidence.py ne-house-02     # one fixture
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline_client.agent.agent import _make_editing_handlers  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "roster_evidence"


def _run_case(case: Dict[str, Any]) -> tuple[bool, str]:
    """Execute one recorded tool call and report whether it was accepted."""
    race_json = json.loads(json.dumps(case["race_json"]))  # deep copy per case
    logs: List[str] = []
    handlers = _make_editing_handlers(race_json, lambda _level, message: logs.append(str(message)))

    result = handlers[case["tool"]](case["args"])
    blocked = str(result).startswith("ERROR") or "Blocked" in str(result) or "blocked" in str(result)
    accepted = not blocked
    return accepted, str(result)


def main(argv: List[str]) -> int:
    wanted = argv[1] if len(argv) > 1 else ""
    paths = sorted(p for p in FIXTURE_DIR.glob("*.json") if wanted in p.stem)
    if not paths:
        print(f"No fixtures matching {wanted!r} in {FIXTURE_DIR}")
        return 2

    failures = 0
    total = 0
    for path in paths:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        print(f"\n=== {path.stem} — {fixture.get('description', '')}")
        for case in fixture["cases"]:
            total += 1
            expected = bool(case["expect_accepted"])
            try:
                accepted, detail = _run_case(case)
            except Exception as exc:  # a guard raising is itself a failure
                accepted, detail = False, f"{type(exc).__name__}: {exc}"
            ok = accepted == expected
            failures += 0 if ok else 1
            verdict = "ok  " if ok else "FAIL"
            want = "accept" if expected else "block"
            got = "accepted" if accepted else "blocked"
            print(f"  [{verdict}] {case['name']}  (want {want}, got {got})")
            if not ok or not accepted:
                print(f"         -> {detail[:220]}")

    print(f"\n{total - failures}/{total} cases behaved as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
