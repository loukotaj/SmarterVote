"""Shared utilities for the agent package."""

import json
import logging
import re
from typing import Any, Callable, Dict, Optional

_logger = logging.getLogger("pipeline")


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM output, handling markdown fences and trailing text.

    Strategy:
    1. Strip markdown code fences.
    2. Try a direct json.loads (fast path).
    3. Walk the string to find the outermost balanced ``{...}`` or ``[...]``
       block — handles cases where the model appends trailing explanation text.
    """
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    # Fast path
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find the outermost balanced JSON object or array.
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        start = cleaned.find(open_ch)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        end = -1
        for i, ch in enumerate(cleaned[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass

    # Re-raise with original error for the caller to handle
    return json.loads(cleaned)


def make_logger(on_log: Optional[Callable] = None) -> Callable:
    """Return a log(level, msg) function writing to both module logger and callback."""
    def log(level: str, msg: str) -> None:
        _logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)
    return log
