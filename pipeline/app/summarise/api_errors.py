"""
API error classes and exceptions for LLM Summarization Engine.

This module contains custom exception classes for handling LLM API errors
and rate limiting scenarios.
"""

from typing import Optional


class LLMAPIError(Exception):
    """Custom exception for LLM API errors."""

    def __init__(self, provider: str, message: str, status_code: Optional[int] = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} API Error: {message}")


class RateLimitError(LLMAPIError):
    """Exception for rate limiting errors."""

    def __init__(self, provider: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        message = "Rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(provider, message, 429)