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
    IMAGE_SEARCH_SYSTEM,
    IMAGE_SEARCH_USER,
    ISSUE_GROUPS,
    ISSUE_RESEARCH_SYSTEM,
    ISSUE_RESEARCH_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    REVIEW_SYSTEM,
    REVIEW_USER,
    UPDATE_SYSTEM,
    UPDATE_USER,
)

logger = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Model configuration — defaults & cheap variants
# ---------------------------------------------------------------------------

# Primary research models
DEFAULT_MODEL = "gpt-5.4"
CHEAP_MODEL = "gpt-5-mini"

# Review models (full quality)
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_GEMINI_MODEL = "gemini-3.0-flash"
DEFAULT_GROK_MODEL = "grok-3"

# Review models (cheap mode)
CHEAP_CLAUDE_MODEL = "claude-haiku-4-20250514"
CHEAP_GEMINI_MODEL = "gemini-3.0-flash-lite"
CHEAP_GROK_MODEL = "grok-3-mini"

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
            from pipeline_client.agent.search_cache import SearchCache

            _search_cache = SearchCache()
        except Exception:
            # Sentinel: cache unavailable; don't retry on every call
            _search_cache = "unavailable"
    return _search_cache if _search_cache != "unavailable" else None


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
    max_retries: int = 5,
) -> Dict[str, Any]:
    """Call the OpenAI Chat Completions API with retry on transient errors."""
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

    import asyncio

    for attempt in range(max_retries):
        async with httpx.AsyncClient(timeout=300) as client:
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
                logger.warning(f"OpenAI {resp.status_code}, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM output, handling markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _normalize_source(source: Any, now_iso: str) -> None:
    """Apply required defaults to a single source object in-place."""
    if isinstance(source, dict):
        source.setdefault("last_accessed", now_iso)


_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"})
_IMAGE_URL_PATTERNS = re.compile(r"/(photo|headshot|portrait|profile[_\-]?pic|image|img|photos?)/", re.IGNORECASE)


def _is_valid_image_url(url: Any) -> bool:
    """Return True only if the URL looks like a direct image, not a web page."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.lower().rstrip("/")
        if any(path.endswith(ext) for ext in _IMAGE_EXTENSIONS):
            return True
        if _IMAGE_URL_PATTERNS.search(parsed.path):
            return True
        # Wikipedia/Wikimedia direct image URLs lack extensions but have /Special:FilePath or /thumb/
        if "wikimedia.org" in parsed.netloc or "wikipedia.org" in parsed.netloc:
            return True
        # Some CDN/image service patterns
        if any(host in parsed.netloc for host in ("cloudfront.net", "githubusercontent.com", "twimg.com", "fbcdn.net")):
            return True
    except Exception:
        return False
    return False


def _normalize_candidate(candidate: Dict[str, Any], now_iso: str) -> None:
    """Apply output defaults and source normalization to a candidate."""
    candidate.setdefault("image_url", None)
    candidate.setdefault("career_history", [])
    candidate.setdefault("education", [])
    candidate.setdefault("voting_record", [])
    candidate.setdefault("top_donors", [])

    # Validate image_url — reject page URLs that aren't direct images
    if candidate.get("image_url") and not _is_valid_image_url(candidate["image_url"]):
        logger.debug(f"Clearing invalid image_url: {candidate['image_url']}")
        candidate["image_url"] = None

    for issue_data in candidate.get("issues", {}).values():
        if isinstance(issue_data, dict):
            for src in issue_data.get("sources", []):
                _normalize_source(src, now_iso)

    for donor in candidate.get("top_donors", []):
        if isinstance(donor, dict):
            _normalize_source(donor.get("source"), now_iso)

    for career_entry in candidate.get("career_history", []):
        if isinstance(career_entry, dict):
            _normalize_source(career_entry.get("source"), now_iso)

    for education_entry in candidate.get("education", []):
        if isinstance(education_entry, dict):
            _normalize_source(education_entry.get("source"), now_iso)

    for voting_entry in candidate.get("voting_record", []):
        if isinstance(voting_entry, dict):
            _normalize_source(voting_entry.get("source"), now_iso)


# ---------------------------------------------------------------------------
# Image URL verification & resolution
# ---------------------------------------------------------------------------


async def _check_url_accessible(url: str) -> bool:
    """Return True if a HEAD request to *url* returns a 2xx status within 8 s."""
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.head(url, headers={"User-Agent": "SmarterVote/1.0"})
            return resp.status_code < 400
    except Exception:
        return False


async def _resolve_candidate_images(
    race_json: Dict[str, Any],
    *,
    model: str,
    on_log: Any | None = None,
    race_id: Optional[str] = None,
    max_iterations: int = 10,
) -> None:
    """Validate each candidate's image_url and fix broken ones in-place.

    For each candidate:
    1. If image_url is set, do a HEAD request to verify it's live.
    2. If missing or dead, run a mini agent loop using IMAGE_SEARCH_USER
       to find a working direct image URL.
    """

    def log(level: str, msg: str) -> None:
        logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)

    for candidate in race_json.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        name = candidate.get("name", "unknown")
        current_url = candidate.get("image_url")

        # Step 1: verify existing URL
        if current_url and _is_valid_image_url(current_url):
            if await _check_url_accessible(current_url):
                log("info", f"  🖼  {name}: image OK ({current_url[:60]}...)")
                continue
            else:
                log("info", f"  🖼  {name}: image URL is dead — searching for replacement")
                candidate["image_url"] = None
        else:
            if current_url:
                log("info", f"  🖼  {name}: image_url looks like a page URL — searching for direct image")
                candidate["image_url"] = None
            else:
                log("info", f"  🖼  {name}: no image_url — searching")

        # Step 2: run mini agent loop to find a working image URL
        try:
            result = await _agent_loop(
                IMAGE_SEARCH_SYSTEM,
                IMAGE_SEARCH_USER.format(candidate_name=name),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=max_iterations,
                phase_name=f"image-{name[:20]}",
            )
            found_url = result.get("image_url")
            if found_url and _is_valid_image_url(found_url):
                if await _check_url_accessible(found_url):
                    candidate["image_url"] = found_url
                    log("info", f"  🖼  {name}: resolved image → {found_url[:80]}")
                else:
                    log("info", f"  🖼  {name}: agent found URL but it's dead: {found_url}")
            else:
                log("info", f"  🖼  {name}: no working image found")
        except Exception as exc:
            log("warning", f"  🖼  {name}: image resolution error: {exc}")


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
    published_dir = Path(__file__).resolve().parents[2] / "data" / "published"
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
        When *True*, use cheaper/faster model variants (``gpt-5-mini`` instead of ``gpt-5.4``).
    max_iterations : int
        Safety limit on each phase's tool-call loop.
    existing_data : dict, optional
        An existing RaceJSON to update/improve. When *None* (default),
        the agent checks ``data/published/{race_id}.json`` for a
        previously published profile and enters update mode if found.
        Pass an empty dict to force a fresh research run even when a
        published profile exists.
    enable_review : bool
        When *True*, send the final profile to Claude, Gemini, and Grok
        for independent fact-checking. Results are stored in ``reviews``.
    research_model : str, optional
        Override the OpenAI model for research phases.
    claude_model : str, optional
        Override the Claude model for review.
    gemini_model : str, optional
        Override the Gemini model for review.
    grok_model : str, optional
        Override the Grok model for review.

    Returns
    -------
    dict
        The completed RaceJSON output.
    """

    model = research_model or (CHEAP_MODEL if cheap_mode else DEFAULT_MODEL)

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
    # Record the models actually used for transparency
    generators = [model]
    if enable_review:
        if os.getenv("ANTHROPIC_API_KEY"):
            generators.append(claude_model or (CHEAP_CLAUDE_MODEL if cheap_mode else DEFAULT_CLAUDE_MODEL))
        if os.getenv("GEMINI_API_KEY"):
            generators.append(gemini_model or (CHEAP_GEMINI_MODEL if cheap_mode else DEFAULT_GEMINI_MODEL))
        if os.getenv("XAI_API_KEY"):
            generators.append(grok_model or (CHEAP_GROK_MODEL if cheap_mode else DEFAULT_GROK_MODEL))
    race_json["generator"] = generators

    # Ensure new fields have defaults
    for candidate in race_json.get("candidates", []):
        if isinstance(candidate, dict):
            _normalize_candidate(candidate, now_iso)

    # --- Optional Phase 4: Multi-LLM review ---
    if enable_review:
        log("info", "Phase 4: Sending to review agents (Claude, Gemini, Grok)...")
        reviews = await _run_reviews(
            race_id, race_json, on_log=on_log, cheap_mode=cheap_mode,
            claude_model=claude_model, gemini_model=gemini_model, grok_model=grok_model,
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

    # --- Phase 1b: Image URL verification & resolution ---
    log("info", "Phase 1b/3: Verifying and resolving candidate image URLs...")
    await _resolve_candidate_images(
        race_json,
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=max_iterations,
    )

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

    def log(level: str, msg: str) -> None:
        logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)

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
        max_iterations=max_iterations,
        phase_name="update",
    )

    # Verify and fix image URLs after update
    log("info", "Post-update: Verifying and resolving candidate image URLs...")
    await _resolve_candidate_images(
        race_json,
        model=model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=max_iterations,
    )

    return race_json


# ---------------------------------------------------------------------------
# Multi-LLM review (Claude / Gemini)
# ---------------------------------------------------------------------------


async def _call_anthropic(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_CLAUDE_MODEL,
) -> str:
    """Call the Anthropic Messages API and return the text response."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    # Extract text from content blocks
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block["text"]
    return ""


async def _call_gemini(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_GEMINI_MODEL,
) -> str:
    """Call the Google Gemini (Generative Language) API and return the text."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
            },
        )
        resp.raise_for_status()
        data = resp.json()

    # Extract text from first candidate
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if "text" in part:
                return part["text"]
    return ""


async def _call_grok(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_GROK_MODEL,
) -> str:
    """Call the xAI Grok API (OpenAI-compatible) and return the text."""
    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return data["choices"][0]["message"]["content"]


async def _run_single_review(
    race_id: str,
    profile_json: str,
    *,
    provider: str,
    model_override: Optional[str] = None,
    on_log: Any | None = None,
) -> Optional[Dict[str, Any]]:
    """Run a single review agent (Claude, Gemini, or Grok)."""

    def log(level: str, msg: str) -> None:
        logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)

    user_prompt = REVIEW_USER.format(
        race_id=race_id,
        profile_json=profile_json,
    )

    model_name = ""
    try:
        if provider == "claude":
            model_name = model_override or DEFAULT_CLAUDE_MODEL
            log("info", f"  📋 Reviewing with {model_name}...")
            raw = await _call_anthropic(REVIEW_SYSTEM, user_prompt, model=model_name)
        elif provider == "gemini":
            model_name = model_override or DEFAULT_GEMINI_MODEL
            log("info", f"  📋 Reviewing with {model_name}...")
            raw = await _call_gemini(REVIEW_SYSTEM, user_prompt, model=model_name)
        elif provider == "grok":
            model_name = model_override or DEFAULT_GROK_MODEL
            log("info", f"  📋 Reviewing with {model_name}...")
            raw = await _call_grok(REVIEW_SYSTEM, user_prompt, model=model_name)
        else:
            return None

        review_data = _extract_json(raw)
        return {
            "model": model_name,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "verdict": review_data.get("verdict", "flagged"),
            "flags": review_data.get("flags", []),
            "summary": review_data.get("summary", ""),
        }
    except Exception as exc:
        log("warning", f"  ⚠️ {provider} review failed: {exc}")
        return None


_REVIEW_PROVIDERS = {
    "claude": ("ANTHROPIC_API_KEY", DEFAULT_CLAUDE_MODEL, CHEAP_CLAUDE_MODEL),
    "gemini": ("GEMINI_API_KEY", DEFAULT_GEMINI_MODEL, CHEAP_GEMINI_MODEL),
    "grok":   ("XAI_API_KEY", DEFAULT_GROK_MODEL, CHEAP_GROK_MODEL),
}


async def _run_reviews(
    race_id: str,
    race_json: Dict[str, Any],
    *,
    on_log: Any | None = None,
    cheap_mode: bool = True,
    claude_model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    grok_model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run reviews with available LLM providers (Claude, Gemini, Grok)."""
    profile_json = json.dumps(race_json, indent=2, default=str)
    reviews: List[Dict[str, Any]] = []

    model_overrides = {
        "claude": claude_model,
        "gemini": gemini_model,
        "grok": grok_model,
    }

    for provider, (env_key, full_model, cheap_model_name) in _REVIEW_PROVIDERS.items():
        if not os.environ.get(env_key):
            if on_log:
                on_log("info", f"  ⏭️ Skipping {provider} review ({env_key} not set)")
            continue

        # Priority: explicit override > cheap_mode selection > full model
        effective_model = model_overrides.get(provider) or (cheap_model_name if cheap_mode else full_model)

        result = await _run_single_review(
            race_id,
            profile_json,
            provider=provider,
            model_override=effective_model,
            on_log=on_log,
        )
        if result:
            reviews.append(result)

    return reviews
