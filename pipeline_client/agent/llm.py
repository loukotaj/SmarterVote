"""OpenRouter client, chat-completions wrapper, agent loop, and data normalisation."""

import asyncio
import json
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

from .ballotpedia import lookup_candidate_data as _ballotpedia_lookup
from .ballotpedia import lookup_election_page as _ballotpedia_election_lookup
from .context import AgentContext, AgentContextBudget
from .cost import (
    accumulate,
    record_context_metrics,
    record_retry_metric,
    record_token_budget_nudge,
    set_current_phase,
    total_token_budget_reached,
)
from .errors import PermanentProviderError, RetryableProviderError
from .model_registry import escalation_for, normalize_model_id
from .roster_adjudicator import collect_roster_adjudications
from .run_budget import RunBudget
from .source_types import normalize_source_type
from .tools import BALLOTPEDIA_ELECTION_TOOL, BALLOTPEDIA_TOOL, FETCH_TOOL, IMAGE_SEARCH_TOOL, SEARCH_TOOL
from .utils import _extract_json, make_logger
from .web_tools import _fetch_page, _page_fetch_log_hint, _serper_image_search, _serper_search

logger = logging.getLogger("pipeline")


#: How many times to re-issue a call that came back with finish_reason "error"
#: and no content. Two is enough for a transient upstream blip without letting a
#: persistently failing provider stall the loop.
PROVIDER_ERROR_RETRIES = 2


def _tool_result_is_error(result: Any) -> bool:
    return isinstance(result, str) and result.lstrip().casefold().startswith(("error:", "blocked", "failed"))


def _provider_usage_cost(usage: Any) -> Optional[float]:
    """Read OpenRouter's billed cost from SDK-known or extra usage fields."""
    if usage is None:
        return None
    value = getattr(usage, "cost", None)
    if value is None:
        extra = getattr(usage, "model_extra", None)
        if isinstance(extra, dict):
            value = extra.get("cost")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _accumulate_usage(resp: Any, model: str) -> None:
    usage = getattr(resp, "usage", None)
    if usage:
        accumulate(
            usage.prompt_tokens or 0,
            usage.completion_tokens or 0,
            model,
            cost_usd=_provider_usage_cost(usage),
        )


# ---------------------------------------------------------------------------
# OpenRouter client singleton
# ---------------------------------------------------------------------------

_openrouter_client: Any = None
_DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 240.0
_DEFAULT_LLM_RATE_LIMIT_MAX_RETRIES = 3
_DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS = 60


def _get_openrouter_client() -> Any:
    """Return (and lazily create) the shared OpenRouter AsyncOpenAI client."""
    global _openrouter_client
    from openai import AsyncOpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    existing_key = getattr(_openrouter_client, "api_key", None)
    if _openrouter_client is None or existing_key != api_key:
        _openrouter_client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            max_retries=0,
            timeout=300,
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://smarter.vote"),
                "X-Title": os.getenv("OPENROUTER_APP_TITLE", "SmarterVote"),
            },
        )

    return _openrouter_client


def _openrouter_request_timeout_seconds() -> float:
    raw = os.getenv("OPENROUTER_REQUEST_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        logger.warning("Invalid LLM request timeout=%r; using default", raw)
        return _DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS
    return max(30.0, timeout)


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


async def _create_chat_completion(
    client: Any,
    kwargs: Dict[str, Any],
    *,
    run_budget: RunBudget | None = None,
):
    """Wrap SDK requests in an explicit asyncio timeout.

    The OpenAI SDK has its own timeout, but long-running Cloud Run workers have
    previously observed stalled awaits with no retry log. An outer timeout keeps
    pipeline queue items from remaining active indefinitely.
    """
    timeout = _openrouter_request_timeout_seconds()
    if run_budget:
        timeout = run_budget.bounded_timeout(timeout, minimum_seconds=5.0, operation="OpenRouter request")
    return await asyncio.wait_for(client.chat.completions.create(**kwargs), timeout=timeout)


async def _await_with_run_budget(
    awaitable: Any,
    *,
    run_budget: RunBudget | None,
    requested_timeout: float,
    operation: str,
    timeout_result: Any,
) -> Any:
    """Await a tool request and turn isolated tool timeouts into model-visible failures."""
    timeout = requested_timeout
    if run_budget:
        timeout = run_budget.bounded_timeout(requested_timeout, minimum_seconds=2.0, operation=operation)
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except asyncio.TimeoutError:
        record_retry_metric("deadline_exits")
        logger.warning("%s timed out after %.1fs; continuing the agent loop", operation, timeout)
        return timeout_result


# ---------------------------------------------------------------------------
# Chat-completions wrapper with retry
# ---------------------------------------------------------------------------


async def _call_openrouter(
    messages: List[Dict[str, Any]],
    *,
    model: str,
    tools: List[Dict[str, Any]] | None = None,
    tool_choice: Any = None,
    max_retries: int = 3,
    max_tokens: int = 16384,
    run_budget: RunBudget | None = None,
    temperature: float | None = None,
):
    """Call OpenRouter's OpenAI-compatible Chat Completions API with retry.

    429 rate-limit: exponential backoff starting at 30 s, capped at 10 min.
    5xx transient errors: shorter exponential backoff (2, 4, 8 … s).
    400 bad-request errors: raised immediately as RuntimeError (unretryable).
    The Retry-After response header always takes precedence.

    Policy violation errors (400 with "policy" in message) are attempted once
    more with simplified messaging; if still rejected, fail with clear error.

    *temperature* overrides the default for callers that need reproducibility
    rather than the usual light sampling — the roster adjudicator gates
    publication, so it asks for 0. Ignored for models that reject the parameter.

    Returns an ``openai.types.chat.ChatCompletion`` object.
    """
    from openai import APIConnectionError, APIStatusError, APITimeoutError, BadRequestError, RateLimitError

    client = _get_openrouter_client()
    model = normalize_model_id(model) or model

    _supports_temperature = not (model.startswith("o1") or model.startswith("o3") or model.startswith("o4") or "nano" in model)
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if _supports_temperature:
        kwargs["temperature"] = 0.2 if temperature is None else temperature
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"

    rate_limit_wait = 0.0
    transient_wait = 0.0
    for attempt in range(max_retries):
        try:
            if run_budget:
                run_budget.require_call_time(5.0, operation="OpenRouter request")
            resp = await _create_chat_completion(client, kwargs, run_budget=run_budget)
            _accumulate_usage(resp, model)
            return resp
        except BadRequestError as exc:
            error_str = str(exc)
            is_policy_violation = "policy" in error_str.lower() or "invalid_prompt" in error_str.lower()

            if is_policy_violation and attempt == 0:
                logger.warning(
                    f"OpenRouter policy violation (400) for model={model}: {exc}\n"
                    f"Attempting one retry with simplified prompt..."
                )
                simplified_msgs = [
                    m for i, m in enumerate(messages) if i < 2 or (i == len(messages) - 1 and m.get("role") == "user")
                ]
                if len(simplified_msgs) < len(messages):
                    kwargs["messages"] = simplified_msgs
                    try:
                        resp = await _create_chat_completion(client, kwargs, run_budget=run_budget)
                        _accumulate_usage(resp, model)
                        logger.warning("Simplified prompt accepted; continuing.")
                        return resp
                    except BadRequestError as retry_exc:
                        logger.error(
                            f"OpenRouter policy violation persists even with simplified prompt for {model}: {retry_exc}"
                        )
                        raise PermanentProviderError(
                            "OpenRouter rejected the simplified prompt due to content policy",
                            provider="openrouter",
                            code="policy_violation",
                        ) from retry_exc

            logger.error(
                f"OpenRouter bad request (400) for model={model}: {exc}"
                f"{' (policy violation)' if is_policy_violation else ''}"
            )
            raise PermanentProviderError(
                "OpenRouter rejected the request",
                provider="openrouter",
                code="bad_request",
            ) from exc
        except RateLimitError as exc:
            rate_limit_max_retries = min(
                max_retries,
                _env_int("OPENROUTER_RATE_LIMIT_MAX_RETRIES", _DEFAULT_LLM_RATE_LIMIT_MAX_RETRIES, minimum=0),
            )
            if attempt >= rate_limit_max_retries or attempt >= max_retries - 1:
                raise RetryableProviderError(
                    "OpenRouter rate limit retry budget exhausted",
                    provider="openrouter",
                    code="rate_limited",
                ) from exc
            max_wait = _env_int(
                "OPENROUTER_RATE_LIMIT_MAX_WAIT_SECONDS",
                _DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
                minimum=1,
            )
            retry_after = 0
            if exc.response is not None:
                retry_after = int(exc.response.headers.get("retry-after", 0))
            backoff = min(max_wait, 30 * (2**attempt))
            wait = min(max(retry_after, backoff), max_wait, max(0.0, 90.0 - rate_limit_wait))
            wait = min(wait * random.uniform(0.8, 1.2), max_wait, max(0.0, 90.0 - rate_limit_wait))
            if wait <= 0:
                raise
            if run_budget:
                wait = run_budget.bounded_sleep(wait, operation="OpenRouter rate-limit retry")
            rate_limit_wait += wait
            record_retry_metric("rate_limits")
            logger.warning(f"OpenRouter 429, retrying in {wait}s (attempt {attempt + 1}/{rate_limit_max_retries + 1})")
            await asyncio.sleep(wait)
        except APIStatusError as exc:
            if exc.status_code < 500:
                # 401/403 are almost always an exhausted or invalid API key, not a
                # malformed request — classify them distinctly so run-health
                # reporting can tell "we're out of credit" apart from other
                # permanent 4xx failures.
                if exc.status_code in (401, 403):
                    raise PermanentProviderError(
                        f"OpenRouter returned HTTP {exc.status_code} (auth/quota failure)",
                        provider="openrouter",
                        code="auth_failure",
                    ) from exc
                raise PermanentProviderError(
                    f"OpenRouter returned HTTP {exc.status_code}",
                    provider="openrouter",
                    code="request_rejected",
                ) from exc
            if attempt >= max_retries - 1:
                raise RetryableProviderError(
                    f"OpenRouter HTTP {exc.status_code} retry budget exhausted",
                    provider="openrouter",
                    code="provider_unavailable",
                ) from exc
            backoff = min(60.0 - transient_wait, (2 ** (attempt + 1)) * random.uniform(0.8, 1.2))
            if backoff <= 0:
                raise
            if run_budget:
                backoff = run_budget.bounded_sleep(backoff, operation="OpenRouter provider retry")
            transient_wait += backoff
            record_retry_metric("provider_failures")
            logger.warning(f"OpenRouter {exc.status_code}, retrying in {backoff}s " f"(attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(backoff)
        except (APIConnectionError, APITimeoutError, asyncio.TimeoutError) as exc:
            if attempt >= max_retries - 1:
                raise RetryableProviderError(
                    "OpenRouter connection retry budget exhausted",
                    provider="openrouter",
                    code="connection_failed",
                ) from exc
            backoff = min(60.0 - transient_wait, (2 ** (attempt + 1)) * random.uniform(0.8, 1.2))
            if backoff <= 0:
                raise
            if run_budget:
                backoff = run_budget.bounded_sleep(backoff, operation="OpenRouter connection retry")
            transient_wait += backoff
            record_retry_metric("provider_failures")
            logger.warning(
                f"OpenRouter connection error, retrying in {backoff}s " f"(attempt {attempt + 1}/{max_retries}): {exc}"
            )
            await asyncio.sleep(backoff)

    raise RuntimeError("OpenRouter: max retries exceeded")


# ---------------------------------------------------------------------------
# Candidate data normalisation
# ---------------------------------------------------------------------------


def _normalize_source(source: Any, now_iso: str) -> None:
    """Apply required defaults to a single source object in-place."""
    if isinstance(source, dict):
        source.setdefault("last_accessed", now_iso)
        source["type"] = normalize_source_type(source.get("type"), url=str(source.get("url") or ""))


def _normalize_candidate(candidate: Dict[str, Any], now_iso: str) -> None:
    """Apply output defaults and source normalisation to a candidate."""
    candidate.setdefault("image_url", None)
    candidate.setdefault("career_history", [])
    candidate.setdefault("education", [])
    candidate.setdefault("donor_summary", None)
    candidate.setdefault("donor_sources", [])
    candidate.setdefault("voting_sources", [])
    candidate.setdefault("links", [])

    if candidate.get("image_url") == "":
        candidate["image_url"] = None

    for src in candidate.get("summary_sources", []):
        _normalize_source(src, now_iso)

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

    for src in candidate.get("voting_sources", []):
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
    contest_label: Optional[str] = None,
    max_iterations: int = 15,
    phase_name: str = "",
    max_tokens: int = 16384,
    extra_tools: List[Dict[str, Any]] | None = None,
    extra_tool_handlers: Dict[str, Any] | None = None,
    tools_mode: bool = False,
    run_budget: RunBudget | None = None,
    max_request_retries: int = 3,
    allow_search_tools: bool = True,
    return_tool_trace: bool = False,
    required_final_tool_name: str | None = None,
    required_final_instruction: str = "",
    escalate_on_tool_errors: bool = False,
) -> Dict[str, Any]:
    """Run a single agent loop.

    In normal (json) mode: search → answer → parse JSON.
    In tools_mode: the LLM uses editing tools to mutate state directly;
    the loop exits when the LLM stops making tool calls.  Returns ``{}``.

    ``escalate_on_tool_errors`` asks for a climb to a stronger model after
    repeated blocked edits. Callers say *whether* to escalate, never *to what*:
    the target comes from :data:`shared.model_catalog.MODEL_ESCALATION`, keyed on
    whatever model this loop is actually running. Naming a target at the call
    site is how every phase ended up escalating to nemotron-3-ultra regardless
    of profile — a model 12 index points weaker than the default research model
    it was supposedly rescuing.
    """
    log = make_logger(on_log)
    set_current_phase(phase_name)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    context_budget = AgentContextBudget.for_model(
        model,
        phase_name=phase_name,
        max_iterations=max_iterations,
        max_output_tokens=max_tokens,
    )
    context = AgentContext(context_budget, task_text=f"{system}\n{user}")

    nudge_at = max(int(max_iterations / 1.5), 3)
    _extra_tools = extra_tools or []
    _extra_handlers = extra_tool_handlers or {}
    _json_parse_failures = 0
    _MAX_JSON_RETRIES = 3
    token_budget_nudged = False
    required_final_tool_succeeded = False
    consecutive_tool_errors = 0
    tool_errors_escalated = False
    # Resolved once from the loop's own model, so every escalation path in this
    # function agrees on where "stronger" points.
    tool_error_escalation_model = escalation_for(model) if escalate_on_tool_errors else None
    researched_urls: set[str] = set()
    fetched_urls: set[str] = set()
    tool_trace = {
        "search_calls": 0,
        "page_fetches": 0,
        "editing_calls": 0,
        "token_budget_reached": False,
        "max_iterations_reached": False,
        "required_final_tool_succeeded": False,
    }

    for iteration in range(max_iterations):
        token_budget_reached = total_token_budget_reached()
        tool_trace["token_budget_reached"] = bool(tool_trace["token_budget_reached"] or token_budget_reached)
        if token_budget_reached and not token_budget_nudged:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The logical run token ceiling has been reached. Do not perform more web research. "
                        "Finalize now from the evidence already collected; do not invent missing facts."
                    ),
                }
            )
            record_token_budget_nudge()
            token_budget_nudged = True
            log("warning", f"  [{phase_name}] token ceiling reached; forcing finalization without search tools")
        active_model = model
        if tool_errors_escalated and tool_error_escalation_model:
            active_model = tool_error_escalation_model
        if _json_parse_failures > 0:
            escalated = escalation_for(model)
            if escalated:
                active_model = escalated
                log(
                    "info",
                    f"  [{phase_name}] JSON parsing failed previously — elevating model from {model} to {active_model} for retry prompt",
                )

        prepare_final_tool = bool(required_final_tool_name and not token_budget_reached and iteration == max_iterations - 2)
        force_final_tool = bool(required_final_tool_name and (token_budget_reached or iteration == max_iterations - 1))
        if prepare_final_tool:
            fallback_model = escalation_for(active_model) or tool_error_escalation_model
            if fallback_model:
                log("info", f"  [{phase_name}] escalating evidence application to {fallback_model}")
                active_model = fallback_model
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Research is complete. Do not search or fetch again. Use the editing tools now to apply all "
                        "supported findings from the accumulated evidence. Fix every validation error already "
                        "reported, then leave the next turn for final validation."
                    ),
                }
            )
        if force_final_tool:
            fallback_model = escalation_for(active_model) or tool_error_escalation_model
            if fallback_model:
                log("info", f"  [{phase_name}] escalating final evidence synthesis to {fallback_model}")
                active_model = fallback_model
            messages.append(
                {
                    "role": "user",
                    "content": required_final_instruction
                    or f"Finalize the evidence now by calling {required_final_tool_name}. Do not perform more research.",
                }
            )

        log("info", f"  [{phase_name}] iteration {iteration + 1}/{max_iterations} — calling {active_model}...")

        if tools_mode:
            search_tools = (
                [SEARCH_TOOL, FETCH_TOOL, BALLOTPEDIA_TOOL, BALLOTPEDIA_ELECTION_TOOL, IMAGE_SEARCH_TOOL]
                if allow_search_tools and not token_budget_reached and iteration < nudge_at
                else []
            )
            tools_for_call = search_tools + _extra_tools if (search_tools or _extra_tools) else None
            if prepare_final_tool:
                tools_for_call = _extra_tools or None
            if force_final_tool:
                tools_for_call = [
                    tool for tool in _extra_tools if tool.get("function", {}).get("name") == required_final_tool_name
                ]

            if iteration == nudge_at and len(messages) > 2:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You have used several searches. If you found real changes to make, "
                            "use your editing tools to commit them now. "
                            "If the data is already correct and no changes are needed, "
                            "do NOT call any tools — just stop. "
                            "Never invent or fabricate data to satisfy this prompt."
                        ),
                    }
                )
                log("info", f"  [{phase_name}] nudging model to commit edits (iteration {iteration + 1})")
        else:
            if iteration == nudge_at and len(messages) > 2:
                messages = [
                    messages[0],
                    messages[1],
                    {
                        "role": "user",
                        "content": (
                            "You have finished searching. Please now compile your findings "
                            "and return ONLY the final JSON response. No more searches."
                        ),
                    },
                ]
                log("info", f"  [{phase_name}] nudging model to produce output (iteration {iteration + 1})")

            base_tools = (
                [SEARCH_TOOL, FETCH_TOOL, BALLOTPEDIA_TOOL, BALLOTPEDIA_ELECTION_TOOL, IMAGE_SEARCH_TOOL]
                if allow_search_tools and not token_budget_reached and iteration < nudge_at
                else []
            )
            tools_for_call = (base_tools + _extra_tools) if (base_tools or _extra_tools) else None

        t_call = time.perf_counter()
        # OpenRouter reports an upstream provider failure as HTTP 200 carrying
        # finish_reason "error" with no content and no usage, so the empty-response
        # guard below never sees it. Treated as an ordinary empty turn it silently
        # consumed one of the loop's iterations: ma-house-02-2026 lost 3 of its 12
        # that way and ran out of budget before it could finalize. Retry the call
        # rather than spending the turn on a response the provider never produced.
        for provider_error_attempt in range(PROVIDER_ERROR_RETRIES + 1):
            try:
                prepared = context.prepare_messages(messages, tools=tools_for_call)
                record_context_metrics(
                    estimated_input_tokens=prepared.estimated_input_tokens,
                    context_window_tokens=context_budget.context_window_tokens,
                    deduplicated_results=prepared.deduplicated_results,
                    compacted_results=prepared.compacted_results,
                    truncated_results=prepared.truncated_results,
                    dropped_tool_turns=prepared.dropped_tool_turns,
                )
                result = await _call_openrouter(
                    prepared.messages,
                    model=active_model,
                    tools=tools_for_call,
                    tool_choice=(
                        {"type": "function", "function": {"name": required_final_tool_name}} if force_final_tool else None
                    ),
                    max_retries=max_request_retries,
                    max_tokens=context_budget.max_output_tokens,
                    run_budget=run_budget,
                )
            except RuntimeError as e:
                if "policy violation" in str(e).lower():
                    log("error", f"  [{phase_name}] policy violation detected; exiting iteration loop")
                    raise
                raise

            if not result or not getattr(result, "choices", None) or len(result.choices) == 0:
                raise RuntimeError(f"[{phase_name}] OpenRouter returned an empty or invalid response: {result}")
            choice = result.choices[0]
            message = choice.message
            finish_reason = choice.finish_reason or "?"
            usage = result.usage
            produced_nothing = not message.tool_calls and not str(message.content or "").strip()
            if finish_reason != "error" or not produced_nothing:
                break
            if provider_error_attempt < PROVIDER_ERROR_RETRIES:
                log(
                    "warning",
                    f"  [{phase_name}] provider returned finish=error with no content; "
                    f"retrying without spending iteration {iteration + 1} "
                    f"({provider_error_attempt + 1}/{PROVIDER_ERROR_RETRIES})",
                )
        elapsed_call = time.perf_counter() - t_call
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
                    tool_trace["search_calls"] += 1
                    args = json.loads(fn.arguments)
                    query = args.get("query", "")
                    log("info", f"    🔍 {query}")
                    search_results = await _await_with_run_budget(
                        _serper_search(
                            query,
                            race_id=race_id,
                            **({"run_budget": run_budget} if run_budget else {}),
                        ),
                        run_budget=run_budget,
                        requested_timeout=30.0,
                        operation="Serper search",
                        timeout_result=[],
                    )
                    log("debug", f"    🔍 got {len(search_results)} results")
                    for search_result in search_results:
                        if isinstance(search_result, dict):
                            result_url = str(search_result.get("url") or search_result.get("link") or "").strip()
                            if result_url:
                                researched_urls.add(result_url)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": context.prepare_tool_result("web_search", search_results),
                        }
                    )
                elif fn.name == "web_image_search":
                    tool_trace["search_calls"] += 1
                    args = json.loads(fn.arguments)
                    query = args.get("query", "")
                    log("info", f"    🖼️ {query}")
                    search_results = await _await_with_run_budget(
                        _serper_image_search(
                            query,
                            race_id=race_id,
                            **({"run_budget": run_budget} if run_budget else {}),
                        ),
                        run_budget=run_budget,
                        requested_timeout=30.0,
                        operation="Serper image search",
                        timeout_result=[],
                    )
                    log("debug", f"    🖼️ got {len(search_results)} results")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": context.prepare_tool_result("web_image_search", search_results),
                        }
                    )
                elif fn.name == "fetch_page":
                    tool_trace["page_fetches"] += 1
                    args = json.loads(fn.arguments)
                    url = args.get("url", "")
                    log("info", f"    📄 fetching {url[:80]}")
                    page_text = await _await_with_run_budget(
                        _fetch_page(url),
                        run_budget=run_budget,
                        requested_timeout=30.0,
                        operation="page fetch",
                        timeout_result="[Page fetch timed out; use another source.]",
                    )
                    log("debug", f"    📄 got {len(page_text)} chars")
                    if page_text and len(page_text) >= 100 and not page_text.lstrip().startswith("["):
                        fetched_urls.add(url)
                        researched_urls.add(url)
                    fetch_hint = _page_fetch_log_hint(url, page_text)
                    if fetch_hint:
                        log("warning", f"    📄 {fetch_hint}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": context.prepare_tool_result("fetch_page", page_text, source_url=url),
                        }
                    )
                elif fn.name == "ballotpedia_lookup":
                    tool_trace["search_calls"] += 1
                    args = json.loads(fn.arguments)
                    candidate_name = args.get("candidate_name", "")
                    log("info", f"    📋 Ballotpedia lookup: {candidate_name}")
                    bp_data = await _await_with_run_budget(
                        _ballotpedia_lookup(candidate_name),
                        run_budget=run_budget,
                        requested_timeout=20.0,
                        operation="Ballotpedia candidate lookup",
                        timeout_result={"found": False, "error": "Candidate lookup timed out."},
                    )
                    log("debug", f"    📋 found={bp_data.get('found')}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": context.prepare_tool_result("ballotpedia_lookup", bp_data),
                        }
                    )
                elif fn.name == "ballotpedia_election_lookup":
                    tool_trace["search_calls"] += 1
                    args = json.loads(fn.arguments)
                    election_race_id = args.get("race_id", race_id or "")
                    log("info", f"    🗳️  Ballotpedia election lookup: {election_race_id}")
                    election_data = await _await_with_run_budget(
                        _ballotpedia_election_lookup(election_race_id),
                        run_budget=run_budget,
                        requested_timeout=20.0,
                        operation="Ballotpedia election lookup",
                        timeout_result={"found": False, "candidates": [], "error": "Election lookup timed out."},
                    )
                    n_found = len(election_data.get("candidates", []))
                    log("debug", f"    🗳️  found={election_data.get('found')} candidates={n_found}")
                    # The election lookup fetched and parsed this exact page;
                    # preserve that provenance just like fetch_page. This does
                    # not make its names authoritative by itself: roster edits
                    # still pass source-class, exact-contest, current-cycle, and
                    # independent completeness adjudication in the handler.
                    election_url = str(election_data.get("page_url") or "").strip()
                    if election_data.get("found") is True and n_found > 0 and election_url.startswith(("http://", "https://")):
                        fetched_urls.add(election_url)
                        researched_urls.add(election_url)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": context.prepare_tool_result("ballotpedia_election_lookup", election_data),
                        }
                    )
                elif fn.name in _extra_handlers:
                    if fn.name != "read_profile":
                        tool_trace["editing_calls"] += 1
                    args = json.loads(fn.arguments)
                    log("info", f"    🔧 {fn.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
                    args["_research_trace"] = {
                        "researched_urls": sorted(researched_urls),
                        "fetched_urls": sorted(fetched_urls),
                    }
                    # Reading-comprehension judgments about roster evidence need a
                    # network call, and the editing handlers are synchronous. Resolve
                    # them here — where we are already async — and hand the handler
                    # finished verdicts, exactly as the research trace is handed over.
                    adjudications = await collect_roster_adjudications(
                        tool_name=fn.name,
                        args=args,
                        race_id=race_id or "",
                        contest_label=contest_label,
                        run_budget=run_budget,
                    )
                    if adjudications:
                        args["_adjudications"] = adjudications
                    try:
                        if fn.name == "read_profile" and context_budget.narrow_phase and args.get("section", "full") == "full":
                            handler_result = (
                                "Full-profile reads are not available in this narrow phase. "
                                "Read section='candidate' with candidate_name, or section='issues'."
                            )
                        else:
                            handler_result = _extra_handlers[fn.name](args)
                        if fn.name == required_final_tool_name and not _tool_result_is_error(handler_result):
                            required_final_tool_succeeded = True
                            tool_trace["required_final_tool_succeeded"] = True
                        if _tool_result_is_error(handler_result):
                            consecutive_tool_errors += 1
                            blocked_detail = " ".join(str(handler_result).split())[:1200]
                            log("warning", f"    🔧 {fn.name} → BLOCKED: {blocked_detail}")
                        else:
                            consecutive_tool_errors = 0
                            log("info", f"    🔧 {fn.name} → OK")
                    except Exception as exc:
                        handler_result = f"Error: {exc}"
                        log("warning", f"    🔧 {fn.name} → {exc}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": context.prepare_tool_result(fn.name, handler_result),
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
            if consecutive_tool_errors >= 2 and tool_error_escalation_model and not tool_errors_escalated:
                tool_errors_escalated = True
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Multiple editing calls were blocked by evidence guards. Do not repeat those calls "
                            "with the same sources. Review the blocked results and all research already collected, "
                            "then pivot to higher-priority official evidence. Only retry an edit when the new "
                            "evidence directly satisfies the guard; otherwise leave the roster unchanged."
                        ),
                    }
                )
                log(
                    "warning",
                    f"  [{phase_name}] repeated blocked edits; escalating subsequent synthesis to "
                    f"{tool_error_escalation_model}",
                )
            if required_final_tool_succeeded:
                return {"_tool_trace": tool_trace} if return_tool_trace else {}
            continue

        # No tool calls — in tools_mode this means the LLM is done editing
        if tools_mode:
            if required_final_tool_name and not required_final_tool_succeeded:
                messages.append(message.model_dump())
                messages.append(
                    {
                        "role": "user",
                        "content": required_final_instruction
                        or f"You have not completed the task. Call {required_final_tool_name} before stopping.",
                    }
                )
                log(
                    "warning",
                    f"  [{phase_name}] model stopped before {required_final_tool_name}; requiring finalization",
                )
                continue
            log("info", f"  [{phase_name}] tools-mode complete (no more tool calls)")
            return {"_tool_trace": tool_trace} if return_tool_trace else {}

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
        tool_trace["max_iterations_reached"] = True
        return {"_tool_trace": tool_trace} if return_tool_trace else {}
    raise RuntimeError(f"[{phase_name}] did not produce output within {max_iterations} iterations")
