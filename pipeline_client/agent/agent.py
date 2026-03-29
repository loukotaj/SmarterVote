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
import re
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
    UPDATE_META_SYSTEM,
    UPDATE_META_USER,
    UPDATE_ISSUE_SYSTEM,
    UPDATE_ISSUE_USER,
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

FETCH_TOOL = {
    "type": "function",
    "function": {
        "name": "fetch_page",
        "description": (
            "Fetch the full text content of a web page. Use this when a search "
            "result URL looks promising but you need more detail than the snippet "
            "provides — e.g. to read a full article, find an image URL embedded "
            "in a page, or extract specific data from a government site. "
            "Returns the page's readable text (HTML stripped), truncated to ~8000 characters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch.",
                }
            },
            "required": ["url"],
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


def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace to get readable page text."""
    # Remove script/style blocks entirely
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Replace block-level tags with newlines so paragraphs stay readable
    text = re.sub(r"</(p|div|li|h[1-6]|tr|br)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    for entity, char in [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'"),
    ]:
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_PAGE_MAX_CHARS = 8000
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


async def _fetch_page(url: str) -> str:
    """Fetch a URL and return stripped text content, with caching."""
    cache = _get_search_cache()
    if cache:
        cached = cache.get_page(url)
        if cached:
            logger.debug(f"Page cache HIT: {url[:60]}")
            return cached

    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type or "text" in content_type:
                text = _strip_html(resp.text)
            else:
                text = f"[Non-text content: {content_type}]"
    except Exception as exc:
        return f"[Failed to fetch {url}: {exc}]"

    # Truncate and add a note if we cut it
    if len(text) > _PAGE_MAX_CHARS:
        text = text[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"

    if cache:
        cache.set_page(url, text)

    return text


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
    max_tokens: int = 16384,
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
    max_tokens: int = 16384,
) -> Dict[str, Any]:
    """Run a single agent loop (search → answer → parse JSON)."""
    log = make_logger(on_log)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    nudge_at = max(int(max_iterations / 1.5), 3)

    for iteration in range(max_iterations):
        log("info", f"  [{phase_name}] iteration {iteration + 1}/{max_iterations} — calling {model}...")

        # After a significant portion of the budget is spent, stop offering the search tool and
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

        tools_for_call = [SEARCH_TOOL, FETCH_TOOL] if iteration < nudge_at else None

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
                elif fn["name"] == "fetch_page":
                    args = json.loads(fn["arguments"])
                    url = args.get("url", "")
                    log("info", f"    📄 fetching {url[:80]}")
                    page_text = await _fetch_page(url)
                    log("debug", f"    📄 got {len(page_text)} chars")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": page_text,
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
                    f"Your response was not valid JSON. Parse error: {exc}. "
                    "Common causes: using None/True/False instead of null/true/false, "
                    "unescaped quotes or backslashes inside string values, or text "
                    "appended after the closing brace. "
                    "Return ONLY the raw JSON object — no markdown, no explanation, "
                    "no trailing text whatsoever."
                ),
            })
            continue

    raise RuntimeError(
        f"[{phase_name}] did not produce output within {max_iterations} iterations"
    )


def _ensure_dict(result: Any, phase_name: str, log: Any) -> Dict[str, Any]:
    """Unwrap a single-element list or raise if the result is not a dict."""
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        # Model sometimes wraps the object in an array — unwrap if unambiguous
        dicts = [item for item in result if isinstance(item, dict)]
        if len(dicts) == 1:
            log("warning", f"  [{phase_name}] returned a list — unwrapping single dict")
            return dicts[0]
        if dicts:
            log("warning", f"  [{phase_name}] returned a list of {len(dicts)} dicts — merging")
            merged: Dict[str, Any] = {}
            for d in dicts:
                merged.update(d)
            return merged
    raise ValueError(f"[{phase_name}] expected dict, got {type(result).__name__}")


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
    enable_review: bool = True,
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

    # LLMs sometimes wrap their output in {"race_json": {...}} — unwrap it so
    # metadata we add below lands at the top level, not buried inside a key.
    if "race_json" in race_json and isinstance(race_json.get("race_json"), dict):
        log("warning", "LLM wrapped output in 'race_json' key — unwrapping")
        race_json = race_json["race_json"]

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
    race_json = _ensure_dict(await _agent_loop(
        DISCOVERY_SYSTEM,
        DISCOVERY_USER.format(race_id=race_id),
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=max_iterations,
        phase_name="discovery",
        max_tokens=16384,
    ), "discovery", log)

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
        try:
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
                max_tokens=16384,
            )
            if not isinstance(issues_result, dict):
                log("warning", f"  Issue group {group_idx + 1} returned non-dict ({type(issues_result).__name__}) — skipping")
            else:
                for cand_name, cand_issues in issues_result.items():
                    if cand_name in all_issues and isinstance(cand_issues, dict):
                        all_issues[cand_name].update(cand_issues)
        except RuntimeError as exc:
            log("warning", f"  Issue group {group_idx + 1} failed after all retries: {exc} — skipping group")

    for candidate in race_json.get("candidates", []):
        name = candidate["name"]
        if name in all_issues:
            candidate.setdefault("issues", {}).update(all_issues[name])

    # --- Phase 3: Refinement ---
    log("info", "Phase 3/3: Refining and improving profile...")
    try:
        race_json = _ensure_dict(await _agent_loop(
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
            max_tokens=32768,
        ), "refine", log)
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Refine phase failed: {exc} — returning unrefined draft")

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
    """Phase-based update mirroring _run_fresh but starting from existing data."""
    log = make_logger(on_log)

    # Start from a deep copy of existing so we never mutate the original
    import copy
    race_json: Dict[str, Any] = copy.deepcopy(existing)

    existing_candidates = existing.get("candidates", [])
    candidate_names = [c["name"] for c in existing_candidates]
    n = len(candidate_names)
    last_updated = existing.get("updated_utc", "unknown")

    if not candidate_names:
        log("warning", "No candidates in existing data — falling back to fresh run")
        return await _run_fresh(race_id, model=model, on_log=on_log, max_iterations=max_iterations)

    meta_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=10)
    issue_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=10)
    refine_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=12)

    # --- Phase 1: Meta update (summaries, donors, polls, voting record) ---
    log("info", "Update Phase 1: Searching for new summaries, donors, polls, voting records...")
    try:
        meta_patch = _ensure_dict(await _agent_loop(
            UPDATE_META_SYSTEM,
            UPDATE_META_USER.format(
                race_id=race_id,
                last_updated=last_updated,
                candidate_names=", ".join(candidate_names),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=meta_iters,
            phase_name="update-meta",
            max_tokens=16384,
        ), "update-meta", log)
        _apply_meta_patch(race_json, meta_patch, log)
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Update meta phase failed: {exc} — keeping existing meta")

    # --- Phase 2: Issue updates (one call per group) ---
    log("info", f"Update Phase 2: Refreshing issue positions for {n} candidates...")
    for group_idx, issues in enumerate(ISSUE_GROUPS):
        log("info", f"  Issue group {group_idx + 1}/{len(ISSUE_GROUPS)}: {', '.join(issues)}")
        try:
            # Build a summary of existing stances for this group
            existing_stances = _summarize_existing_stances(existing_candidates, issues)
            issues_result = await _agent_loop(
                UPDATE_ISSUE_SYSTEM,
                UPDATE_ISSUE_USER.format(
                    race_id=race_id,
                    last_updated=last_updated,
                    candidate_names=", ".join(candidate_names),
                    issues_list="\n".join(f"  - {i}" for i in issues),
                    existing_stances=existing_stances,
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=issue_iters,
                phase_name=f"update-issues-{group_idx + 1}",
                max_tokens=8192,
            )
            if not isinstance(issues_result, dict):
                log("warning", f"  Issue group {group_idx + 1} returned non-dict — skipping")
            else:
                _apply_issue_patch(race_json, issues_result, log)
        except (RuntimeError, ValueError) as exc:
            log("warning", f"  Issue group {group_idx + 1} failed: {exc} — keeping existing")

    # --- Phase 3: Refinement (same as fresh run) ---
    log("info", "Update Phase 3: Refining updated profile...")
    try:
        refined = _ensure_dict(await _agent_loop(
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
            phase_name="update-refine",
            max_tokens=32768,
        ), "update-refine", log)

        # Safety: never let refine wipe candidates
        if refined.get("candidates") and len(refined["candidates"]) >= n:
            race_json = refined
        else:
            log("warning", "  Refine dropped candidates — keeping pre-refine version")
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Refine phase failed: {exc} — keeping unrefined update")

    # --- Post-update: image URL verification ---
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


def _apply_meta_patch(race_json: Dict[str, Any], patch: Dict[str, Any], log: Any) -> None:
    """Merge a meta patch (summaries, donors, polls, voting record) into race_json in-place."""
    if "description" in patch and patch["description"]:
        race_json["description"] = patch["description"]

    if "polling" in patch and isinstance(patch["polling"], list) and patch["polling"]:
        existing_polls = race_json.get("polling", [])
        race_json["polling"] = patch["polling"] + existing_polls

    patch_candidates = {c["name"]: c for c in patch.get("candidates", []) if isinstance(c, dict)}
    for candidate in race_json.get("candidates", []):
        name = candidate.get("name")
        pc = patch_candidates.get(name)
        if not pc:
            continue
        if pc.get("summary"):
            candidate["summary"] = pc["summary"]
        if pc.get("top_donors"):
            candidate["top_donors"] = pc["top_donors"]
        if pc.get("voting_record"):
            existing_vr = {v.get("bill_name"): v for v in candidate.get("voting_record", [])}
            for vote in pc["voting_record"]:
                existing_vr[vote.get("bill_name", "")] = vote
            candidate["voting_record"] = list(existing_vr.values())
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
