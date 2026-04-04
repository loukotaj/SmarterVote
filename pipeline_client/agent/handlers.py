"""Editing tool handler factory for tools-mode agent phases.

``_make_editing_handlers(race_json, log)`` returns a dict of handler
functions keyed by tool name.  Each handler closes over *race_json*,
mutates it in-place, and returns a short confirmation string that the
LLM receives as the tool result.
"""

import json
from typing import Any, Callable, Dict, Optional


def _make_editing_handlers(
    race_json: Dict[str, Any], log: Callable
) -> Dict[str, Any]:
    """Build editing-tool handlers closed over *race_json*.

    Returns a ``{tool_name: handler_fn}`` dict compatible with the
    ``extra_tool_handlers`` parameter of ``_agent_loop``.
    """
    _ALLOWED_CANDIDATE_FIELDS = {"party", "incumbent", "website", "image_url"}
    _ALLOWED_RACE_FIELDS = {"description", "office", "election_date", "polling_note"}

    def _find_candidate(name: str) -> Optional[Dict[str, Any]]:
        for c in race_json.get("candidates", []):
            if c.get("name") == name:
                return c
        return None

    # --- Roster handlers ---

    def add_candidate(args: Dict[str, Any]) -> str:
        name = args["name"]
        if _find_candidate(name):
            return f"Candidate '{name}' already exists — skipping."
        candidate = {
            "name": name,
            "party": args.get("party", ""),
            "incumbent": args.get("incumbent", False),
            "summary": "",
            "summary_sources": [],
            "image_url": None,
            "website": None,
            "social_media": {},
            "career_history": [],
            "education": [],
            "donor_summary": None,
            "donor_source_url": None,
            "voting_summary": None,
            "voting_source_url": None,
            "links": [],
            "issues": {},
        }
        race_json.setdefault("candidates", []).append(candidate)
        log("info", f"    ✅ Added candidate: {name} ({args.get('party', '?')})")
        return f"Added candidate '{name}'."

    def remove_candidate(args: Dict[str, Any]) -> str:
        name = args["name"]
        reason = args.get("reason", "").strip()

        # Guard: reject removals that are clearly data-quality fixes rather than
        # actual race withdrawals. Withdrawal reasons must mention the race exit.
        _WITHDRAWAL_KEYWORDS = {
            "withdrew", "withdrawal", "dropped out", "drop out", "suspended",
            "disqualified", "disqualification", "ended campaign", "exited race",
            "no longer running", "not running", "retired from race", "lost primary",
            "primary loss",
        }
        reason_lower = reason.lower()
        has_withdrawal_signal = any(kw in reason_lower for kw in _WITHDRAWAL_KEYWORDS)

        # Also reject if reason sounds like a data-quality fix
        _DATA_FIX_KEYWORDS = {
            "fabricated", "incorrect", "wrong", "replace", "fix", "error",
            "bad data", "inaccurate", "verified", "update", "correction",
        }
        has_data_fix_signal = any(kw in reason_lower for kw in _DATA_FIX_KEYWORDS)

        if has_data_fix_signal or (reason and not has_withdrawal_signal):
            log(
                "warning",
                f"    ⚠️ remove_candidate('{name}') BLOCKED — reason does not confirm "
                f"a race withdrawal: {reason!r}. Use this tool only when a candidate "
                f"has officially left the race.",
            )
            return (
                f"ERROR: remove_candidate blocked. The reason '{reason}' does not indicate "
                f"that '{name}' has withdrawn from the race. Only call remove_candidate when "
                f"a candidate has officially withdrawn, dropped out, or been disqualified. "
                f"Do NOT use this tool to fix data quality issues."
            )

        candidates = race_json.get("candidates", [])
        for i, c in enumerate(candidates):
            if c.get("name") == name:
                candidates.pop(i)
                log("info", f"    ❌ Removed candidate: {name} ({reason or 'no reason given'})")
                return f"Removed candidate '{name}' ({reason or 'no reason given'})."
        return f"Candidate '{name}' not found — no action taken."

    def rename_candidate(args: Dict[str, Any]) -> str:
        old_name, new_name = args["old_name"], args["new_name"]
        c = _find_candidate(old_name)
        if not c:
            return f"Candidate '{old_name}' not found."
        c["name"] = new_name
        log("info", f"    📝 Renamed: {old_name} → {new_name}")
        return f"Renamed '{old_name}' to '{new_name}'."

    # --- Candidate field handlers ---

    def set_candidate_field(args: Dict[str, Any]) -> str:
        name, field, value = args["candidate_name"], args["field"], args["value"]
        if field not in _ALLOWED_CANDIDATE_FIELDS:
            return f"Field '{field}' not allowed. Allowed: {', '.join(sorted(_ALLOWED_CANDIDATE_FIELDS))}."
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c[field] = value
        log("info", f"    📝 {name}.{field} = {value!r}")
        return f"Set {name}.{field} = {value!r}."

    def set_candidate_summary(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["summary"] = args["summary"]
        if args.get("sources"):
            c["summary_sources"] = args["sources"]
        log("info", f"    📝 Updated summary for {name}")
        return f"Updated summary for '{name}'."

    # --- Issue handler ---

    def set_issue_stance(args: Dict[str, Any]) -> str:
        name, issue = args["candidate_name"], args["issue"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        stance_data: Dict[str, Any] = {
            "stance": args["stance"],
            "confidence": args["confidence"],
        }
        if args.get("sources"):
            stance_data["sources"] = args["sources"]
        c.setdefault("issues", {})[issue] = stance_data
        log("info", f"    📝 {name} / {issue} [{args['confidence']}]")
        return f"Set {name}'s {issue} stance (confidence: {args['confidence']})."

    # --- Career, education, social media handlers ---

    def add_career_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        entry = {
            "title": args["title"],
            "organization": args["organization"],
            "start_year": args.get("start_year"),
            "end_year": args.get("end_year"),
            "description": args.get("description", ""),
        }
        c.setdefault("career_history", []).append(entry)
        log("info", f"    📝 Added career entry for {name}: {args['title']} at {args['organization']}")
        return f"Added career entry for '{name}': {args['title']} at {args['organization']}."

    def add_education_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        entry = {
            "institution": args["institution"],
            "degree": args["degree"],
            "field": args.get("field"),
            "year": args.get("year"),
        }
        c.setdefault("education", []).append(entry)
        log("info", f"    📝 Added education for {name}: {args['degree']} from {args['institution']}")
        return f"Added education for '{name}': {args['degree']} from {args['institution']}."

    def set_social_media(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        platform = args["platform"].lower()
        c.setdefault("social_media", {})[platform] = args["url"]
        log("info", f"    📝 {name}.social_media.{platform} = {args['url']}")
        return f"Set {name}'s {platform} to {args['url']}."

    def remove_career_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        org = args["organization"].lower()
        before = len(c.get("career_history", []))
        c["career_history"] = [e for e in c.get("career_history", []) if org not in e.get("organization", "").lower()]
        removed = before - len(c["career_history"])
        log("info", f"    🗑️ Removed {removed} career entry/entries matching '{args['organization']}' for {name}")
        return f"Removed {removed} career entry/entries matching '{args['organization']}' for '{name}'."

    def update_career_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        org = args["organization"].lower()
        matched = [e for e in c.get("career_history", []) if org in e.get("organization", "").lower()]
        if not matched:
            return f"No career entry matching '{args['organization']}' found for '{name}'."
        for entry in matched:
            for field in ("title", "start_year", "end_year", "description"):
                if field in args:
                    entry[field] = args[field]
        changes = {k: v for k, v in args.items() if k not in ("candidate_name", "organization")}
        log("info", f"    ✏️ Updated career entry '{args['organization']}' for {name}: {changes}")
        return f"Updated {len(matched)} career entry/entries for '{name}' matching '{args['organization']}'."

    def update_education_entry(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        inst = args["institution"].lower()
        matched = [e for e in c.get("education", []) if inst in e.get("institution", "").lower()]
        if not matched:
            return f"No education entry matching '{args['institution']}' found for '{name}'."
        for entry in matched:
            for field in ("degree", "field", "year"):
                if field in args:
                    entry[field] = args[field]
        changes = {k: v for k, v in args.items() if k not in ("candidate_name", "institution")}
        log("info", f"    ✏️ Updated education entry '{args['institution']}' for {name}: {changes}")
        return f"Updated {len(matched)} education entry/entries for '{name}' matching '{args['institution']}'."

    def clear_career_history(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["career_history"] = []
        log("info", f"    🗑️ Cleared career_history for {name}")
        return f"Cleared career_history for '{name}'. Use add_career_entry to add correct entries."

    def clear_education(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["education"] = []
        log("info", f"    🗑️ Cleared education for {name}")
        return f"Cleared education for '{name}'. Use add_education_entry to add correct entries."

    # --- Record handlers (summary setters) ---

    def set_donor_summary(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["donor_summary"] = args["summary"]
        if args.get("source_url"):
            c["donor_source_url"] = args["source_url"]
        log("info", f"    📝 Updated donor summary for {name}")
        return f"Updated donor summary for '{name}'."

    def set_voting_summary(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["voting_summary"] = args["summary"]
        if args.get("source_url"):
            c["voting_source_url"] = args["source_url"]
        log("info", f"    📝 Updated voting summary for {name}")
        return f"Updated voting summary for '{name}'."

    def add_candidate_link(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        url = args["url"]
        existing_urls = {lnk.get("url") for lnk in c.get("links", [])}
        if url in existing_urls:
            return f"Link already exists for '{name}': {url}"
        c.setdefault("links", []).append({
            "url": url,
            "title": args["title"],
            "type": args.get("type", "other"),
        })
        log("info", f"    🔗 Added link for {name}: {url[:60]}")
        return f"Added {args.get('type', 'other')} link for '{name}'."

    # --- Race-level handlers ---

    def add_poll(args: Dict[str, Any]) -> str:
        poll = {
            "pollster": args["pollster"],
            "date": args["date"],
            "matchups": args["matchups"],
            "source_url": args["source_url"],
        }
        if args.get("sample_size"):
            poll["sample_size"] = args["sample_size"]
        race_json.setdefault("polling", []).insert(0, poll)
        log("info", f"    📊 Added poll: {args['pollster']} ({args['date']})")
        return f"Added poll from {args['pollster']} ({args['date']})."

    def update_race_field(args: Dict[str, Any]) -> str:
        field, value = args["field"], args["value"]
        if field not in _ALLOWED_RACE_FIELDS:
            return f"Field '{field}' not allowed. Allowed: {', '.join(sorted(_ALLOWED_RACE_FIELDS))}."
        race_json[field] = value
        log("info", f"    📝 race.{field} updated")
        return f"Updated race.{field}."

    # --- Read-only verification handler ---

    def read_profile(args: Dict[str, Any]) -> str:
        section = args.get("section", "full")
        if section == "full":
            return json.dumps(race_json, indent=2, default=str)[:16000]
        if section == "candidates":
            return json.dumps(race_json.get("candidates", []), indent=2, default=str)[:16000]
        if section == "issues":
            compact = {}
            for c in race_json.get("candidates", []):
                issues = {}
                for k, v in c.get("issues", {}).items():
                    if isinstance(v, dict):
                        issues[k] = {
                            "stance": v.get("stance", "")[:80],
                            "confidence": v.get("confidence", "?"),
                        }
                compact[c.get("name", "?")] = issues
            return json.dumps(compact, indent=2)
        if section == "polling":
            return json.dumps(race_json.get("polling", []), indent=2, default=str)[:8000]
        if section == "meta":
            return json.dumps(
                {k: race_json.get(k) for k in
                 ("id", "title", "office", "jurisdiction", "election_date", "description")
                 if k in race_json},
                indent=2,
                default=str,
            )
        return f"Unknown section '{section}'."

    return {
        "add_candidate": add_candidate,
        "remove_candidate": remove_candidate,
        "rename_candidate": rename_candidate,
        "set_candidate_field": set_candidate_field,
        "set_candidate_summary": set_candidate_summary,
        "set_issue_stance": set_issue_stance,
        "set_donor_summary": set_donor_summary,
        "set_voting_summary": set_voting_summary,
        "add_candidate_link": add_candidate_link,
        "add_poll": add_poll,
        "update_race_field": update_race_field,
        "read_profile": read_profile,
        "add_career_entry": add_career_entry,
        "remove_career_entry": remove_career_entry,
        "update_career_entry": update_career_entry,
        "add_education_entry": add_education_entry,
        "update_education_entry": update_education_entry,
        "set_social_media": set_social_media,
        "clear_career_history": clear_career_history,
        "clear_education": clear_education,
    }
