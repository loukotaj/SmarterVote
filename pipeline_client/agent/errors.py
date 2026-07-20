"""Typed failures for external pipeline services.

These errors let orchestration distinguish work that should be retried by a
later invocation from permanent request or policy failures. They deliberately
carry no provider response body so API and queue logs do not leak secrets.
"""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for a sanitized external-provider failure."""

    retryable = False

    def __init__(self, message: str, *, provider: str, code: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code


class RetryableProviderError(ProviderError):
    """Transient provider failure safe to retry in a later invocation."""

    retryable = True


class PermanentProviderError(ProviderError):
    """Request or policy failure that retrying unchanged will not fix."""


def is_retryable_provider_error(exc: BaseException) -> bool:
    return isinstance(exc, RetryableProviderError)
