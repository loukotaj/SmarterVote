"""Multi-phase candidate research agent with web search & caching.

Phases (fresh run):
1. **Discovery** – identify the race, candidates, career history, images.
1b. **Image resolution** – verify/find direct image URLs per candidate.
2. **Issue research** – 12 per-candidate sub-agent calls (one per canonical issue).
2b. **Finance & voting** – dedicated donor and voting-record research.
3. **Refinement** – tools-mode per-candidate and meta cleanup.
4. **Review** (optional) – send to Claude, Gemini, and Grok for fact-checking.
5. **Iteration** – tools-mode pass to address review flags (up to 2 cycles).

Update run adds Phase 0 (roster sync) before Phase 1 (meta update).

Uses a SQLite search cache (``pipeline_client.agent.search_cache``) to avoid
redundant Serper API calls across runs.  Token usage and estimated USD cost
are attached to the output JSON under ``agent_metrics``.
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

from .cost import _cost_ctx, accumulate, estimate_cost
from .handlers import _make_editing_handlers
from .images import resolve_candidate_images
from .prompts import (
    CANONICAL_ISSUES,
    DISCOVERY_SYSTEM,
    DISCOVERY_USER,
    FINANCE_VOTING_SYSTEM,
    FINANCE_VOTING_USER,
    ISSUE_SUBAGENT_SYSTEM,
    ISSUE_SUBAGENT_USER,
    ITERATE_SYSTEM,
    ITERATE_USER,
    ITERATE_META_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    REFINE_META_USER,
    ROSTER_SYNC_SYSTEM,
    ROSTER_SYNC_USER,
    UPDATE_ISSUE_SUBAGENT_SYSTEM,
    UPDATE_ISSUE_SUBAGENT_USER,
    UPDATE_META_SYSTEM,
    UPDATE_META_USER,
)
from .review import run_reviews
from .utils import _extract_json, make_logger

logger = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Model configuration — defaults & cheap variants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gpt-5.4"
CHEAP_MODEL  = "gpt-5.4-mini"
NANO_MODEL   = "gpt-5-nano"   # fastest/cheapest — used for focused sub-tasks in cheap mode

# ---------------------------------------------------------------------------
# Web search tool definition for OpenAI function calling
# (cost tracking imported from .cost; editing handlers from .handlers)
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
# Editing tool definitions for tools-mode phases
# ---------------------------------------------------------------------------

# --- Roster tools ---

ADD_CANDIDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "add_candidate",
        "description": "Add a new candidate to the race. Use when a new entrant has joined the race.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name of the candidate."},
                "party": {"type": "string", "description": "Party affiliation (e.g. 'Democratic', 'Republican')."},
                "incumbent": {"type": "boolean", "description": "Whether this candidate is the incumbent."},
            },
            "required": ["name", "party"],
        },
    },
}

REMOVE_CANDIDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "remove_candidate",
        "description": "Remove a candidate who has dropped out or withdrawn from the race.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Exact name of the candidate to remove."},
                "reason": {"type": "string", "description": "Brief reason for removal (e.g. 'withdrew', 'disqualified')."},
            },
            "required": ["name"],
        },
    },
}

RENAME_CANDIDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "rename_candidate",
        "description": "Correct a candidate's name (e.g. fix spelling, use formal name).",
        "parameters": {
            "type": "object",
            "properties": {
                "old_name": {"type": "string", "description": "Current name in the profile."},
                "new_name": {"type": "string", "description": "Corrected name."},
            },
            "required": ["old_name", "new_name"],
        },
    },
}

ROSTER_TOOLS = [ADD_CANDIDATE_TOOL, REMOVE_CANDIDATE_TOOL, RENAME_CANDIDATE_TOOL]

# --- Candidate field tools ---

SET_CANDIDATE_FIELD_TOOL = {
    "type": "function",
    "function": {
        "name": "set_candidate_field",
        "description": (
            "Update a scalar field on a candidate. Allowed fields: party, incumbent, "
            "website, image_url."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "field": {"type": "string", "enum": ["party", "incumbent", "website", "image_url"],
                          "description": "Field to update."},
                "value": {"description": "New value for the field."},
            },
            "required": ["candidate_name", "field", "value"],
        },
    },
}

SET_CANDIDATE_SUMMARY_TOOL = {
    "type": "function",
    "function": {
        "name": "set_candidate_summary",
        "description": "Rewrite a candidate's biographical summary. Keep it 2-3 sentences, nonpartisan.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "summary": {"type": "string", "description": "New 2-3 sentence nonpartisan summary."},
                "sources": {
                    "type": "array",
                    "description": "Source URLs for the summary.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "type": {"type": "string"},
                            "title": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["candidate_name", "summary"],
        },
    },
}

CANDIDATE_TOOLS = [SET_CANDIDATE_FIELD_TOOL, SET_CANDIDATE_SUMMARY_TOOL]

# --- Issue tools ---

SET_ISSUE_STANCE_TOOL = {
    "type": "function",
    "function": {
        "name": "set_issue_stance",
        "description": "Set or update a candidate's stance on a canonical issue.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "issue": {"type": "string", "description": "Canonical issue name (e.g. 'Healthcare')."},
                "stance": {"type": "string", "description": "1-2 sentence position description."},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"],
                               "description": "Confidence level."},
                "sources": {
                    "type": "array",
                    "description": "Source URLs supporting this stance.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "type": {"type": "string"},
                            "title": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["candidate_name", "issue", "stance", "confidence"],
        },
    },
}

ISSUE_TOOLS = [SET_ISSUE_STANCE_TOOL]

# --- Record tools (bulk replace) ---

SET_VOTING_RECORDS_TOOL = {
    "type": "function",
    "function": {
        "name": "set_voting_records",
        "description": "Replace a candidate's entire voting record list.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "records": {
                    "type": "array",
                    "description": "Full voting record list.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "bill_name": {"type": "string"},
                            "bill_description": {"type": "string"},
                            "vote": {"type": "string", "enum": ["yes", "no", "abstain", "absent"]},
                            "date": {"type": "string"},
                            "source": {"type": "object"},
                        },
                        "required": ["bill_name", "vote"],
                    },
                },
            },
            "required": ["candidate_name", "records"],
        },
    },
}

SET_DONORS_TOOL = {
    "type": "function",
    "function": {
        "name": "set_donors",
        "description": "Replace a candidate's entire top donors list.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_name": {"type": "string", "description": "Exact candidate name."},
                "donors": {
                    "type": "array",
                    "description": "Full top donors list.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "amount": {"type": "number"},
                            "organization": {"type": "string"},
                            "source": {"type": "object"},
                        },
                        "required": ["name"],
                    },
                },
            },
            "required": ["candidate_name", "donors"],
        },
    },
}

RECORD_TOOLS = [SET_VOTING_RECORDS_TOOL, SET_DONORS_TOOL]

# --- Race-level tools ---

ADD_POLL_TOOL = {
    "type": "function",
    "function": {
        "name": "add_poll",
        "description": "Add a new poll to the race's polling data.",
        "parameters": {
            "type": "object",
            "properties": {
                "pollster": {"type": "string", "description": "Polling organization name."},
                "date": {"type": "string", "description": "Date of poll (YYYY-MM-DD)."},
                "sample_size": {"type": "integer", "description": "Number of respondents."},
                "matchups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidates": {"type": "array", "items": {"type": "string"}},
                            "percentages": {"type": "array", "items": {"type": "number"}},
                        },
                    },
                },
                "source_url": {"type": "string", "description": "URL to poll source."},
            },
            "required": ["pollster", "date", "matchups", "source_url"],
        },
    },
}

UPDATE_RACE_FIELD_TOOL = {
    "type": "function",
    "function": {
        "name": "update_race_field",
        "description": "Update a race-level field. Allowed fields: description, office, election_date.",
        "parameters": {
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": ["description", "office", "election_date"],
                          "description": "Field to update."},
                "value": {"type": "string", "description": "New value."},
            },
            "required": ["field", "value"],
        },
    },
}

RACE_TOOLS = [ADD_POLL_TOOL, UPDATE_RACE_FIELD_TOOL]

# --- Read-only tool for verifying state ---

READ_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_profile",
        "description": (
            "Read the current state of the race profile JSON. Use this to verify "
            "your edits took effect or to check what data already exists."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["full", "candidates", "issues", "polling", "meta"],
                    "description": "Which section to read. Use 'issues' for a compact issues-only view.",
                },
            },
            "required": ["section"],
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
    # Strip ASCII control characters that are invalid in JSON strings
    # (keep \x09 tab, \x0a newline, \x0d carriage-return)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


_PAGE_MAX_CHARS = 16000
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
    max_retries: int = 12,
    max_tokens: int = 16384,
):
    """Call the OpenAI Chat Completions API with retry on transient errors.

    429 rate-limit: exponential backoff starting at 30 s, capped at 10 min.
    5xx transient errors: shorter exponential backoff (2, 4, 8 … s).
    The Retry-After response header always takes precedence.

    Returns an ``openai.types.chat.ChatCompletion`` object.
    """
    from openai import AsyncOpenAI, RateLimitError, APIStatusError

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = AsyncOpenAI(api_key=api_key, max_retries=0, timeout=300)

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_completion_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    for attempt in range(max_retries):
        try:
            resp = await client.chat.completions.create(**kwargs)
            if resp.usage:
                accumulate(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0, model)
            return resp
        except RateLimitError as exc:
            if attempt >= max_retries - 1:
                raise
            retry_after = 0
            if exc.response is not None:
                retry_after = int(exc.response.headers.get("retry-after", 0))
            backoff = min(600, 30 * (2 ** attempt))
            wait = max(retry_after, backoff)
            logger.warning(f"OpenAI 429, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait)
        except APIStatusError as exc:
            if attempt >= max_retries - 1 or exc.status_code < 500:
                raise
            backoff = 2 ** (attempt + 1)
            logger.warning(
                f"OpenAI {exc.status_code}, retrying in {backoff}s "
                f"(attempt {attempt + 1}/{max_retries})"
            )
            await asyncio.sleep(backoff)

    raise RuntimeError("OpenAI: max retries exceeded")


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
    extra_tools: List[Dict[str, Any]] | None = None,
    extra_tool_handlers: Dict[str, Any] | None = None,
    tools_mode: bool = False,
) -> Dict[str, Any]:
    """Run a single agent loop.

    In normal (json) mode: search → answer → parse JSON.
    In tools_mode: the LLM uses editing tools to mutate state directly;
    the loop exits when the LLM stops making tool calls.  Returns ``{}``.
    """
    log = make_logger(on_log)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    nudge_at = max(int(max_iterations / 1.5), 3)
    _extra_tools = extra_tools or []
    _extra_handlers = extra_tool_handlers or {}

    for iteration in range(max_iterations):
        log("info", f"  [{phase_name}] iteration {iteration + 1}/{max_iterations} — calling {model}...")

        if tools_mode:
            # In tools mode: search tools cut off at nudge_at, editing tools stay available
            search_tools = [SEARCH_TOOL, FETCH_TOOL] if iteration < nudge_at else []
            tools_for_call = search_tools + _extra_tools if (search_tools or _extra_tools) else None

            if iteration == nudge_at and len(messages) > 2:
                messages.append({
                    "role": "user",
                    "content": (
                        "You have used several searches. Stop searching and use your "
                        "editing tools to commit your findings now. When you are done "
                        "editing, reply with a short confirmation message (no JSON needed)."
                    ),
                })
                log("info", f"  [{phase_name}] nudging model to commit edits (iteration {iteration + 1})")
        else:
            # In json mode: all tools cut off at nudge_at
            if iteration == nudge_at and len(messages) > 2:
                messages.append({
                    "role": "user",
                    "content": (
                        "You have used several searches. Please now compile your findings "
                        "and return ONLY the final JSON response. No more searches."
                    ),
                })
                log("info", f"  [{phase_name}] nudging model to produce output (iteration {iteration + 1})")

            base_tools = [SEARCH_TOOL, FETCH_TOOL] if iteration < nudge_at else []
            # Extra tools (editing) stay available past nudge in json mode too
            tools_for_call = (base_tools + _extra_tools) if (base_tools or _extra_tools) else None

        t_call = time.perf_counter()
        result = await _call_openai(
            messages, model=model, tools=tools_for_call, max_tokens=max_tokens
        )
        elapsed_call = time.perf_counter() - t_call

        choice = result.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason or "?"
        usage = result.usage
        log(
            "info",
            f"  [{phase_name}] response in {elapsed_call:.1f}s — "
            f"finish={finish_reason} "
            f"tokens={getattr(usage, 'prompt_tokens', '?')}→{getattr(usage, 'completion_tokens', '?')}",
        )

        # If the model wants to call tools, execute them
        if message.tool_calls and tools_for_call:
            # model_dump() can include extra Pydantic fields; keep only what the API accepts
            msg_dict = {
                "role": message.role,
                "content": message.content,
                "tool_calls": [tc.model_dump() for tc in message.tool_calls],
            }
            messages.append(msg_dict)
            for tool_call in message.tool_calls:
                fn = tool_call.function
                if fn.name == "web_search":
                    args = json.loads(fn.arguments)
                    query = args.get("query", "")
                    log("info", f"    🔍 {query}")
                    search_results = await _serper_search(query, race_id=race_id)
                    log("debug", f"    🔍 got {len(search_results)} results")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(search_results),
                    })
                elif fn.name == "fetch_page":
                    args = json.loads(fn.arguments)
                    url = args.get("url", "")
                    log("info", f"    📄 fetching {url[:80]}")
                    page_text = await _fetch_page(url)
                    log("debug", f"    📄 got {len(page_text)} chars")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": page_text,
                    })
                elif fn.name in _extra_handlers:
                    args = json.loads(fn.arguments)
                    log("info", f"    🔧 {fn.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
                    try:
                        handler_result = _extra_handlers[fn.name](args)
                        log("info", f"    🔧 {fn.name} → OK")
                    except Exception as exc:
                        handler_result = f"Error: {exc}"
                        log("warning", f"    🔧 {fn.name} → {exc}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(handler_result),
                    })
                else:
                    log("warning", f"    ⚠️ Unknown tool: {fn.name}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: unknown tool '{fn.name}'",
                    })
            continue

        # No tool calls — in tools_mode this means the LLM is done editing
        if tools_mode:
            log("info", f"  [{phase_name}] tools-mode complete (no more tool calls)")
            return {}

        # Normal json mode — try to parse the answer
        content = message.content or ""

        # Response was truncated: ask for a more concise answer
        if finish_reason == "length":
            log("warning", f"  [{phase_name}] response truncated (finish_reason=length) — retrying with brevity prompt")
            messages.append(message.model_dump())
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
            messages.append(message.model_dump())
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

    if tools_mode:
        log("warning", f"  [{phase_name}] tools-mode hit max iterations — returning")
        return {}
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
    # Sub-task model: nano in cheap mode, mini in normal mode (full model reserved for synthesis).
    small_model = NANO_MODEL if cheap_mode else CHEAP_MODEL
    log = make_logger(on_log)
    t0 = time.perf_counter()

    # Initialise a fresh cost accumulator for this run
    _acc: Dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0}
    _ctx_token = _cost_ctx.set(_acc)

    if existing_data is None:
        existing_data = _load_existing(race_id)

    if existing_data:
        log("info", f"🔄 Update mode for {race_id} (model={model}, small_model={small_model})")
        race_json = await _run_update(race_id, existing_data, model=model, small_model=small_model, on_log=on_log, max_iterations=max_iterations)
    else:
        log("info", f"🆕 New research for {race_id} (model={model}, small_model={small_model})")
        race_json = await _run_fresh(race_id, model=model, small_model=small_model, on_log=on_log, max_iterations=max_iterations)

    # LLMs sometimes wrap their output in {"race_json": {...}} — unwrap it so
    # metadata we add below lands at the top level, not buried inside a key.
    if "race_json" in race_json and isinstance(race_json.get("race_json"), dict):
        log("warning", "LLM wrapped output in 'race_json' key — unwrapping")
        race_json = race_json["race_json"]

    race_json.setdefault("id", race_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    race_json["updated_utc"] = now_iso

    # Record the models actually used (deduplicated — nano == model in full mode)
    generators = list(dict.fromkeys([model, small_model]))  # preserves order, drops duplicates
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

        # --- Phase 5: Iterate on review feedback (up to 2 cycles) ---
        max_review_cycles = 2
        for cycle in range(1, max_review_cycles + 1):
            # Cycle 2+: only iterate on error-severity flags to break subjective loops
            min_severity = "error" if cycle > 1 else "warning"
            if not _has_actionable_flags(reviews, min_severity=min_severity):
                if cycle == 1:
                    log("info", "  No actionable review flags — skipping iteration")
                else:
                    log("info", f"  Cycle {cycle}: no remaining {min_severity}+ flags — done")
                break

            log("info", f"Phase 5 (cycle {cycle}/{max_review_cycles}): Iterating on review feedback...")
            # Split iteration budget: 60% cycle 1, 40% cycle 2
            cycle_budget = int(max_iterations * (0.6 if cycle == 1 else 0.4))
            improved = await _run_iteration_pass(
                race_id, race_json, reviews,
                model=model, on_log=on_log, max_iterations=max(cycle_budget, 8),
            )
            if improved is not None:
                race_json = improved
                # Re-normalize after iteration
                now_iso = datetime.now(timezone.utc).isoformat()
                race_json["updated_utc"] = now_iso
                for candidate in race_json.get("candidates", []):
                    if isinstance(candidate, dict):
                        _normalize_candidate(candidate, now_iso)
                race_json["generator"] = generators

                log("info", f"  Cycle {cycle}: Re-running reviews...")
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
                log("warning", f"  Cycle {cycle}: iteration failed — stopping")
                break
    else:
        race_json.setdefault("reviews", [])

    elapsed = time.perf_counter() - t0

    # Compute and attach cost estimate (covers all LLMs: OpenAI + review providers)
    _cost_ctx.reset(_ctx_token)
    pt = _acc["prompt_tokens"]
    ct = _acc["completion_tokens"]
    total_tokens = pt + ct
    breakdown = _acc.get("model_breakdown", {})
    total_cost = (
        sum(
            estimate_cost(m, bd.get("prompt_tokens", 0), bd.get("completion_tokens", 0))
            for m, bd in breakdown.items()
        )
        if breakdown
        else estimate_cost(model, pt, ct)
    )
    agent_metrics = {
        "model": model,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": total_tokens,
        "estimated_usd": round(total_cost, 4),
        "model_breakdown": breakdown,
        "duration_s": round(elapsed, 1),
    }
    race_json["agent_metrics"] = agent_metrics
    log(
        "info",
        f"✅ Agent finished in {elapsed:.1f}s — "
        f"${total_cost:.4f} estimated "
        f"({pt:,} in + {ct:,} out = {total_tokens:,} tokens)",
    )

    # Sanity-check: reject partial LLM output (e.g. a stray polling entry)
    _candidates = race_json.get("candidates")
    if not isinstance(_candidates, list):
        raise ValueError(
            f"Agent output for '{race_id}' has no 'candidates' — looks like a partial "
            f"LLM response was returned instead of the full race profile. "
            f"Top-level keys present: {list(race_json.keys())}. Re-queue the race to retry."
        )

    return race_json


# ---------------------------------------------------------------------------
# Per-candidate, per-issue sub-agent
# ---------------------------------------------------------------------------

_HANDOFF_WINDOW = 4  # how many previous issue handoffs to include


def _build_handoff_context(
    handoffs: List[Dict[str, Any]],
    cached_info: Dict[str, Any] | None,
) -> str:
    """Build a handoff context string for the issue sub-agent.

    Includes the last N stances already written and a summary of cached
    search queries / page URLs the sub-agent can freely re-fetch.
    """
    parts: List[str] = []

    # Previous stances written for this candidate
    recent = handoffs[-_HANDOFF_WINDOW:] if handoffs else []
    if recent:
        parts.append("Previous stances already written for this candidate:")
        for h in recent:
            parts.append(f"  - {h['issue']}: {h['stance'][:120]} [{h['confidence']}]")
        parts.append("")

    # Cache-aware section
    if cached_info:
        searches = cached_info.get("searches", [])
        if searches:
            parts.append(f"Cached searches available ({len(searches)} queries — results are free to re-use):")
            for s in searches[:15]:  # cap display to avoid prompt bloat
                urls_str = ", ".join(s["urls"][:3])
                parts.append(f"  - \"{s['query']}\" → {urls_str}")
            parts.append("")

    return "\n".join(parts) if parts else "No prior context available."


async def _run_issue_research_for_candidate(
    candidate_name: str,
    race_json: Dict[str, Any],
    *,
    race_id: str,
    model: str,
    on_log: Any | None = None,
    max_iterations: int = 12,
    is_update: bool = False,
    last_updated: str = "",
) -> None:
    """Run per-issue research for one candidate, mutating race_json in place.

    For each of the canonical issues, a separate tools-mode _agent_loop
    call uses web_search + set_issue_stance. A structured handoff is passed
    between issues so the sub-agent knows what has already been written and
    which search queries are cached.
    """
    log = make_logger(on_log)
    handlers = _make_editing_handlers(race_json, log)
    cache = _get_search_cache()
    cached_info = cache.list_cached_for_race(race_id) if cache else None

    handoffs: List[Dict[str, Any]] = []

    for issue_idx, issue in enumerate(CANONICAL_ISSUES):
        handoff_ctx = _build_handoff_context(handoffs, cached_info)

        # Find existing stance for this candidate/issue (for update mode)
        existing_stance = ""
        if is_update:
            for c in race_json.get("candidates", []):
                if c.get("name") == candidate_name:
                    sd = c.get("issues", {}).get(issue)
                    if isinstance(sd, dict):
                        existing_stance = (
                            f"  Stance: {sd.get('stance', '?')}\n"
                            f"  Confidence: {sd.get('confidence', '?')}\n"
                            f"  Sources: {json.dumps(sd.get('sources', []))}"
                        )
                    else:
                        existing_stance = "  MISSING — no existing stance"
                    break

        if is_update:
            sys_prompt = UPDATE_ISSUE_SUBAGENT_SYSTEM
            usr_prompt = UPDATE_ISSUE_SUBAGENT_USER.format(
                candidate_name=candidate_name,
                race_id=race_id,
                issue=issue,
                last_updated=last_updated,
                existing_stance=existing_stance or "  MISSING",
                handoff_context=handoff_ctx,
            )
        else:
            sys_prompt = ISSUE_SUBAGENT_SYSTEM
            usr_prompt = ISSUE_SUBAGENT_USER.format(
                candidate_name=candidate_name,
                race_id=race_id,
                issue=issue,
                handoff_context=handoff_ctx,
            )

        log("info", f"    Issue {issue_idx + 1}/12: {issue}")

        try:
            await _agent_loop(
                sys_prompt,
                usr_prompt,
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=max_iterations,
                phase_name=f"issue-{candidate_name[:15]}-{issue[:15]}",
                max_tokens=4096,
                extra_tools=ISSUE_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
            )
        except (RuntimeError, ValueError) as exc:
            log("warning", f"    Issue sub-agent failed for {candidate_name}/{issue}: {exc}")

        # Build handoff entry from what was just written
        for c in race_json.get("candidates", []):
            if c.get("name") == candidate_name:
                sd = c.get("issues", {}).get(issue, {})
                handoffs.append({
                    "issue": issue,
                    "stance": sd.get("stance", "(not set)") if isinstance(sd, dict) else "(not set)",
                    "confidence": sd.get("confidence", "?") if isinstance(sd, dict) else "?",
                })
                break

        # Refresh cache info after each issue (new searches may have been cached)
        if cache:
            cached_info = cache.list_cached_for_race(race_id)


# ---------------------------------------------------------------------------
# Fresh run (new race)
# ---------------------------------------------------------------------------


async def _run_fresh(
    race_id: str,
    *,
    model: str,
    small_model: str,
    on_log: Any | None = None,
    max_iterations: int = 15,
) -> Dict[str, Any]:
    """Phase 1 → 2 → 3: Discovery → Issue research → Refinement.

    *model* is used for complex phases (discovery, finance, refinement).
    *small_model* is used for focused sub-tasks (image resolution, per-issue sub-agents).
    """
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

    refine_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=12)
    log("info", f"  Iteration budgets — refine:{refine_iters}  (n={n} candidates)")

    # --- Phase 1b: Image URL verification & resolution (parallel) ---
    log("info", "Phase 1b/3: Verifying and resolving candidate image URLs...")
    await resolve_candidate_images(
        race_json,
        agent_loop_fn=_agent_loop,
        model=small_model,
        on_log=on_log,
        race_id=race_id,
        max_iterations=min(max_iterations, 10),
    )

    # --- Phase 2: Per-candidate, per-issue research (tools mode) ---
    log("info", f"Phase 2/3: Researching issues for {n} candidates (12 issues each)...")
    for cand_name in candidate_names:
        log("info", f"  Researching {cand_name}...")
        await _run_issue_research_for_candidate(
            cand_name,
            race_json,
            race_id=race_id,
            model=small_model,
            on_log=on_log,
            max_iterations=max_iterations,
            is_update=False,
        )

    # --- Phase 2b: Dedicated finance & voting record research ---
    finance_iters = _scale_iterations(max_iterations, n, per_candidate=4, minimum=15)
    log("info", f"Phase 2b: Researching donors & voting records for {n} candidates...")
    try:
        finance_result = await _agent_loop(
            FINANCE_VOTING_SYSTEM,
            FINANCE_VOTING_USER.format(
                race_id=race_id,
                candidate_names=", ".join(candidate_names),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=finance_iters,
            phase_name="finance-voting",
            max_tokens=16384,
        )
        if isinstance(finance_result, dict):
            _apply_finance_patch(race_json, finance_result, log)
        else:
            log("warning", "  Finance/voting phase returned non-dict — skipping")
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Finance/voting phase failed: {exc} — continuing without")

    # --- Phase 3: Refinement (tools mode — per-candidate + meta) ---
    log("info", "Phase 3/3: Refining profile (one candidate at a time, tools mode)...")
    handlers = _make_editing_handlers(race_json, log)
    candidate_names_in_json = [c["name"] for c in race_json.get("candidates", [])]
    for candidate in race_json.get("candidates", []):
        cname = candidate["name"]
        log("info", f"  Refining {cname}...")
        try:
            await _agent_loop(
                REFINE_SYSTEM,
                REFINE_USER.format(
                    race_id=race_id,
                    candidate_name=cname,
                    candidate_json=json.dumps(candidate, indent=2, default=str),
                    race_description=race_json.get("description", ""),
                    other_candidates=", ".join(cn for cn in candidate_names_in_json if cn != cname),
                    all_issues=", ".join(CANONICAL_ISSUES),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=max(8, refine_iters // max(len(candidate_names_in_json), 1)),
                phase_name=f"refine-{cname[:20]}",
                max_tokens=8192,
                extra_tools=CANDIDATE_TOOLS + RECORD_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
            )
        except (RuntimeError, ValueError) as exc:
            log("warning", f"  Refine failed for {cname}: {exc} — keeping existing")

    # Meta refinement (description + polling) — tools mode
    log("info", "  Refining race metadata...")
    try:
        await _agent_loop(
            REFINE_SYSTEM,
            REFINE_META_USER.format(
                race_id=race_id,
                race_description=race_json.get("description", ""),
                polling_json=json.dumps(race_json.get("polling", []), indent=2, default=str),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max(6, refine_iters // 3),
            phase_name="refine-meta",
            max_tokens=4096,
            extra_tools=RACE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
        )
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Refine meta failed: {exc} — keeping existing meta")

    return race_json


# ---------------------------------------------------------------------------
# Update run (existing race)
# ---------------------------------------------------------------------------


async def _run_update(
    race_id: str,
    existing: Dict[str, Any],
    *,
    model: str,
    small_model: str,
    on_log: Any | None = None,
    max_iterations: int = 15,
) -> Dict[str, Any]:
    """Phase-based update mirroring _run_fresh but starting from existing data.

    *model* is used for complex phases (meta update, finance, refinement).
    *small_model* is used for focused sub-tasks (roster sync, per-issue sub-agents, images).
    """
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
        return await _run_fresh(race_id, model=model, small_model=small_model, on_log=on_log, max_iterations=max_iterations)

    refine_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=12)
    handlers = _make_editing_handlers(race_json, log)

    # --- Phase 0: Roster sync (tools mode) ---
    log("info", "Update Phase 0: Verifying candidate roster...")
    try:
        await _agent_loop(
            ROSTER_SYNC_SYSTEM,
            ROSTER_SYNC_USER.format(
                race_id=race_id,
                last_updated=last_updated,
                candidate_names=", ".join(candidate_names),
            ),
            model=small_model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max(8, max_iterations // 2),
            phase_name="roster-sync",
            max_tokens=4096,
            extra_tools=ROSTER_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
        )
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Roster sync failed: {exc} — keeping existing roster")

    # Refresh candidate names after roster sync (may have changed)
    candidate_names = [c["name"] for c in race_json.get("candidates", [])]
    n = len(candidate_names)

    if not candidate_names:
        log("warning", "No candidates after roster sync — falling back to fresh run")
        return await _run_fresh(race_id, model=model, small_model=small_model, on_log=on_log, max_iterations=max_iterations)

    # --- Phase 1: Meta update (tools mode — summaries, polls, race fields) ---
    meta_iters = _scale_iterations(max_iterations, n, per_candidate=2, minimum=10)
    log("info", "Update Phase 1: Searching for new summaries, donors, polls, voting records...")
    try:
        await _agent_loop(
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
            extra_tools=RACE_TOOLS + CANDIDATE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
        )
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Update meta phase failed: {exc} — keeping existing meta")

    # --- Phase 2: Per-candidate, per-issue research (tools mode) ---
    log("info", f"Update Phase 2: Refreshing issue positions for {n} candidates (12 issues each)...")
    for cand_name in candidate_names:
        log("info", f"  Updating issues for {cand_name}...")
        await _run_issue_research_for_candidate(
            cand_name,
            race_json,
            race_id=race_id,
            model=small_model,
            on_log=on_log,
            max_iterations=max_iterations,
            is_update=True,
            last_updated=last_updated,
        )

    # --- Phase 2b: Dedicated finance & voting record refresh ---
    finance_iters = _scale_iterations(max_iterations, n, per_candidate=4, minimum=15)
    log("info", f"Update Phase 2b: Refreshing donors & voting records for {n} candidates...")
    try:
        finance_result = await _agent_loop(
            FINANCE_VOTING_SYSTEM,
            FINANCE_VOTING_USER.format(
                race_id=race_id,
                candidate_names=", ".join(candidate_names),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=finance_iters,
            phase_name="update-finance-voting",
            max_tokens=16384,
        )
        if isinstance(finance_result, dict):
            _apply_finance_patch(race_json, finance_result, log)
        else:
            log("warning", "  Finance/voting phase returned non-dict — skipping")
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Finance/voting phase failed: {exc} — continuing without")

    # --- Phase 3: Refinement (tools mode — per-candidate + meta) ---
    log("info", "Update Phase 3: Refining updated profile (one candidate at a time, tools mode)...")
    cand_list = race_json.get("candidates", [])
    for candidate in cand_list:
        cname = candidate["name"]
        log("info", f"  Refining {cname}...")
        try:
            await _agent_loop(
                REFINE_SYSTEM,
                REFINE_USER.format(
                    race_id=race_id,
                    candidate_name=cname,
                    candidate_json=json.dumps(candidate, indent=2, default=str),
                    race_description=race_json.get("description", ""),
                    other_candidates=", ".join(c["name"] for c in cand_list if c["name"] != cname),
                    all_issues=", ".join(CANONICAL_ISSUES),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=max(8, refine_iters // max(len(cand_list), 1)),
                phase_name=f"upd-refine-{cname[:20]}",
                max_tokens=8192,
                extra_tools=CANDIDATE_TOOLS + RECORD_TOOLS + [READ_PROFILE_TOOL],
                extra_tool_handlers=handlers,
                tools_mode=True,
            )
        except (RuntimeError, ValueError) as exc:
            log("warning", f"  Refine failed for {cname}: {exc} — keeping existing")

    # Meta refinement (description + polling) — tools mode
    log("info", "  Refining race metadata...")
    try:
        await _agent_loop(
            REFINE_SYSTEM,
            REFINE_META_USER.format(
                race_id=race_id,
                race_description=race_json.get("description", ""),
                polling_json=json.dumps(race_json.get("polling", []), indent=2, default=str),
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max(6, refine_iters // 3),
            phase_name="upd-refine-meta",
            max_tokens=4096,
            extra_tools=RACE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
        )
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Refine meta failed: {exc} — keeping existing meta")

    # --- Post-update: image URL verification ---
    log("info", "Post-update: Verifying and resolving candidate image URLs...")
    await resolve_candidate_images(
        race_json,
        agent_loop_fn=_agent_loop,
        model=small_model,
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


def _apply_candidate_patch(candidate: Dict[str, Any], patch: Dict[str, Any], log: Any) -> None:
    """Merge a per-candidate patch dict into the candidate in-place.

    Simple fields (summary, image_url, website) are overwritten.
    List fields (career_history, education, voting_record, top_donors) replace
    the existing list only when the patch list is non-empty.
    Issues are merged key-by-key.
    summary_sources replaces the existing array when non-empty.
    """
    cname = candidate.get("name", "?")
    for key in ("summary", "image_url", "website", "incumbent", "party"):
        if key in patch:
            candidate[key] = patch[key]
    for key in ("summary_sources", "career_history", "education", "top_donors"):
        val = patch.get(key)
        if isinstance(val, list) and val:
            candidate[key] = val
    # voting_record — deduplicate by bill_name
    new_votes = patch.get("voting_record")
    if isinstance(new_votes, list) and new_votes:
        existing_vr = {v.get("bill_name"): v for v in candidate.get("voting_record", [])}
        for vote in new_votes:
            existing_vr[vote.get("bill_name", "")] = vote
        candidate["voting_record"] = list(existing_vr.values())
    # Issues — merge key-by-key
    new_issues = patch.get("issues")
    if isinstance(new_issues, dict) and new_issues:
        candidate.setdefault("issues", {}).update(new_issues)
    log("debug", f"  Candidate patch applied for {cname}")


def _apply_refine_patch(race_json: Dict[str, Any], meta_patch: Dict[str, Any],
                        candidate_patches: List[Dict[str, Any]], log: Any,
                        iteration_notes: List[str]) -> None:
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

        # Merge donors — replace if the new data has more entries, then deduplicate
        new_donors = data.get("top_donors", [])
        if isinstance(new_donors, list) and new_donors:
            existing_donors = candidate.get("top_donors", [])
            if len(new_donors) >= len(existing_donors):
                candidate["top_donors"] = new_donors
            else:
                # Append new ones not already present
                existing_names = {d.get("name", "").lower() for d in existing_donors}
                for d in new_donors:
                    if d.get("name", "").lower() not in existing_names:
                        existing_donors.append(d)
                candidate["top_donors"] = existing_donors
            # Deduplicate donors by name (keep highest amount)
            candidate["top_donors"] = _deduplicate_donors(candidate["top_donors"])

        # Merge voting records — deduplicate by bill_name
        new_votes = data.get("voting_record", [])
        if isinstance(new_votes, list) and new_votes:
            existing_vr = {v.get("bill_name"): v for v in candidate.get("voting_record", [])}
            for vote in new_votes:
                existing_vr[vote.get("bill_name", "")] = vote
            candidate["voting_record"] = list(existing_vr.values())

        # Merge new scalar fields
        if data.get("voting_summary"):
            candidate["voting_summary"] = data["voting_summary"]
        if data.get("voting_source_url"):
            candidate["voting_source_url"] = data["voting_source_url"]
        if data.get("donor_source_url"):
            candidate["donor_source_url"] = data["donor_source_url"]

        updated += 1
    log("info", f"  Finance/voting patch applied — {updated} candidates updated")


def _deduplicate_donors(donors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate donors by lowercased name, keeping the entry with the highest amount."""
    best: Dict[str, Dict[str, Any]] = {}
    for d in donors:
        key = d.get("name", "").strip().lower()
        if not key:
            continue
        existing = best.get(key)
        if existing is None:
            best[key] = d
        else:
            # Keep whichever has the higher amount (treat None as 0)
            new_amt = d.get("amount") or 0
            old_amt = existing.get("amount") or 0
            if new_amt > old_amt:
                best[key] = d
    return list(best.values())


def _format_review_flags(reviews: List[Dict[str, Any]]) -> str:
    """Format review flags into a readable text block for the iteration prompt."""
    lines = []
    for review in reviews:
        model = review.get("model", "unknown")
        verdict = review.get("verdict", "unknown")
        lines.append(f"\n--- Review by {model} (verdict: {verdict}) ---")
        if review.get("summary"):
            lines.append(f"Summary: {review['summary']}")
        for flag in review.get("flags", []):
            severity = flag.get("severity", "info").upper()
            field = flag.get("field", "?")
            concern = flag.get("concern", "")
            suggestion = flag.get("suggestion", "")
            lines.append(f"  [{severity}] {field}: {concern}")
            if suggestion:
                lines.append(f"    Suggestion: {suggestion}")
    return "\n".join(lines) if lines else "  (no specific flags)"


def _has_actionable_flags(
    reviews: List[Dict[str, Any]],
    min_severity: str = "warning",
    exclude_fields: set | None = None,
) -> bool:
    """Return True if any review has actionable flags at or above *min_severity*.

    *exclude_fields* is a set of field paths to skip (already dismissed).
    """
    severity_rank = {"info": 0, "warning": 1, "error": 2}
    threshold = severity_rank.get(min_severity, 1)
    _excluded = exclude_fields or set()
    for review in reviews:
        for flag in review.get("flags", []):
            rank = severity_rank.get(flag.get("severity", "info"), 0)
            if rank >= threshold and flag.get("field", "") not in _excluded:
                return True
    return False


async def _run_iteration_pass(
    race_id: str,
    race_json: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    *,
    model: str,
    on_log: Any | None = None,
    max_iterations: int = 20,
) -> Optional[Dict[str, Any]]:
    """Run a single iteration pass addressing review flags (tools mode).

    Uses the full editing toolkit so the LLM can directly fix flagged issues.
    Returns the improved race_json (same object, modified), or None if
    every call fails.
    """
    import copy
    log = make_logger(on_log)

    flags_text = _format_review_flags(reviews)
    candidates = race_json.get("candidates", [])
    n = len(candidates)
    iterate_iters = _scale_iterations(max_iterations, n, per_candidate=3, minimum=12)
    iters_per_cand = max(6, iterate_iters // max(n, 1))

    log("info", f"  Iteration: addressing review flags for {n} candidates (tools mode)")

    working = copy.deepcopy(race_json)
    handlers = _make_editing_handlers(working, log)
    all_tools = ROSTER_TOOLS + CANDIDATE_TOOLS + ISSUE_TOOLS + RECORD_TOOLS + RACE_TOOLS + [READ_PROFILE_TOOL]
    any_success = False

    # Per-candidate iteration
    for candidate in working.get("candidates", []):
        cname = candidate["name"]
        log("info", f"  Iterating on {cname}...")
        try:
            await _agent_loop(
                ITERATE_SYSTEM,
                ITERATE_USER.format(
                    race_id=race_id,
                    candidate_name=cname,
                    candidate_json=json.dumps(candidate, indent=2, default=str),
                    review_flags=flags_text,
                    all_issues=", ".join(CANONICAL_ISSUES),
                ),
                model=model,
                on_log=on_log,
                race_id=race_id,
                max_iterations=iters_per_cand,
                phase_name=f"iterate-{cname[:20]}",
                max_tokens=8192,
                extra_tools=all_tools,
                extra_tool_handlers=handlers,
                tools_mode=True,
            )
            any_success = True
        except (RuntimeError, ValueError) as exc:
            log("warning", f"  Iteration failed for {cname}: {exc} — keeping existing")

    # Meta iteration (description + polling flags)
    log("info", "  Iterating on race metadata...")
    try:
        await _agent_loop(
            ITERATE_SYSTEM,
            ITERATE_META_USER.format(
                race_id=race_id,
                race_description=working.get("description", ""),
                polling_json=json.dumps(working.get("polling", []), indent=2, default=str),
                review_flags=flags_text,
            ),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max(5, iters_per_cand // 2),
            phase_name="iterate-meta",
            max_tokens=4096,
            extra_tools=RACE_TOOLS + [READ_PROFILE_TOOL],
            extra_tool_handlers=handlers,
            tools_mode=True,
        )
        any_success = True
    except (RuntimeError, ValueError) as exc:
        log("warning", f"  Iteration meta failed: {exc} — keeping existing meta")

    if not any_success:
        log("warning", "  All iteration calls failed — keeping original")
        return None

    working.setdefault("id", race_id)
    return working
