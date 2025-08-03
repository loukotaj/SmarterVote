"""
Fetch Service for SmarterVote Pipeline

This module provides a unified interface for fetching content from various sources.
"""

from .web_content_fetcher import WebContentFetcher

# Main service class for backwards compatibility
FetchService = WebContentFetcher

__all__ = ["FetchService", "WebContentFetcher"]
