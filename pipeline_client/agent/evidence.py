"""Helpers for preserving cited evidence across incremental profile updates."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List

SOURCE_LIST_FIELDS = ("roster_sources", "summary_sources", "donor_sources", "voting_sources")


def _source_identity(source: Any) -> str:
    if isinstance(source, dict):
        return str(source.get("url") or "").strip()
    return str(source or "").strip()


def merge_source_lists(current: Any, previous: Any) -> List[Any]:
    """Return current evidence followed by any previously cited unique sources."""
    merged: List[Any] = []
    seen: set[str] = set()
    for source in _iter_sources(current, previous):
        identity = _source_identity(source)
        if not identity or identity in seen:
            continue
        merged.append(copy.deepcopy(source))
        seen.add(identity)
    return merged


def _iter_sources(*values: Any) -> Iterable[Any]:
    for value in values:
        if isinstance(value, list):
            yield from value


def preserve_baseline_evidence(race_json: Dict[str, Any], baseline: Any) -> int:
    """Restore source citations omitted by an incremental update.

    Agents may explicitly remove obsolete URLs with ``remove_candidate_source_url``.
    Ordinary field and issue updates are otherwise monotonic: omission is not
    interpreted as an instruction to discard existing evidence.
    """
    if not isinstance(baseline, dict):
        return 0

    baseline_candidates = {
        str(candidate.get("name") or "").strip().casefold(): candidate
        for candidate in baseline.get("candidates") or []
        if isinstance(candidate, dict) and str(candidate.get("name") or "").strip()
    }
    removed_by_candidate: Dict[str, set[str]] = {}
    pipeline_state = race_json.get("pipeline_state")
    if isinstance(pipeline_state, dict):
        for removal in pipeline_state.get("removed_source_urls") or []:
            if not isinstance(removal, dict):
                continue
            candidate_key = str(removal.get("candidate_name") or "").strip().casefold()
            url = str(removal.get("url") or "").strip()
            if candidate_key and url:
                removed_by_candidate.setdefault(candidate_key, set()).add(url)

    restored = 0
    for candidate in race_json.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        candidate_key = str(candidate.get("name") or "").strip().casefold()
        previous = baseline_candidates.get(candidate_key)
        if not isinstance(previous, dict):
            continue
        removed_urls = removed_by_candidate.get(candidate_key, set())

        for field in SOURCE_LIST_FIELDS:
            before = len(candidate.get(field) or []) if isinstance(candidate.get(field), list) else 0
            merged = [
                source
                for source in merge_source_lists(candidate.get(field), previous.get(field))
                if _source_identity(source) not in removed_urls
            ]
            if merged:
                candidate[field] = merged
            elif field in candidate:
                candidate[field] = []
            restored += max(0, len(merged) - before)

        current_issues = candidate.setdefault("issues", {})
        previous_issues = previous.get("issues")
        if not isinstance(current_issues, dict) or not isinstance(previous_issues, dict):
            continue
        for issue_name, previous_issue in previous_issues.items():
            if not isinstance(previous_issue, dict):
                continue
            current_issue = current_issues.get(issue_name)
            if not isinstance(current_issue, dict):
                restored_issue = copy.deepcopy(previous_issue)
                restored_issue["sources"] = [
                    source for source in restored_issue.get("sources") or [] if _source_identity(source) not in removed_urls
                ]
                current_issues[issue_name] = restored_issue
                restored += len(restored_issue["sources"])
                continue
            before = len(current_issue.get("sources") or []) if isinstance(current_issue.get("sources"), list) else 0
            merged = [
                source
                for source in merge_source_lists(current_issue.get("sources"), previous_issue.get("sources"))
                if _source_identity(source) not in removed_urls
            ]
            if merged:
                current_issue["sources"] = merged
            elif "sources" in current_issue:
                current_issue["sources"] = []
            restored += max(0, len(merged) - before)

    return restored
