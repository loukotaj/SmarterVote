"""Patch and merge helpers for applying agent results to RaceJSON."""

from typing import Any, Dict, List

from pipeline_client.agent.evidence import merge_source_lists

_NO_POSITION_MARKERS = ("no public position found",)


def _is_documented_absence(stance: Any) -> bool:
    return any(marker in str(stance or "").casefold() for marker in _NO_POSITION_MARKERS)


def _merge_issue_data(existing: Any, incoming: Any) -> Any:
    """Merge a patch's issue entry over the stored one, keeping cited evidence.

    Refinement and iteration write issues through here rather than through the
    ``set_issue_stance`` tool, which refuses a substantive stance carrying no
    sources. Nothing enforced that rule on this path, so a patch could introduce
    an assertion about a candidate with nothing behind it -- and 32 of the 69
    unsourced substantive stances in the published catalogue have no
    ``research_audit`` at all, meaning they never came from the issues phase.
    This is where they came from.

    A documented absence is still allowed to carry no sources; that is the
    honest outcome when a real search finds nothing.
    """
    if not isinstance(incoming, dict):
        return incoming
    if not isinstance(existing, dict):
        # Nothing stored yet, so there is no evidence to fall back on. Refuse an
        # unsourced assertion rather than creating one.
        if not _is_documented_absence(incoming.get("stance")) and not (incoming.get("sources") or []):
            return None
        return incoming
    merged = dict(existing)
    merged.update(incoming)
    merged["sources"] = merge_source_lists(incoming.get("sources"), existing.get("sources"))
    if not _is_documented_absence(merged.get("stance")) and not merged["sources"]:
        # The rewrite dropped the last citation. Keep what was already stored
        # rather than publishing the new claim unsupported.
        return existing
    return merged


def _apply_meta_patch(race_json: Dict[str, Any], patch: Dict[str, Any], log: Any) -> None:
    if "description" in patch and patch["description"]:
        race_json["description"] = patch["description"]

    if "polling" in patch and isinstance(patch["polling"], list) and patch["polling"]:
        existing_polls = race_json.get("polling", [])
        seen = {(p.get("source"), p.get("date")) for p in existing_polls if isinstance(p, dict)}
        deduped_new = [p for p in patch["polling"] if isinstance(p, dict) and (p.get("source"), p.get("date")) not in seen]
        race_json["polling"] = deduped_new + existing_polls

    if patch.get("polling_note"):
        race_json["polling_note"] = patch["polling_note"]

    patch_candidates = {
        str(c.get("name")).strip(): c
        for c in patch.get("candidates", [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    }
    for candidate in race_json.get("candidates", []):
        name = candidate.get("name")
        pc = patch_candidates.get(name)
        if not pc:
            continue
        if pc.get("summary") is not None:
            candidate["summary"] = pc["summary"]
        if pc.get("donor_summary") is not None:
            candidate["donor_summary"] = pc["donor_summary"]
        if isinstance(pc.get("donor_sources"), list):
            candidate["donor_sources"] = merge_source_lists(pc["donor_sources"], candidate.get("donor_sources"))
        if isinstance(pc.get("voting_sources"), list):
            candidate["voting_sources"] = merge_source_lists(pc["voting_sources"], candidate.get("voting_sources"))
    log("info", f"  Meta patch applied — {len(patch_candidates)} candidates updated")


def _apply_issue_patch(race_json: Dict[str, Any], patch: Dict[str, Any], log: Any) -> None:
    """Merge an issue patch into race_json candidates in-place."""
    updated = 0
    candidates_by_name = {
        str(c.get("name")).strip(): c
        for c in race_json.get("candidates", [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    }
    for cand_name, issues in patch.items():
        if not isinstance(issues, dict) or cand_name not in candidates_by_name:
            continue
        candidate = candidates_by_name[cand_name]
        current_issues = candidate.setdefault("issues", {})
        for issue_name, issue_data in issues.items():
            merged = _merge_issue_data(current_issues.get(issue_name), issue_data)
            if merged is None:
                log("warning", f"  Skipped unsourced {cand_name} / {issue_name} stance from issue patch")
                continue
            current_issues[issue_name] = merged
        updated += 1
    log("info", f"  Issue patch applied — {updated} candidates updated")


def _summarize_existing_stances(candidates: List[Dict[str, Any]], issues: List[str]) -> str:
    """Format existing stances for a set of issues as compact text for the prompt."""
    lines = []
    for c in candidates:
        name = c.get("name", "?")
        for issue in issues:
            stance_data = c.get("issues", {}).get(issue)
            if stance_data and isinstance(stance_data, dict):
                stance = stance_data.get("stance", "")
                conf = stance_data.get("confidence", "low")
                lines.append(f"  {name} / {issue} [{conf}]: {stance[:120]}")
            else:
                lines.append(f"  {name} / {issue}: MISSING")
    return "\n".join(lines) if lines else "  (no existing stances)"


def _apply_candidate_patch(candidate: Dict[str, Any], patch: Dict[str, Any], log: Any) -> None:
    """Merge a per-candidate patch dict into the candidate in-place."""
    cname = candidate.get("name", "?")
    for key in (
        "summary",
        "image_url",
        "website",
        "incumbent",
        "party",
        "donor_summary",
        "donor_source_url",
        "voting_summary",
        "voting_source_url",
    ):
        if key in patch:
            candidate[key] = patch[key]
    for key in ("summary_sources", "donor_sources", "voting_sources"):
        val = patch.get(key)
        if isinstance(val, list):
            candidate[key] = merge_source_lists(val, candidate.get(key))
    for key in ("career_history", "education"):
        val = patch.get(key)
        if isinstance(val, list) and val:
            candidate[key] = val
    new_links = patch.get("links")
    if isinstance(new_links, list) and new_links:
        existing_urls = {lnk.get("url") for lnk in candidate.get("links", []) if isinstance(lnk, dict)}
        for lnk in new_links:
            if isinstance(lnk, dict) and lnk.get("url") not in existing_urls:
                candidate.setdefault("links", []).append(lnk)
                existing_urls.add(lnk.get("url"))
    new_issues = patch.get("issues")
    if isinstance(new_issues, dict) and new_issues:
        current_issues = candidate.setdefault("issues", {})
        for issue_name, issue_data in new_issues.items():
            merged = _merge_issue_data(current_issues.get(issue_name), issue_data)
            if merged is None:
                log("warning", f"  Skipped unsourced {cname} / {issue_name} stance from candidate patch")
                continue
            current_issues[issue_name] = merged
    log("debug", f"  Candidate patch applied for {cname}")


def _apply_refine_patch(
    race_json: Dict[str, Any],
    meta_patch: Dict[str, Any],
    candidate_patches: List[Dict[str, Any]],
    log: Any,
    iteration_notes: List[str],
) -> None:
    """Apply refine meta + per-candidate patches to race_json in-place."""
    if meta_patch.get("description"):
        race_json["description"] = meta_patch["description"]
    if isinstance(meta_patch.get("polling"), list) and meta_patch["polling"]:
        race_json["polling"] = meta_patch["polling"]
    candidates_by_name = {
        str(c.get("name")).strip(): c
        for c in race_json.get("candidates", [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    }
    for patch in candidate_patches:
        name = patch.get("name")
        if name and name in candidates_by_name:
            _apply_candidate_patch(candidates_by_name[name], patch, log)
            notes = patch.get("iteration_notes", [])
            if isinstance(notes, list):
                iteration_notes.extend(notes)


def _apply_finance_patch(race_json: Dict[str, Any], patch: Dict[str, Any], log: Any) -> None:
    """Merge finance/voting research results into race_json candidates in-place."""
    candidates_by_name = {
        str(c.get("name")).strip(): c
        for c in race_json.get("candidates", [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    }
    updated = 0
    for cand_name, data in patch.items():
        if not isinstance(data, dict) or cand_name not in candidates_by_name:
            continue
        candidate = candidates_by_name[cand_name]

        if data.get("donor_summary"):
            candidate["donor_summary"] = data["donor_summary"]
        if data.get("donor_source_url"):
            candidate["donor_source_url"] = data["donor_source_url"]
        if isinstance(data.get("donor_sources"), list):
            candidate["donor_sources"] = merge_source_lists(data["donor_sources"], candidate.get("donor_sources"))
        if data.get("voting_summary"):
            candidate["voting_summary"] = data["voting_summary"]
        if data.get("voting_source_url"):
            candidate["voting_source_url"] = data["voting_source_url"]
        if isinstance(data.get("voting_sources"), list):
            candidate["voting_sources"] = merge_source_lists(data["voting_sources"], candidate.get("voting_sources"))

        new_links = data.get("links", [])
        if isinstance(new_links, list) and new_links:
            existing_urls = {lnk.get("url") for lnk in candidate.get("links", []) if isinstance(lnk, dict)}
            for lnk in new_links:
                if isinstance(lnk, dict) and lnk.get("url") not in existing_urls:
                    candidate.setdefault("links", []).append(lnk)
                    existing_urls.add(lnk.get("url"))

        updated += 1
    log("info", f"  Finance/voting patch applied — {updated} candidates updated")
