"""Pipeline V2 agent: multi-phase candidate research with web search & caching.

Phases:
1. **Discovery** – identify the race and candidates via web search.
2. **Issue research** – one focused call per issue group (6 calls).
3. **Refinement** – merge, clean, and improve the full profile.

Supports **rerun/update** mode: pass an existing RaceJSON and the agent
will search for new developments and improve the profile.

Uses a SQLite search cache (``pipeline.app.utils.search_cache``) to avoid
redundant Serper API calls across runs.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .prompts import (
    CANONICAL_ISSUES,
    DISCOVERY_SYSTEM,
    DISCOVERY_USER,
    ISSUE_GROUPS,
    ISSUE_RESEARCH_SYSTEM,
    ISSUE_RESEARCH_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    UPDATE_SYSTEM,
    UPDATE_USER,
)

logger = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Web search tool definition for OpenAI function calling
# ---------------------------------------------------------------------------

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information about candidates, "
            "elections, and political positions. Returns a list of search "
            "results with titles, snippets, and URLs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to execute.",
                }
            },
            "required": ["query"],
        },
    },
}


# ---------------------------------------------------------------------------
# Search cache helpers
# ---------------------------------------------------------------------------

_search_cache = None


def _get_search_cache():
    """Lazy-init the shared search cache singleton."""
    global _search_cache
    if _search_cache is None:
        try:
            from pipeline.app.utils.search_cache import SearchCache

            _search_cache = SearchCache()
        except Exception:
            # If the v1 cache module isn't available, disable caching
            _search_cache = False
    return _search_cache if _search_cache else None


# ---------------------------------------------------------------------------
# Serper web search implementation (with caching)
# ---------------------------------------------------------------------------


async def _serper_search(
    query: str, *, num_results: int = 8, race_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Execute a web search via the Serper API, with caching."""
    # Check cache first
    cache = _get_search_cache()
    if cache:
        cached = cache.get(query, race_id)
        if cached:
            logger.debug(f"Search cache HIT: {query[:60]}")
            return cached["results"]

    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return [{"error": "SERPER_API_KEY not configured"}]

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num_results},
        )
        resp.raise_for_status()
        data = resp.json()

    results: List[Dict[str, Any]] = []
    for item in data.get("organic", []):
        results.append(
            {
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "url": item.get("link", ""),
            }
        )

    # Include knowledge graph if present
    kg = data.get("knowledgeGraph")
    if kg:
        results.insert(
            0,
            {
                "title": kg.get("title", ""),
                "snippet": kg.get("description", ""),
                "url": kg.get("website", kg.get("descriptionLink", "")),
                "type": "knowledge_graph",
            },
        )

    # Store in cache
    if cache:
        cache.set(query, results, race_id=race_id, provider="serper")

    return results


# ---------------------------------------------------------------------------
# OpenAI helpers
# ---------------------------------------------------------------------------


async def _call_openai(
    messages: List[Dict[str, Any]],
    *,
    model: str,
    tools: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Call the OpenAI Chat Completions API."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM output, handling markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Generic agent loop used by each phase
# ---------------------------------------------------------------------------


async def _agent_loop(
    system: str,
    user: str,
    *,
    model: str,
    on_log: Any | None = None,
    race_id: Optional[str] = None,
    max_iterations: int = 15,
    phase_name: str = "",
) -> Dict[str, Any]:
    """Run a single agent loop (search → answer → parse JSON)."""

    def log(level: str, msg: str) -> None:
        logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    for iteration in range(max_iterations):
        log("info", f"  [{phase_name}] iteration {iteration + 1}/{max_iterations}")

        result = await _call_openai(messages, model=model, tools=[SEARCH_TOOL])
        choice = result["choices"][0]
        message = choice["message"]

        # If the model wants to call tools, execute them
        if message.get("tool_calls"):
            messages.append(message)
            for tool_call in message["tool_calls"]:
                fn = tool_call["function"]
                if fn["name"] == "web_search":
                    args = json.loads(fn["arguments"])
                    query = args.get("query", "")
                    log("info", f"    🔍 {query}")
                    search_results = await _serper_search(
                        query, race_id=race_id
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(search_results),
                        }
                    )
            continue

        # No tool calls – parse the answer
        content = message.get("content", "")
        try:
            return _extract_json(content)
        except (json.JSONDecodeError, ValueError) as exc:
            log("warning", f"  [{phase_name}] bad JSON: {exc}")
            messages.append(message)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your response was not valid JSON. Please return ONLY "
                        "the JSON object with no markdown fences or extra text."
                    ),
                }
            )
            continue

    raise RuntimeError(f"[{phase_name}] did not produce output within {max_iterations} iterations")


# ---------------------------------------------------------------------------
# Load existing published data for rerun/update mode
# ---------------------------------------------------------------------------


def _load_existing(race_id: str) -> Optional[Dict[str, Any]]:
    """Load an existing published RaceJSON if it exists."""
    published_dir = Path(__file__).resolve().parents[1] / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_agent(
    race_id: str,
    *,
    on_log: Any | None = None,
    cheap_mode: bool = True,
    max_iterations: int = 15,
    existing_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the multi-phase research agent for a given race_id.

    Parameters
    ----------
    race_id : str
        Race slug, e.g. ``"mo-senate-2024"``.
    on_log : callable, optional
        ``(level, message) -> None`` callback for streaming logs.
    cheap_mode : bool
        When *True*, use ``gpt-4o-mini``; otherwise ``gpt-4o``.
    max_iterations : int
        Safety limit on each phase's tool-call loop.
    existing_data : dict, optional
        An existing RaceJSON to update/improve. If *None*, the agent
        will check ``data/published/{race_id}.json`` automatically.

    Returns
    -------
    dict
        The completed RaceJSON output.
    """

    model = "gpt-4o-mini" if cheap_mode else "gpt-4o"

    def log(level: str, msg: str) -> None:
        logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)

    t0 = time.perf_counter()

    # Check for existing data (rerun mode)
    if existing_data is None:
        existing_data = _load_existing(race_id)

    if existing_data:
        log("info", f"🔄 Update mode for {race_id} (model={model})")
        race_json = await _run_update(
            race_id,
            existing_data,
            model=model,
            on_log=on_log,
            max_iterations=max_iterations,
        )
    else:
        log("info", f"🆕 New research for {race_id} (model={model})")
        race_json = await _run_fresh(
            race_id,
            model=model,
            on_log=on_log,
            max_iterations=max_iterations,
        )

    # Normalise the output
    race_json.setdefault("id", race_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    race_json["updated_utc"] = now_iso  # Always update timestamp
    race_json.setdefault("generator", ["pipeline-v2-agent"])

    # Add last_accessed timestamps to sources that lack them
    for candidate in race_json.get("candidates", []):
        for issue_data in candidate.get("issues", {}).values():
            if isinstance(issue_data, dict):
                for src in issue_data.get("sources", []):
                    if isinstance(src, dict):
                        src.setdefault("last_accessed", now_iso)

    elapsed = time.perf_counter() - t0
    log("info", f"✅ Agent finished in {elapsed:.1f}s")
    return race_json


# ---------------------------------------------------------------------------
# Fresh run (new race)
# ---------------------------------------------------------------------------


async def _run_fresh(
    race_id: str,
    *,
    model: str,
    on_log: Any | None = None,
    max_iterations: int = 15,
) -> Dict[str, Any]:
    """Phase 1 → 2 → 3: Discovery → Issue research → Refinement."""

    def log(level: str, msg: str) -> None:
        logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)

    # --- Phase 1: Discovery ---
    log("info", "Phase 1/3: Discovering race and candidates...")
    race_json = await _agent_loop(
        DISCOVERY_SYSTEM,
        DISCOVERY_USER.format(race_id=race_id),
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=max_iterations,
        phase_name="discovery",
    )

    candidate_names = [c["name"] for c in race_json.get("candidates", [])]
    if not candidate_names:
        log("warning", "No candidates found in discovery phase")
        return race_json

    # --- Phase 2: Issue research (one call per group) ---
    log("info", f"Phase 2/3: Researching issues for {len(candidate_names)} candidates...")
    all_issues: Dict[str, Dict[str, Any]] = {name: {} for name in candidate_names}

    for group_idx, issues in enumerate(ISSUE_GROUPS):
        log("info", f"  Issue group {group_idx + 1}/{len(ISSUE_GROUPS)}: {', '.join(issues)}")
        issues_result = await _agent_loop(
            ISSUE_RESEARCH_SYSTEM,
            ISSUE_RESEARCH_USER.format(
                race_id=race_id,
                candidate_names=", ".join(candidate_names),
                issues_list="\n".join(f"  - {i}" for i in issues),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
            phase_name=f"issues-{group_idx + 1}",
        )

        # Merge issue results into per-candidate map
        for cand_name, cand_issues in issues_result.items():
            if cand_name in all_issues and isinstance(cand_issues, dict):
                all_issues[cand_name].update(cand_issues)

    # Merge issues into the race JSON
    for candidate in race_json.get("candidates", []):
        name = candidate["name"]
        if name in all_issues:
            candidate.setdefault("issues", {}).update(all_issues[name])

    # --- Phase 3: Refinement ---
    log("info", "Phase 3/3: Refining and improving profile...")
    race_json = await _agent_loop(
        REFINE_SYSTEM,
        REFINE_USER.format(
            race_id=race_id,
            draft_json=json.dumps(race_json, indent=2, default=str),
            all_issues=", ".join(CANONICAL_ISSUES),
        ),
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=max_iterations,
        phase_name="refine",
    )

    return race_json


# ---------------------------------------------------------------------------
# Update run (existing race)
# ---------------------------------------------------------------------------


async def _run_update(
    race_id: str,
    existing: Dict[str, Any],
    *,
    model: str,
    on_log: Any | None = None,
    max_iterations: int = 15,
) -> Dict[str, Any]:
    """Run an update/rerun pass on an existing profile."""

    last_updated = existing.get("updated_utc", "unknown")
    return await _agent_loop(
        UPDATE_SYSTEM,
        UPDATE_USER.format(
            race_id=race_id,
            existing_json=json.dumps(existing, indent=2, default=str),
            last_updated=last_updated,
        ),
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=max_iterations,
        phase_name="update",
    )
