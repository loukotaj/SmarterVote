"""Multi-phase candidate research agent with web search & caching.

Phases:
1. **Discovery** – identify the race, candidates, career history, images.
2. **Issue research** – one focused call per issue group (6 calls).
3. **Refinement** – merge, clean, and improve the full profile.
4. **Review** (optional) – send to Claude and/or Gemini for fact-checking.

Supports **rerun/update** mode: pass an existing RaceJSON and the agent
will search for new developments and improve the profile.

Uses a SQLite search cache (``pipeline_client.agent.search_cache``) to avoid
redundant Serper API calls across runs.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .images import resolve_candidate_images
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
from .review import run_reviews
from .utils import _extract_json, make_logger

logger = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Model configuration — defaults & cheap variants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gpt-5.4"
CHEAP_MODEL = "gpt-5.4-mini"

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
# Search cache
# ---------------------------------------------------------------------------


def _get_search_cache():
    """Return the shared SearchCache instance, or None if unavailable."""
    try:
        from pipeline_client.agent.search_cache import get_search_cache
        return get_search_cache()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Serper web search implementation (with caching)
# ---------------------------------------------------------------------------


async def _serper_search(
    query: str, *, num_results: int = 8, race_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Execute a web search via the Serper API, with caching."""
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
        results.append({
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "url": item.get("link", ""),
        })

    kg = data.get("knowledgeGraph")
    if kg:
        results.insert(0, {
            "title": kg.get("title", ""),
            "snippet": kg.get("description", ""),
            "url": kg.get("website", kg.get("descriptionLink", "")),
            "type": "knowledge_graph",
        })

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
    max_retries: int = 5,
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """Call the OpenAI Chat Completions API with retry on transient errors."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_completion_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    # Reuse one client across all retry attempts
    async with httpx.AsyncClient(timeout=300) as client:
        for attempt in range(max_retries):
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code in (429, 500, 502, 503) and attempt < max_retries - 1:
                retry_after = int(resp.headers.get("retry-after", 0))
                wait = max(retry_after, 2 ** (attempt + 1))
                logger.warning(
                    f"OpenAI {resp.status_code}, retrying in {wait}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()


# ---------------------------------------------------------------------------
# Candidate data normalisation
# ---------------------------------------------------------------------------


def _normalize_source(source: Any, now_iso: str) -> None:
    """Apply required defaults to a single source object in-place."""
    if isinstance(source, dict):
        source.setdefault("last_accessed", now_iso)


def _normalize_candidate(candidate: Dict[str, Any], now_iso: str) -> None:
    """Apply output defaults and source normalisation to a candidate."""
    candidate.setdefault("image_url", None)
    candidate.setdefault("career_history", [])
    candidate.setdefault("education", [])
    candidate.setdefault("voting_record", [])
    candidate.setdefault("top_donors", [])

    # Normalise empty string image_url to None
    if candidate.get("image_url") == "":
        candidate["image_url"] = None

    for issue_data in candidate.get("issues", {}).values():
        if isinstance(issue_data, dict):
            for src in issue_data.get("sources", []):
                _normalize_source(src, now_iso)

    for donor in candidate.get("top_donors", []):
        if isinstance(donor, dict):
            _normalize_source(donor.get("source"), now_iso)

    for entry in candidate.get("career_history", []):
        if isinstance(entry, dict):
            _normalize_source(entry.get("source"), now_iso)

    for entry in candidate.get("education", []):
        if isinstance(entry, dict):
            _normalize_source(entry.get("source"), now_iso)

    for entry in candidate.get("voting_record", []):
        if isinstance(entry, dict):
            _normalize_source(entry.get("source"), now_iso)


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
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """Run a single agent loop (search → answer → parse JSON)."""
    log = make_logger(on_log)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    nudge_at = max(max_iterations // 2, 3)

    for iteration in range(max_iterations):
        log("info", f"  [{phase_name}] iteration {iteration + 1}/{max_iterations} — calling {model}...")

        # After half the budget is spent, stop offering the search tool and
        # tell the model to produce its final JSON answer now.
        if iteration == nudge_at and len(messages) > 2:
            messages.append({
                "role": "user",
                "content": (
                    "You have used several searches. Please now compile your findings "
                    "and return ONLY the final JSON response. No more searches."
                ),
            })
            log("info", f"  [{phase_name}] nudging model to produce output (iteration {iteration + 1})")

        tools_for_call = [SEARCH_TOOL] if iteration < nudge_at else None

        t_call = time.perf_counter()
        result = await _call_openai(
            messages, model=model, tools=tools_for_call, max_tokens=max_tokens
        )
        elapsed_call = time.perf_counter() - t_call

        choice = result["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason", "?")
        usage = result.get("usage", {})
        log(
            "info",
            f"  [{phase_name}] response in {elapsed_call:.1f}s — "
            f"finish={finish_reason} "
            f"tokens={usage.get('prompt_tokens', '?')}→{usage.get('completion_tokens', '?')}",
        )

        # If the model wants to call tools, execute them (only when tools were offered)
        if message.get("tool_calls") and tools_for_call:
            messages.append(message)
            for tool_call in message["tool_calls"]:
                fn = tool_call["function"]
                if fn["name"] == "web_search":
                    args = json.loads(fn["arguments"])
                    query = args.get("query", "")
                    log("info", f"    🔍 {query}")
                    search_results = await _serper_search(query, race_id=race_id)
                    log("debug", f"    🔍 got {len(search_results)} results")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(search_results),
                    })
            continue

        # No tool calls — try to parse the answer
        content = message.get("content", "")

        # Response was truncated: ask for a more concise answer
        if finish_reason == "length":
            log("warning", f"  [{phase_name}] response truncated (finish_reason=length) — retrying with brevity prompt")
            messages.append(message)
            messages.append({
                "role": "user",
                "content": (
                    "Your previous response was cut off because it was too long. "
                    "Please return a shorter JSON object. Use concise string values "
                    "(under 200 characters each), omit optional or redundant fields, "
                    "and return ONLY the JSON with no markdown fences or extra text."
                ),
            })
            continue

        try:
            parsed = _extract_json(content)
            log("info", f"  [{phase_name}] JSON parsed OK")
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            log("warning", f"  [{phase_name}] bad JSON ({exc}) — retrying")
            messages.append(message)
            messages.append({
                "role": "user",
                "content": (
                    "Your response was not valid JSON. Please return ONLY "
                    "the JSON object with no markdown fences or extra text."
                ),
            })
            continue

    raise RuntimeError(
        f"[{phase_name}] did not produce output within {max_iterations} iterations"
    )


# ---------------------------------------------------------------------------
# Load existing published data for rerun/update mode
# ---------------------------------------------------------------------------


def _load_existing(race_id: str) -> Optional[Dict[str, Any]]:
    """Load an existing published RaceJSON if it exists."""
    published_dir = Path(__file__).resolve().parents[2] / "data" / "published"
    path = published_dir / f"{race_id}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _scale_iterations(base: int, n_candidates: int, per_candidate: int, minimum: int = 12) -> int:
    """Return an iteration budget scaled to the number of candidates."""
    return max(base, n_candidates * per_candidate + minimum)


async def run_agent(
    race_id: str,
    *,
    on_log: Any | None = None,
    cheap_mode: bool = True,
    max_iterations: int = 20,
    existing_data: Optional[Dict[str, Any]] = None,
    enable_review: bool = False,
    research_model: Optional[str] = None,
    claude_model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    grok_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the multi-phase research agent for a given race_id.

    Parameters
    ----------
    race_id : str
        Race slug, e.g. ``"mo-senate-2024"``.
    on_log : callable, optional
        ``(level, message) -> None`` callback for streaming logs.
    cheap_mode : bool
        When *True*, use cheaper/faster model variants (``gpt-5.4-mini``).
    max_iterations : int
        Safety limit on each phase's tool-call loop.
    existing_data : dict, optional
        An existing RaceJSON to update/improve. When *None* (default),
        the agent checks ``data/published/{race_id}.json`` for a previously
        published profile and enters update mode if found.
        Pass an empty dict to force a fresh research run.
    enable_review : bool
        When *True*, send the final profile to Claude, Gemini, and Grok.
    research_model : str, optional
        Override the OpenAI model for research phases.
    claude_model / gemini_model / grok_model : str, optional
        Override individual review models.
    """
    from .review import (
        DEFAULT_CLAUDE_MODEL, CHEAP_CLAUDE_MODEL,
        DEFAULT_GEMINI_MODEL, CHEAP_GEMINI_MODEL,
        DEFAULT_GROK_MODEL, CHEAP_GROK_MODEL,
    )

    model = research_model or (CHEAP_MODEL if cheap_mode else DEFAULT_MODEL)
    log = make_logger(on_log)
    t0 = time.perf_counter()

    if existing_data is None:
        existing_data = _load_existing(race_id)

    if existing_data:
        log("info", f"🔄 Update mode for {race_id} (model={model})")
        race_json = await _run_update(race_id, existing_data, model=model, on_log=on_log, max_iterations=max_iterations)
    else:
        log("info", f"🆕 New research for {race_id} (model={model})")
        race_json = await _run_fresh(race_id, model=model, on_log=on_log, max_iterations=max_iterations)

    race_json.setdefault("id", race_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    race_json["updated_utc"] = now_iso

    # Record the models actually used
    generators = [model]
    if enable_review:
        if os.getenv("ANTHROPIC_API_KEY"):
            generators.append(claude_model or (CHEAP_CLAUDE_MODEL if cheap_mode else DEFAULT_CLAUDE_MODEL))
        if os.getenv("GEMINI_API_KEY"):
            generators.append(gemini_model or (CHEAP_GEMINI_MODEL if cheap_mode else DEFAULT_GEMINI_MODEL))
        if os.getenv("XAI_API_KEY"):
            generators.append(grok_model or (CHEAP_GROK_MODEL if cheap_mode else DEFAULT_GROK_MODEL))
    race_json["generator"] = generators

    for candidate in race_json.get("candidates", []):
        if isinstance(candidate, dict):
            _normalize_candidate(candidate, now_iso)

    race_json.setdefault("polling", [])

    if enable_review:
        log("info", "Phase 4: Sending to review agents (Claude, Gemini, Grok)...")
        reviews = await run_reviews(
            race_id, race_json,
            on_log=on_log,
            cheap_mode=cheap_mode,
            claude_model=claude_model,
            gemini_model=gemini_model,
            grok_model=grok_model,
        )
        race_json["reviews"] = reviews
    else:
        race_json.setdefault("reviews", [])

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
    log = make_logger(on_log)

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
        max_tokens=4096,
    )

    candidate_names = [c["name"] for c in race_json.get("candidates", [])]
    n = len(candidate_names)
    if not candidate_names:
        log("warning", "No candidates found in discovery phase")
        return race_json

    issue_iters = _scale_iterations(max_iterations, n, per_candidate=3, minimum=12)
    refine_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=12)
    log("info", f"  Iteration budgets — issue:{issue_iters}  refine:{refine_iters}  (n={n} candidates)")

    # --- Phase 1b: Image URL verification & resolution (parallel) ---
    log("info", "Phase 1b/3: Verifying and resolving candidate image URLs...")
    await resolve_candidate_images(
        race_json,
        agent_loop_fn=_agent_loop,
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=min(max_iterations, 10),
    )

    # --- Phase 2: Issue research (one call per group) ---
    log("info", f"Phase 2/3: Researching issues for {n} candidates...")
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
            max_iterations=issue_iters,
            phase_name=f"issues-{group_idx + 1}",
            max_tokens=4096,
        )
        for cand_name, cand_issues in issues_result.items():
            if cand_name in all_issues and isinstance(cand_issues, dict):
                all_issues[cand_name].update(cand_issues)

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
        max_iterations=refine_iters,
        phase_name="refine",
        max_tokens=8192,
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
    log = make_logger(on_log)

    n = len(existing.get("candidates", []))
    update_iters = _scale_iterations(max_iterations, n, per_candidate=4, minimum=15)
    log("info", f"  Update iteration budget: {update_iters} (n={n} candidates)")

    last_updated = existing.get("updated_utc", "unknown")
    race_json = await _agent_loop(
        UPDATE_SYSTEM,
        UPDATE_USER.format(
            race_id=race_id,
            existing_json=json.dumps(existing, indent=2, default=str),
            last_updated=last_updated,
        ),
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=update_iters,
        phase_name="update",
        max_tokens=8192,
    )

    # Verify and fix image URLs after update (parallel)
    log("info", "Post-update: Verifying and resolving candidate image URLs...")
    await resolve_candidate_images(
        race_json,
        agent_loop_fn=_agent_loop,
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=min(max_iterations, 10),
    )

    return race_json
