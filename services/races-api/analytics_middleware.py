"""
FastAPI middleware that records every request to the analytics store.
"""

import asyncio
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Paths that should not be tracked
_SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi", "/favicon")


class AnalyticsMiddleware(BaseHTTPMiddleware):
    """Records latency, status code, and hashed IP for every tracked request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip internal and documentation endpoints
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        store = getattr(request.app.state, "analytics", None)
        if store is not None:
            client_ip = request.client.host if request.client else None
            referer = request.headers.get("referer")
            # Fire-and-forget — never delay the response
            asyncio.create_task(
                store.log_request(
                    path=path,
                    status_code=response.status_code,
                    response_ms=elapsed_ms,
                    client_ip=client_ip,
                    referer=referer,
                )
            )

        return response
