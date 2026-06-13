"""Editing tool handler factory for tools-mode agent phases.

``_make_editing_handlers(race_json, log)`` returns a dict of handler
functions keyed by tool name.  Each handler closes over *race_json*,
mutates it in-place, and returns a short confirmation string that the
LLM receives as the tool result.
"""

import json
import re
from datetime import datetime, timezone
from difflib import get_close_matches
from typing import Any, Callable, Dict, Optional

# Pattern matching metadata field names (snake_case, no spaces) — clearly not human names
_METADATA_KEY_RE = re.compile(r"^[a-z][a-z0-9_]+$")

from pipeline_client.agent.images import _is_valid_image_url
from pipeline_client.agent.prompts import CANONICAL_ISSUES
from pipeline_client.agent.source_types import normalize_source_type

_CANONICAL_ISSUE_SET = set(CANONICAL_ISSUES)


def _normalize_source(source: Any, *, default_type: str = "finance") -> Dict[str, Any] | None:
    """Normalize a lightweight tool-provided source into the shared Source shape."""
    if not isinstance(source, dict) or not source.get("url"):
        return None
    normalized = {
        "url": source["url"],
        "type": normalize_source_type(source.get("type"), url=str(source["url"]), default_type=default_type),
        "last_accessed": source.get("last_accessed") or datetime.now(timezone.utc).isoformat(),
    }
    for key in ("title", "description", "published_at", "checksum", "is_fresh", "is_official_campaign"):
        if source.get(key) is not None:
            normalized[key] = source[key]
    return normalized


def _make_editing_handlers(race_json: Dict[str, Any], log: Callable) -> Dict[str, Any]:
    """Build editing-tool handlers closed over *race_json*.

    Returns a ``{tool_name: handler_fn}`` dict compatible with the
    ``extra_tool_handlers`` parameter of ``_agent_loop``.
    """
    _ALLOWED_CANDIDATE_FIELDS = {"party", "incumbent", "website", "image_url"}
    _ALLOWED_RACE_FIELDS = {
        "description",
        "office",
        "election_date",
        "polling_note",
        "ballotpedia_url",
        "register_to_vote_url",
        "how_to_vote_url",
    }

    def _find_candidate(name: str) -> Optional[Dict[str, Any]]:
        for c in race_json.get("candidates", []):
            if isinstance(c, dict) and c.get("name") == name:
                return c
        return None

    # --- Roster handlers ---

    def add_candidate(args: Dict[str, Any]) -> str:
        name = args["name"]
        _PLACEHOLDER_NAMES = {
            "",
            "unknown",
            "tbd",
            "to be determined",
            "n/a",
            "na",
            "none",
            "dummy",
            "test",
            "placeholder",
            "candidate",
            "sample",
            "example",
            "insert name here",
            "insert candidate name",
            "[candidate name]",
        }
        if name.strip().lower() in _PLACEHOLDER_NAMES or name.strip().startswith("["):
            log("warning", f"    add_candidate('{name}') BLOCKED: placeholder/test name rejected")
            return (
                f"Blocked: '{name}' looks like a placeholder name, not a real candidate. Only add confirmed real candidates."
            )
        if _find_candidate(name):
            return f"Candidate '{name}' already exists — skipping."
        party = str(args.get("party") or "")
        party_key = "democratic" if "democrat" in party.lower() else "republican" if "republican" in party.lower() else ""
        if party_key:
            for existing in race_json.get("candidates", []):
                if not isinstance(existing, dict) or party_key not in str(existing.get("party") or "").lower():
                    continue
                roster_text = " ".join(
                    str(existing.get(field) or "") for field in ("summary", "donor_summary", "voting_summary")
                )
                if re.search(r"\b(?:the )?(?:democratic|republican|gop)?\s*nominee\b", roster_text, re.IGNORECASE):
                    existing_name = existing.get("name") or "existing candidate"
                    log(
                        "warning",
                        f"    add_candidate('{name}') BLOCKED: {existing_name} is already identified "
                        f"as the {party_key.title()} nominee.",
                    )
                    return (
                        f"Blocked adding '{name}': {existing_name} is already the {party_key.title()} nominee. "
                        "Only replace a nominee after a verified withdrawal or disqualification."
                    )
        candidate = {
            "name": name,
            "party": party,
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
        log("info", f"    Added candidate: {name} ({args.get('party', '?')})")
        return f"Added candidate '{name}'."

    def remove_candidate(args: Dict[str, Any]) -> str:
        name = args["name"]
        reason = args.get("reason", "").strip()

        # Guard: reject removals that are clearly data-quality fixes rather than
        # actual race withdrawals. Withdrawal reasons must mention the race exit.
        _WITHDRAWAL_KEYWORDS = {
            "withdrew",
            "withdrawal",
            "dropped out",
            "drop out",
            "suspended",
            "disqualified",
            "disqualification",
            "ended campaign",
            "exited race",
            "no longer running",
            "not running",
            "retired from race",
            "lost primary",
            "primary loss",
        }
        reason_lower = reason.lower()
        has_withdrawal_signal = any(kw in reason_lower for kw in _WITHDRAWAL_KEYWORDS)

        # Also reject if reason sounds like a data-quality fix
        _DATA_FIX_KEYWORDS = {
            "fabricated",
            "incorrect",
            "wrong",
            "replace",
            "fix",
            "error",
            "bad data",
            "inaccurate",
            "verified",
            "update",
            "correction",
        }
        has_data_fix_signal = any(kw in reason_lower for kw in _DATA_FIX_KEYWORDS)

        # Special case: structurally invalid entries (e.g. a metadata key like
        # "updated_utc" accidentally stored as a candidate name) should be
        # physically deleted rather than marked withdrawn.
        is_structural_garbage = bool(_METADATA_KEY_RE.match(name))

        if has_data_fix_signal and not has_withdrawal_signal and not is_structural_garbage:
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

        if is_structural_garbage:
            # Physically delete malformed/non-human entries from the list
            orig_len = len(candidates)
            race_json["candidates"] = [c for c in candidates if not isinstance(c, dict) or c.get("name") != name]
            removed = orig_len - len(race_json["candidates"])
            if removed:
                log("info", f"    🗑️ Deleted malformed candidate entry '{name}' ({removed} removed)")
                return f"Deleted malformed entry '{name}' from candidates list."
            return f"Entry '{name}' not found — no action taken."

        for c in candidates:
            if not isinstance(c, dict):
                continue
            if c.get("name") == name:
                c["withdrawn"] = True
                c["withdrawal_reason"] = reason or None
                log("info", f"    🚪 Marked withdrawn: {name} ({reason or 'no reason given'})")
                return f"Marked candidate '{name}' as withdrawn ({reason or 'no reason given'}). Data preserved; candidate will be hidden from main race view."
        return f"Candidate '{name}' not found — no action taken."

    def rename_candidate(args: Dict[str, Any]) -> str:
        old_name, new_name = args["old_name"], args["new_name"]
        c = _find_candidate(old_name)
        if not c:
            return f"Candidate '{old_name}' not found."
        c["name"] = new_name
        log("info", f"    Renamed: {old_name} -> {new_name}")
        return f"Renamed '{old_name}' to '{new_name}'."

    # --- Candidate field handlers ---

    def set_candidate_field(args: Dict[str, Any]) -> str:
        name, field, value = args["candidate_name"], args["field"], args["value"]
        if field not in _ALLOWED_CANDIDATE_FIELDS:
            return f"Field '{field}' not allowed. Allowed: {', '.join(sorted(_ALLOWED_CANDIDATE_FIELDS))}."
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        if field == "image_url" and value is not None and not _is_valid_image_url(value):
            log("warning", f"    Rejected non-image URL for {name}: {value!r}")
            return f"ERROR: {value!r} is not a direct image URL. " "Use a URL for an image file or set image_url to null."
        c[field] = value
        log("info", f"    {name}.{field} = {value!r}")
        return f"Set {name}.{field} = {value!r}."

    def set_candidate_summary(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["summary"] = args["summary"]
        if args.get("sources"):
            c["summary_sources"] = [
                src for src in (_normalize_source(source, default_type="website") for source in args["sources"]) if src
            ]
        log("info", f"    Updated summary for {name}")
        return f"Updated summary for '{name}'."

    # --- Issue handler ---

    def set_issue_stance(args: Dict[str, Any]) -> str:
        name, issue = args["candidate_name"], args["issue"]
        if issue not in _CANONICAL_ISSUE_SET:
            close = get_close_matches(issue, CANONICAL_ISSUES, n=1, cutoff=0.4)
            hint = f" Did you mean: {close[0]!r}?" if close else f" Valid issues: {', '.join(CANONICAL_ISSUES)}."
            return f"ERROR: '{issue}' is not a canonical issue.{hint}"
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        stance_data: Dict[str, Any] = {
            "stance": args["stance"],
            "confidence": args["confidence"],
        }
        if args.get("sources"):
            stance_data["sources"] = [
                src for src in (_normalize_source(source, default_type="website") for source in args["sources"]) if src
            ]
        c.setdefault("issues", {})[issue] = stance_data
        log("info", f"    {name} / {issue} [{args['confidence']}]")
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
        # Dedup: same org + overlapping years -> skip
        org_lower = args["organization"].lower()
        start = args.get("start_year")
        for existing in c.get("career_history", []):
            same_org = (
                org_lower in existing.get("organization", "").lower() or existing.get("organization", "").lower() in org_lower
            )
            same_start = existing.get("start_year") == start
            if same_org and same_start:
                return f"Career entry for '{args['organization']}' ({start}) already exists for '{name}' — skipping duplicate."
        c.setdefault("career_history", []).append(entry)
        log("info", f"    Added career entry for {name}: {args['title']} at {args['organization']}")
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
        # Dedup: same institution + degree -> skip
        inst_lower = args["institution"].lower()
        deg_lower = args["degree"].lower()
        for existing in c.get("education", []):
            if inst_lower in existing.get("institution", "").lower() and deg_lower in existing.get("degree", "").lower():
                return f"Education entry for '{args['institution']}' ({args['degree']}) already exists for '{name}' — skipping duplicate."
        c.setdefault("education", []).append(entry)
        log("info", f"    Added education for {name}: {args['degree']} from {args['institution']}")
        return f"Added education for '{name}': {args['degree']} from {args['institution']}."

    def set_social_media(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        platform = args["platform"].lower()
        c.setdefault("social_media", {})[platform] = args["url"]
        log("info", f"    {name}.social_media.{platform} = {args['url']}")
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
        if isinstance(args.get("sources"), list):
            c["donor_sources"] = [src for src in (_normalize_source(s) for s in args["sources"]) if src]
        log("info", f"    Updated donor summary for {name}")
        return f"Updated donor summary for '{name}'."

    def set_voting_summary(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        c["voting_summary"] = args["summary"]
        if args.get("source_url"):
            c["voting_source_url"] = args["source_url"]
        if isinstance(args.get("sources"), list):
            c["voting_sources"] = [src for src in (_normalize_source(s) for s in args["sources"]) if src]
        log("info", f"    Updated voting summary for {name}")
        return f"Updated voting summary for '{name}'."

    def add_candidate_link(args: Dict[str, Any]) -> str:
        name = args["candidate_name"]
        c = _find_candidate(name)
        if not c:
            return f"Candidate '{name}' not found."
        url = args["url"]
        existing_urls = {lnk.get("url") for lnk in c.get("links", []) if isinstance(lnk, dict)}
        if url in existing_urls:
            return f"Link already exists for '{name}': {url}"
        c.setdefault("links", []).append(
            {
                "url": url,
                "title": args["title"],
                "type": args.get("type", "other"),
            }
        )
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
        # Dedup: same pollster + date
        for existing in race_json.get("polling", []):
            if existing.get("pollster") == args["pollster"] and existing.get("date") == args["date"]:
                return f"Poll from {args['pollster']} ({args['date']}) already exists — skipping duplicate."
        race_json.setdefault("polling", []).insert(0, poll)
        log("info", f"    📊 Added poll: {args['pollster']} ({args['date']})")
        return f"Added poll from {args['pollster']} ({args['date']})."

    def remove_poll(args: Dict[str, Any]) -> str:
        pollster = args["pollster"]
        date = args.get("date")
        reason = args.get("reason", "")
        polling = race_json.get("polling", [])
        orig_len = len(polling)
        if date:
            race_json["polling"] = [p for p in polling if not (p.get("pollster") == pollster and p.get("date") == date)]
            removed = orig_len - len(race_json["polling"])
            if removed:
                log("info", f"    🗑️ Removed poll: {pollster} ({date}) — {reason}")
                return f"Removed {removed} poll(s) from {pollster} ({date})."
            return f"No poll found matching {pollster} / {date} — no action taken."
        else:
            race_json["polling"] = [p for p in polling if p.get("pollster") != pollster]
            removed = orig_len - len(race_json["polling"])
            if removed:
                log("info", f"    🗑️ Removed {removed} poll(s) by '{pollster}' — {reason}")
                return f"Removed {removed} poll(s) from {pollster}."
            return f"No polls found for pollster '{pollster}' — no action taken."

    def update_race_field(args: Dict[str, Any]) -> str:
        field, value = args["field"], args["value"]
        if field not in _ALLOWED_RACE_FIELDS:
            return f"Field '{field}' not allowed. Allowed: {', '.join(sorted(_ALLOWED_RACE_FIELDS))}."
        race_json[field] = value
        log("info", f"    race.{field} updated")
        return f"Updated race.{field}."

    # --- Read-only verification handler ---

    def read_profile(args: Dict[str, Any]) -> str:
        section = args.get("section", "full")
        if section == "full":
            return json.dumps(race_json, indent=2, default=str)
        if section == "candidates":
            return json.dumps(race_json.get("candidates", []), indent=2, default=str)
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
            return json.dumps(race_json.get("polling", []), indent=2, default=str)
        if section == "meta":
            return json.dumps(
                {
                    k: race_json.get(k)
                    for k in ("id", "title", "office", "jurisdiction", "election_date", "description")
                    if k in race_json
                },
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
        "remove_poll": remove_poll,
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
