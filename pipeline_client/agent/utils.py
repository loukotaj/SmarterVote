"""Shared utilities for the agent package."""

import json
import logging
import re
from typing import Any, Callable, Dict, Optional

_logger = logging.getLogger("pipeline")


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM output, handling markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def make_logger(on_log: Optional[Callable] = None) -> Callable:
    """Return a log(level, msg) function writing to both module logger and callback."""
    def log(level: str, msg: str) -> None:
        _logger.log(getattr(logging, level.upper(), logging.INFO), msg)
        if on_log:
            on_log(level, msg)
    return log
