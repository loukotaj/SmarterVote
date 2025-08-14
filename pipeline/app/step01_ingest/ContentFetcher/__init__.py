"""
Content Fetcher Service for SmarterVote Pipeline

This module provides a unified interface for fetching web and other content sources.
"""

try:  # pragma: no cover - selenium is optional
    from .web_content_fetcher import WebContentFetcher

    __all__ = ["WebContentFetcher"]
except Exception:  # noqa: BLE001
    __all__: list[str] = []
