"""Patch and merge helpers for applying agent results to RaceJSON."""

from typing import Any, Dict, List


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

    patch_candidates = {c["name"]: c for c in patch.get("candidates", []) if isinstance(c, dict)}
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
            candidate["donor_sources"] = pc["donor_sources"]
        if isinstance(pc.get("voting_sources"), list):
            candidate["voting_sources"] = pc["voting_sources"]
    log("info", f"  Meta patch applied — {len(patch_candidates)} candidates updated")


def _apply_issue_patch(race_json: Dict[str, Any], patch: Dict[str, Any], log: Any) -> None:
    """Merge an issue patch into race_json candidates in-place."""
    updated = 0
    candidates_by_name = {c["name"]: c for c in race_json.get("candidates", [])}
    for cand_name, issues in patch.items():
        if not isinstance(issues, dict) or cand_name not in candidates_by_name:
            continue
        candidate = candidates_by_name[cand_name]
        candidate.setdefault("issues", {}).update(issues)
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
        "donor_sources",
        "voting_summary",
        "voting_source_url",
        "voting_sources",
    ):
        if key in patch:
            candidate[key] = patch[key]
    for key in ("summary_sources", "career_history", "education"):
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
        candidate.setdefault("issues", {}).update(new_issues)
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
    candidates_by_name = {c["name"]: c for c in race_json.get("candidates", [])}
    for patch in candidate_patches:
        name = patch.get("name")
        if name and name in candidates_by_name:
            _apply_candidate_patch(candidates_by_name[name], patch, log)
            notes = patch.get("iteration_notes", [])
            if isinstance(notes, list):
                iteration_notes.extend(notes)


def _apply_finance_patch(race_json: Dict[str, Any], patch: Dict[str, Any], log: Any) -> None:
    """Merge finance/voting research results into race_json candidates in-place."""
    candidates_by_name = {c["name"]: c for c in race_json.get("candidates", [])}
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
            candidate["donor_sources"] = data["donor_sources"]
        if data.get("voting_summary"):
            candidate["voting_summary"] = data["voting_summary"]
        if data.get("voting_source_url"):
            candidate["voting_source_url"] = data["voting_source_url"]

        new_links = data.get("links", [])
        if isinstance(new_links, list) and new_links:
            existing_urls = {lnk.get("url") for lnk in candidate.get("links", []) if isinstance(lnk, dict)}
            for lnk in new_links:
                if isinstance(lnk, dict) and lnk.get("url") not in existing_urls:
                    candidate.setdefault("links", []).append(lnk)
                    existing_urls.add(lnk.get("url"))

        updated += 1
    log("info", f"  Finance/voting patch applied — {updated} candidates updated")


def _deduplicate_donors(donors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Kept for backward-compat with any update-run paths that may load old data."""
    best: Dict[str, Dict[str, Any]] = {}
    for d in donors:
        key = d.get("name", "").strip().lower()
        if not key:
            continue
        existing = best.get(key)
        if existing is None:
            best[key] = d
        else:
            new_amt = d.get("amount") or 0
            old_amt = existing.get("amount") or 0
            if new_amt > old_amt:
                best[key] = d
    return list(best.values())
