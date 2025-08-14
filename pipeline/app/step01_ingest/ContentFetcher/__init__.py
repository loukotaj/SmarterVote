"""
Content Fetcher Service for SmarterVote Pipeline

This module provides a unified interface for fetching web and other content sources.
"""

from .web_content_fetcher import WebContentFetcher

__all__ = ["WebContentFetcher"]
