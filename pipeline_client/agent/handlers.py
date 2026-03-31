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
    _ALLOWED_RACE_FIELDS = {"description", "office", "election_date"}

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
            "voting_record": [],
            "top_donors": [],
            "issues": {},
        }
        race_json.setdefault("candidates", []).append(candidate)
        log("info", f"    ✅ Added candidate: {name} ({args.get('party', '?')})")
        return f"Added candidate '{name}'."

    def remove_candidate(args: Dict[str, Any]) -> str:
        name = args["name"]
        candidates = race_json.get("candidates", [])
        for i, c in enumerate(candidates):
            if c.get("name") == name:
                candidates.pop(i)
                reason = args.get("reason", "no reason given")
                log("info", f"    ❌ Removed candidate: {name} ({reason})")
                return f"Removed candidate '{name}' ({reason})."
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

    # --- Record handlers (bulk replace) ---

    def set_voting_records(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["voting_record"] = args["records"]
        n = len(args["records"])
        log("info", f"    📝 Replaced voting records for {name} ({n} entries)")
        return f"Replaced voting records for '{name}' ({n} entries)."

    def set_donors(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["top_donors"] = args["donors"]
        n = len(args["donors"])
        log("info", f"    📝 Replaced donors for {name} ({n} entries)")
        return f"Replaced donors for '{name}' ({n} entries)."

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
        "set_voting_records": set_voting_records,
        "set_donors": set_donors,
        "add_poll": add_poll,
        "update_race_field": update_race_field,
        "read_profile": read_profile,
    }
