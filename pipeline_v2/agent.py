"""Pipeline V2 agent: single-step candidate research with web search.

Uses OpenAI function calling with a web_search tool backed by the
Serper API to research candidates and produce RaceJSON output.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

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
# Serper web search implementation
# ---------------------------------------------------------------------------


async def _serper_search(query: str, *, num_results: int = 8) -> List[Dict[str, Any]]:
    """Execute a web search via the Serper API."""
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

    return results


# ---------------------------------------------------------------------------
# Agent loop
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
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


async def run_agent(
    race_id: str,
    *,
    on_log: Any | None = None,
    cheap_mode: bool = True,
    max_iterations: int = 20,
) -> Dict[str, Any]:
    """Run the v2 research agent for a given race_id.

    Parameters
    ----------
    race_id : str
        Race slug, e.g. ``"mo-senate-2024"``.
    on_log : callable, optional
        ``(level, message) -> None`` callback for streaming logs.
    cheap_mode : bool
        When *True*, use ``gpt-4o-mini``; otherwise ``gpt-4o``.
    max_iterations : int
        Safety limit on the agent tool-call loop.

    Returns
    -------
    dict
        The completed RaceJSON-like output.
    """

    model = "gpt-4o-mini" if cheap_mode else "gpt-4o"

    def log(level: str, msg: str) -> None:
        logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)

    log("info", f"v2 agent starting for {race_id} (model={model})")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(race_id=race_id)},
    ]

    t0 = time.perf_counter()
    search_count = 0

    for iteration in range(max_iterations):
        log("info", f"Agent iteration {iteration + 1}/{max_iterations}")

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
                    log("info", f"  🔍 Searching: {query}")
                    search_results = await _serper_search(query)
                    search_count += 1
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(search_results),
                        }
                    )
            continue

        # No tool calls – the model produced its final answer
        content = message.get("content", "")
        elapsed = time.perf_counter() - t0
        log(
            "info",
            f"Agent finished in {elapsed:.1f}s after {search_count} searches",
        )

        try:
            race_json = _extract_json(content)
        except (json.JSONDecodeError, ValueError) as exc:
            log("warning", f"Failed to parse agent output as JSON: {exc}")
            # Ask the model to fix its output
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

        # Normalise the output
        race_json.setdefault("id", race_id)
        race_json.setdefault("updated_utc", datetime.now(timezone.utc).isoformat())
        race_json.setdefault("generator", ["pipeline-v2-agent"])

        # Add last_accessed timestamps to sources that lack them
        now_iso = datetime.now(timezone.utc).isoformat()
        for candidate in race_json.get("candidates", []):
            for issue_data in candidate.get("issues", {}).values():
                if isinstance(issue_data, dict):
                    for src in issue_data.get("sources", []):
                        if isinstance(src, dict):
                            src.setdefault("last_accessed", now_iso)

        return race_json

    raise RuntimeError(f"Agent did not produce output within {max_iterations} iterations")
