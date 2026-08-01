"""Triage community race issues against the live races API.

Runs hourly from .github/workflows/race-issue-triage.yaml. Read-only with respect to the
pipeline: it never queues a run and never spends LLM or search credits. It reads the admin
race record for each reported race and posts at most two comments per issue:

1. ``auto-triaged`` -- the initial verdict (does the race exist, is the reported gap real,
   what run *would* fix it). Posted once, then the label prevents repeats.
2. ``draft-ready``  -- posted later if a publishable draft appears for that race.

Queueing the recommended run stays a human (or durable-agent) decision.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from typing import Any, Iterable

REPO = os.getenv("TRIAGE_REPO", "SmarterVote/SmarterVote")
API_URL = os.getenv("SMARTERVOTE_RACES_API_URL", "https://races-api-dev-ddsvfazica-uc.a.run.app").rstrip("/")
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")
NOTIFY_HANDLE = os.getenv("TRIAGE_NOTIFY_HANDLE", "@loukotaj")

TRIAGED_LABEL = "auto-triaged"
DRAFT_READY_LABEL = "draft-ready"
RACE_ISSUE_LABELS = {"data-request", "race-request"}
RACE_ISSUE_TITLE_PREFIXES = ("[Data]", "[Race Request]")

RACE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
# Issue-forms render each field as "### Label\n\n<value>" up to the next "###".
FIELD_PATTERN = "### {label}\\s*\\n+(.+?)(?=\\n###|\\Z)"

# Issue research is never queued alone: raw stances without review/iteration are unvalidated
# and nothing gets published, so the remedy is always the combined run.
COMBINED_STEPS = ["issues", "finance", "refinement", "polling", "forecast", "voter_resources", "review", "iteration"]

# "What type of data is missing?" checkbox labels -> the concern they represent.
REPORTED_TYPE_CONCERNS = {
    "issue stances / positions": "issues",
    "donor information": "finance",
    "voting record": "finance",
    "biographical information": "roster",
    "campaign website": "roster",
}

# catalog_health gaps -> the concern they corroborate.
GAP_CONCERNS = {
    "missing_issue_research": "issues",
    "unsourced_issue_stances": "issues",
    "incomplete_finance": "finance",
    "missing_images": "images",
    "forecast_missing_sources": "forecast",
}


class TriageError(RuntimeError):
    """Raised when an individual issue cannot be triaged."""


def gh(*args: str, check: bool = True) -> str:
    """Run a gh CLI command and return stdout."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def fetch_race_record(race_id: str) -> dict[str, Any] | None:
    """Return the admin race record, or None when the race is not in the catalog."""
    request = urllib.request.Request(
        f"{API_URL}/api/races/{race_id}",
        headers={"X-Admin-Key": ADMIN_KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in (401, 403):
            # A bad key breaks every issue, not just this one -- fail the whole job loudly.
            raise SystemExit(f"races API rejected ADMIN_API_KEY ({exc.code}). Check the repo secret.") from exc
        raise TriageError(f"races API returned HTTP {exc.code} for {race_id}") from exc
    except urllib.error.URLError as exc:
        raise TriageError(f"could not reach races API for {race_id}: {exc.reason}") from exc


def extract_field(body: str, label: str) -> str:
    """Pull a single issue-form field value out of the rendered issue body."""
    match = re.search(FIELD_PATTERN.format(label=re.escape(label)), body or "", re.DOTALL)
    if not match:
        return ""
    value = match.group(1).strip()
    return "" if value in {"_No response_", "N/A"} else value


def normalize_name(name: str) -> str:
    """Fold accents, drop punctuation, and collapse whitespace for name comparison."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", stripped.lower()).split())


def name_parts(name: str) -> list[str]:
    """Normalized name words with generational suffixes dropped."""
    return [part for part in normalize_name(name).split() if part not in NAME_SUFFIXES]


def find_candidate(record: dict[str, Any], reported_name: str) -> dict[str, Any] | None:
    """Locate the reported candidate in the roster, tolerating punctuation and accents."""
    target = normalize_name(reported_name)
    if not target:
        return None
    candidates = record.get("candidates") or []
    for candidate in candidates:
        if normalize_name(candidate.get("name", "")) == target:
            return candidate
    # Fall back to surname matching so "Bob Casey Jr." still matches "Bob Casey".
    target_parts = name_parts(reported_name)
    if not target_parts:
        return None
    surname = target_parts[-1]
    for candidate in candidates:
        candidate_parts = name_parts(candidate.get("name", ""))
        if candidate_parts and candidate_parts[-1] == surname and candidate_parts[0][:1] == target_parts[0][:1]:
            return candidate
    return None


def reported_concerns(body: str) -> set[str]:
    """Read the checked 'What type of data is missing?' boxes into concern keys."""
    checked = {label.strip().lower() for label in re.findall(r"^\s*-\s*\[x\]\s*(.+?)\s*$", body or "", re.MULTILINE)}
    return {REPORTED_TYPE_CONCERNS[label] for label in checked if label in REPORTED_TYPE_CONCERNS}


def recommend(concerns: Iterable[str], roster_unverified: bool, has_draft: bool) -> list[dict[str, Any]]:
    """Order remedies for the observed concerns, most important first."""
    concern_set = set(concerns)
    actions: list[dict[str, Any]] = []

    if roster_unverified:
        actions.append(
            {
                "label": "re-verify candidate roster first",
                "steps": ["discovery"],
                "baseline": "published",
                "note": "",
            }
        )

    if concern_set & {"issues", "finance"}:
        actions.append(
            {
                "label": "combined issues run",
                "steps": COMBINED_STEPS,
                "baseline": "latest" if has_draft else "published",
                "note": "",
            }
        )
    elif "roster" in concern_set and not roster_unverified:
        actions.append(
            {
                "label": "roster re-verification",
                "steps": ["discovery"],
                "baseline": "published",
                "note": "",
            }
        )

    # Forecast is already included in COMBINED_STEPS if issues or finance is queued
    if "forecast" in concern_set and not (concern_set & {"issues", "finance"}):
        actions.append({"label": "targeted forecast re-run", "steps": ["forecast"], "baseline": "latest", "note": ""})

    if "images" in concern_set:
        actions.append({"label": "image refresh", "steps": ["images"], "baseline": "latest", "note": ""})

    return actions


def build_triage_comment(issue: dict[str, Any], race_id: str, record: dict[str, Any] | None) -> str:
    """Compose an ultra-compact triage verdict comment without emojis."""
    lines = [f"### Triage: `{race_id}`", ""]

    if record is None:
        is_request = issue["title"].startswith("[Race Request]")
        status = "new race request" if is_request else "not in catalog"
        lines += [f"`{race_id}` is **{status}**.", "", NOTIFY_HANDLE]
        return "\n".join(lines)

    health = record.get("catalog_health") or {}
    gaps = health.get("gaps") or []
    reported_name = extract_field(issue.get("body", ""), "Candidate Name")

    grade = record.get("quality_grade") or "none"
    count = record.get("candidate_count", 0)
    lines += [f"**{record.get('title', race_id)}** (Grade `{grade}`, {count} candidates)", ""]

    roster_needs_work = False
    if reported_name:
        candidate = find_candidate(record, reported_name)
        if candidate is None:
            roster_needs_work = True
            lines += [f"Candidate **{reported_name}** is not in roster.", ""]

    if record.get("draft_exists"):
        lines += ["A run has been completed and is pending review.", ""]

    concerns = reported_concerns(issue.get("body", ""))
    concerns |= {GAP_CONCERNS[gap] for gap in gaps if gap in GAP_CONCERNS}
    actions = recommend(concerns, roster_needs_work, bool(record.get("draft_exists")))

    if not actions:
        lines += ["No pipeline work indicated.", ""]
    else:
        for action in actions:
            cmd = (
                f'queue_races(race_ids=["{race_id}"], enabled_steps={json.dumps(action["steps"])}, '
                f'baseline_source="{action["baseline"]}")'
            )
            lines += ["```", cmd, "```", ""]

    lines += [NOTIFY_HANDLE]
    return "\n".join(lines)


def build_draft_ready_comment(race_id: str, record: dict[str, Any]) -> str:
    """Compose the follow-up comment announcing a publishable draft."""
    draft_health = record.get("draft_catalog_health") or {}
    return "\n".join(
        [
            f"### Draft ready: `{race_id}`",
            "",
            f"A draft for **{record.get('title', race_id)}** passes validation "
            f"(Grade `{draft_health.get('validation_grade') or 'none'}`, "
            f"{draft_health.get('candidate_count', 0)} candidates).",
            "",
            "```",
            f'publish_race(race_id="{race_id}")',
            "```",
            "",
            f"{NOTIFY_HANDLE} — publishing remains a manual action.",
        ]
    )


def is_race_issue(issue: dict[str, Any]) -> bool:
    """Match issues produced by the missing-data or race-request templates."""
    labels = {label["name"] for label in issue.get("labels", [])}
    if labels & RACE_ISSUE_LABELS:
        return True
    return issue["title"].startswith(RACE_ISSUE_TITLE_PREFIXES)


def resolve_race_id(issue: dict[str, Any]) -> str:
    """Extract and validate the Race ID field from an issue body.

    The race-request template labels the field "Proposed Race ID" while missing-data uses
    "Race ID"; issues filed before that split use "Race ID" for both.
    """
    body = issue.get("body", "")
    raw = extract_field(body, "Race ID") or extract_field(body, "Proposed Race ID")
    race_id = raw.strip().strip("`").lower()
    if not race_id:
        raise TriageError("no Race ID field found in the issue body")
    if not RACE_ID_PATTERN.match(race_id):
        raise TriageError(f"'{race_id}' is not a valid race ID")
    return race_id


def ensure_labels() -> None:
    """Create the labels this workflow and the issue templates depend on."""
    wanted = [
        (TRIAGED_LABEL, "0E8A16", "Automated triage has posted a verdict"),
        (DRAFT_READY_LABEL, "1D76DB", "A publishable draft exists for this race"),
        ("data-request", "D93F0B", "Community report of missing candidate data"),
        ("race-request", "FBCA04", "Community request for new race coverage"),
        ("community-contribution", "5319E7", "Filed via a community issue template"),
    ]
    existing = set(gh("label", "list", "--repo", REPO, "--limit", "200", "--json", "name", "--jq", ".[].name").split("\n"))
    for name, color, description in wanted:
        if name not in existing:
            gh("label", "create", name, "--repo", REPO, "--color", color, "--description", description, check=False)


def post(issue_number: int, body: str, label: str, dry_run: bool) -> None:
    """Comment on an issue and apply the state label, unless this is a dry run."""
    if dry_run:
        print(f"[dry-run] would comment on #{issue_number} and add '{label}':\n{body}\n{'-' * 60}")
        return
    gh("issue", "comment", str(issue_number), "--repo", REPO, "--body", body)
    gh("issue", "edit", str(issue_number), "--repo", REPO, "--add-label", label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print comments instead of posting them")
    args = parser.parse_args()

    # Comments contain emoji; a cp1252 console (Windows dry runs) would otherwise crash on print.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if not ADMIN_KEY:
        raise SystemExit("ADMIN_API_KEY is not set")

    if not args.dry_run:
        ensure_labels()

    raw = gh(
        "issue",
        "list",
        "--repo",
        REPO,
        "--state",
        "open",
        "--limit",
        "100",
        "--json",
        "number,title,body,labels",
    )
    issues = [issue for issue in json.loads(raw or "[]") if is_race_issue(issue)]

    summary: list[str] = ["# Race issue triage", ""]
    triaged = ready = skipped = failed = 0

    for issue in issues:
        number = issue["number"]
        labels = {label["name"] for label in issue.get("labels", [])}
        needs_triage = TRIAGED_LABEL not in labels
        needs_draft_check = TRIAGED_LABEL in labels and DRAFT_READY_LABEL not in labels

        if not needs_triage and not needs_draft_check:
            skipped += 1
            continue

        try:
            race_id = resolve_race_id(issue)
            record = fetch_race_record(race_id)

            if needs_triage:
                post(number, build_triage_comment(issue, race_id, record), TRIAGED_LABEL, args.dry_run)
                triaged += 1
                summary.append(f"- Triaged #{number} (`{race_id}`)")
                continue

            draft_health = (record or {}).get("draft_catalog_health") or {}
            if record and record.get("draft_exists") and draft_health.get("validation_passed"):
                post(number, build_draft_ready_comment(race_id, record), DRAFT_READY_LABEL, args.dry_run)
                ready += 1
                summary.append(f"- **Publishable draft** for #{number} (`{race_id}`)")
            else:
                skipped += 1
        except TriageError as exc:
            failed += 1
            summary.append(f"- ⚠️ #{number}: {exc}")
        except Exception as exc:  # keep one broken issue from killing the whole run
            failed += 1
            summary.append(f"- ⚠️ #{number}: unexpected error: {exc}")

    summary.insert(1, f"Triaged {triaged} · publishable drafts {ready} · skipped {skipped} · errors {failed}")
    summary.append("")
    summary.append("No pipeline runs were queued; this job never spends LLM or search credits.")

    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(summary) + "\n")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
