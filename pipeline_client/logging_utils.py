"""Shared sanitization helpers for pipeline logs and status payloads."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from shared.pipeline_config import RetentionConfig

_SENSITIVE_QUERY_KEYS = frozenset({"key", "api_key", "apikey", "token", "access_token", "secret"})
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+")
_HEADER_RE = re.compile(r"(?i)\b(Authorization|X-API-Key|API-Key)\s*[:=]\s*(?:Bearer\s+)?([^\s,;]+)")
_PROVIDER_KEY_RE = re.compile(
    r"\b(?:" r"AIza[0-9A-Za-z_-]{20,}" r"|sk-[0-9A-Za-z_-]{16,}" r"|serper_[0-9A-Za-z_-]{16,}" r")\b"
)


def _sanitize_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    trailing = ""
    while raw_url and raw_url[-1] in ".,;:)]}":
        trailing = raw_url[-1] + trailing
        raw_url = raw_url[:-1]

    try:
        parts = urlsplit(raw_url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        if not query:
            return raw_url + trailing
        sanitized_query = [(key, "[REDACTED]" if key.casefold() in _SENSITIVE_QUERY_KEYS else value) for key, value in query]
        return (
            urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(sanitized_query, safe="[]"), parts.fragment))
            + trailing
        )
    except ValueError:
        return raw_url + trailing


def truncate_log_message(message: str, max_chars: int | None = None) -> tuple[str, bool]:
    """Bound a sanitized log message and return whether it was truncated."""
    limit = max_chars if max_chars is not None else RetentionConfig.from_env().max_log_message_chars
    if len(message) <= limit:
        return message, False
    suffix = f"... [truncated to {limit} chars]"
    if limit <= len(suffix):
        return message[:limit], True
    return message[: limit - len(suffix)] + suffix, True


def sanitize_log_message_with_metadata(message: Any, *, max_chars: int | None = None) -> tuple[str, bool]:
    """Return a safe log string plus a flag indicating post-sanitization truncation."""
    text = str(message)
    text = _URL_RE.sub(_sanitize_url, text)
    text = _HEADER_RE.sub(r"\1: [REDACTED]", text)
    text = _BEARER_RE.sub(r"\1[REDACTED]", text)
    sanitized = _PROVIDER_KEY_RE.sub("[REDACTED]", text)
    return truncate_log_message(sanitized, max_chars=max_chars)


def sanitize_log_message(message: Any, *, max_chars: int | None = None) -> str:
    """Return a string safe to persist in pipeline logs."""
    return sanitize_log_message_with_metadata(message, max_chars=max_chars)[0]


def sanitize_log_data(value: Any) -> Any:
    """Recursively sanitize strings in structured log/status data."""
    if isinstance(value, str):
        return sanitize_log_message(value)
    if isinstance(value, dict):
        return {key: sanitize_log_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_log_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_log_data(item) for item in value)
    return value
