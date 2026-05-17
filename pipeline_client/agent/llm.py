"""OpenAI client, chat-completions wrapper, agent loop, and data normalisation."""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .ballotpedia import lookup_candidate_data as _ballotpedia_lookup
from .ballotpedia import lookup_election_page as _ballotpedia_election_lookup
from .cost import CHEAP_MODEL, DEFAULT_MODEL, NANO_MODEL, accumulate
from .tools import BALLOTPEDIA_ELECTION_TOOL, BALLOTPEDIA_TOOL, FETCH_TOOL, SEARCH_TOOL
from .utils import _extract_json, make_logger
from .web_tools import _fetch_page, _page_fetch_log_hint, _serper_search

logger = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# OpenAI client singleton
# ---------------------------------------------------------------------------

_openai_client: Any = None


def _get_openai_client() -> Any:
    """Return (and lazily create) the shared AsyncOpenAI client."""
    global _openai_client
    from openai import AsyncOpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    existing_key = getattr(_openai_client, "api_key", None)
    if _openai_client is None or existing_key != api_key:
        _openai_client = AsyncOpenAI(api_key=api_key, max_retries=0, timeout=300)

    return _openai_client


# ---------------------------------------------------------------------------
# Chat-completions wrapper with retry
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
    400 bad-request errors: raised immediately as RuntimeError (unretryable).
    The Retry-After response header always takes precedence.

    Policy violation errors (400 with "policy" in message) are attempted once
    more with simplified messaging; if still rejected, fail with clear error.

    Returns an ``openai.types.chat.ChatCompletion`` object.
    """
    from openai import APIConnectionError, APIStatusError, APITimeoutError, BadRequestError, RateLimitError

    client = _get_openai_client()

    _supports_temperature = not (model.startswith("o1") or model.startswith("o3") or model.startswith("o4") or "nano" in model)
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_tokens,
    }
    if _supports_temperature:
        kwargs["temperature"] = 0.2
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    for attempt in range(max_retries):
        try:
            resp = await client.chat.completions.create(**kwargs)
            if resp.usage:
                accumulate(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0, model)
            return resp
        except BadRequestError as exc:
            error_str = str(exc)
            is_policy_violation = "policy" in error_str.lower() or "invalid_prompt" in error_str.lower()

            if is_policy_violation and attempt == 0:
                logger.warning(
                    f"OpenAI policy violation (400) for model={model}: {exc}\n"
                    f"Attempting one retry with simplified prompt..."
                )
                simplified_msgs = [
                    m for i, m in enumerate(messages) if i < 2 or (i == len(messages) - 1 and m.get("role") == "user")
                ]
                if len(simplified_msgs) < len(messages):
                    kwargs["messages"] = simplified_msgs
                    try:
                        resp = await client.chat.completions.create(**kwargs)
                        if resp.usage:
                            accumulate(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0, model)
                        logger.warning("Simplified prompt accepted; continuing.")
                        return resp
                    except BadRequestError as retry_exc:
                        logger.error(f"OpenAI policy violation persists even with simplified prompt for {model}: {retry_exc}")
                        raise RuntimeError(f"OpenAI policy violation (unrecoverable): {exc}") from retry_exc

            logger.error(
                f"OpenAI bad request (400) for model={model}: {exc}" f"{' (policy violation)' if is_policy_violation else ''}"
            )
            raise RuntimeError(f"OpenAI bad request: {exc}") from exc
        except RateLimitError as exc:
            if attempt >= max_retries - 1:
                raise
            retry_after = 0
            if exc.response is not None:
                retry_after = int(exc.response.headers.get("retry-after", 0))
            backoff = min(600, 30 * (2**attempt))
            wait = max(retry_after, backoff)
            logger.warning(f"OpenAI 429, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait)
        except APIStatusError as exc:
            if attempt >= max_retries - 1 or exc.status_code < 500:
                raise
            backoff = 2 ** (attempt + 1)
            logger.warning(f"OpenAI {exc.status_code}, retrying in {backoff}s " f"(attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(backoff)
        except (APIConnectionError, APITimeoutError) as exc:
            if attempt >= max_retries - 1:
                raise
            backoff = min(60, 2 ** (attempt + 1))
            logger.warning(f"OpenAI connection error, retrying in {backoff}s " f"(attempt {attempt + 1}/{max_retries}): {exc}")
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
    candidate.setdefault("donor_summary", None)
    candidate.setdefault("donor_sources", [])
    candidate.setdefault("links", [])

    if candidate.get("image_url") == "":
        candidate["image_url"] = None

    for issue_data in candidate.get("issues", {}).values():
        if isinstance(issue_data, dict):
            for src in issue_data.get("sources", []):
                _normalize_source(src, now_iso)

    for entry in candidate.get("career_history", []):
        if isinstance(entry, dict):
            _normalize_source(entry.get("source"), now_iso)

    for entry in candidate.get("education", []):
        if isinstance(entry, dict):
            _normalize_source(entry.get("source"), now_iso)

    for src in candidate.get("donor_sources", []):
        _normalize_source(src, now_iso)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _ensure_dict(result: Any, phase_name: str, log: Any) -> Dict[str, Any]:
    """Unwrap a single-element list or raise if the result is not a dict."""
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
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
    _json_parse_failures = 0
    _MAX_JSON_RETRIES = 3

    for iteration in range(max_iterations):
        log("info", f"  [{phase_name}] iteration {iteration + 1}/{max_iterations} — calling {model}...")

        if tools_mode:
            search_tools = (
                [SEARCH_TOOL, FETCH_TOOL, BALLOTPEDIA_TOOL, BALLOTPEDIA_ELECTION_TOOL] if iteration < nudge_at else []
            )
            tools_for_call = search_tools + _extra_tools if (search_tools or _extra_tools) else None

            if iteration == nudge_at and len(messages) > 2:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You have used several searches. Stop searching and use your "
                            "editing tools to commit your findings now. When you are done "
                            "editing, make no further tool calls — do not produce a text reply."
                        ),
                    }
                )
                log("info", f"  [{phase_name}] nudging model to commit edits (iteration {iteration + 1})")
        else:
            if iteration == nudge_at and len(messages) > 2:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You have used several searches. Please now compile your findings "
                            "and return ONLY the final JSON response. No more searches."
                        ),
                    }
                )
                log("info", f"  [{phase_name}] nudging model to produce output (iteration {iteration + 1})")

            base_tools = [SEARCH_TOOL, FETCH_TOOL, BALLOTPEDIA_TOOL, BALLOTPEDIA_ELECTION_TOOL] if iteration < nudge_at else []
            tools_for_call = (base_tools + _extra_tools) if (base_tools or _extra_tools) else None

        t_call = time.perf_counter()
        try:
            result = await _call_openai(messages, model=model, tools=tools_for_call, max_tokens=max_tokens)
        except RuntimeError as e:
            if "policy violation" in str(e).lower():
                log("error", f"  [{phase_name}] policy violation detected; exiting iteration loop")
                raise
            raise
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
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(search_results),
                        }
                    )
                elif fn.name == "fetch_page":
                    args = json.loads(fn.arguments)
                    url = args.get("url", "")
                    log("info", f"    📄 fetching {url[:80]}")
                    page_text = await _fetch_page(url)
                    log("debug", f"    📄 got {len(page_text)} chars")
                    fetch_hint = _page_fetch_log_hint(url, page_text)
                    if fetch_hint:
                        log("warning", f"    📄 {fetch_hint}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": page_text,
                        }
                    )
                elif fn.name == "ballotpedia_lookup":
                    args = json.loads(fn.arguments)
                    candidate_name = args.get("candidate_name", "")
                    log("info", f"    📋 Ballotpedia lookup: {candidate_name}")
                    bp_data = await _ballotpedia_lookup(candidate_name)
                    log("debug", f"    📋 found={bp_data.get('found')}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(bp_data),
                        }
                    )
                elif fn.name == "ballotpedia_election_lookup":
                    args = json.loads(fn.arguments)
                    election_race_id = args.get("race_id", race_id or "")
                    log("info", f"    🗳️  Ballotpedia election lookup: {election_race_id}")
                    election_data = await _ballotpedia_election_lookup(election_race_id)
                    n_found = len(election_data.get("candidates", []))
                    log("debug", f"    🗳️  found={election_data.get('found')} candidates={n_found}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(election_data),
                        }
                    )
                elif fn.name in _extra_handlers:
                    args = json.loads(fn.arguments)
                    log("info", f"    🔧 {fn.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
                    try:
                        handler_result = _extra_handlers[fn.name](args)
                        log("info", f"    🔧 {fn.name} → OK")
                    except Exception as exc:
                        handler_result = f"Error: {exc}"
                        log("warning", f"    🔧 {fn.name} → {exc}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(handler_result),
                        }
                    )
                else:
                    log("warning", f"    ⚠️ Unknown tool: {fn.name}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Error: unknown tool '{fn.name}'",
                        }
                    )
            continue

        # No tool calls — in tools_mode this means the LLM is done editing
        if tools_mode:
            log("info", f"  [{phase_name}] tools-mode complete (no more tool calls)")
            return {}

        # Normal json mode — try to parse the answer
        content = message.content or ""

        if finish_reason == "length":
            log("warning", f"  [{phase_name}] response truncated (finish_reason=length) — retrying with brevity prompt")
            messages.append(message.model_dump())
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response was cut off because it was too long. "
                        "Please return a shorter JSON object. Use concise string values "
                        "(under 200 characters each), omit optional or redundant fields, "
                        "and return ONLY the JSON with no markdown fences or extra text."
                    ),
                }
            )
            continue

        try:
            parsed = _extract_json(content)
            log("info", f"  [{phase_name}] JSON parsed OK")
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            _json_parse_failures += 1
            if _json_parse_failures >= _MAX_JSON_RETRIES:
                raise RuntimeError(
                    f"[{phase_name}] failed to produce valid JSON after " f"{_json_parse_failures} attempts. Last error: {exc}"
                )
            log("warning", f"  [{phase_name}] bad JSON ({exc}) — retry {_json_parse_failures}/{_MAX_JSON_RETRIES}")
            messages.append(message.model_dump())
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your response was not valid JSON. Parse error: {exc}. "
                        "Common causes: using None/True/False instead of null/true/false, "
                        "unescaped quotes or backslashes inside string values, or text "
                        "appended after the closing brace. "
                        "Return ONLY the raw JSON object — no markdown, no explanation, "
                        "no trailing text whatsoever."
                    ),
                }
            )
            continue

    if tools_mode:
        log("warning", f"  [{phase_name}] tools-mode hit max iterations — returning")
        return {}
    raise RuntimeError(f"[{phase_name}] did not produce output within {max_iterations} iterations")
