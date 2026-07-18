"""Shared API rate limiter configuration."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_rate_limit_key(request: Request) -> str | None:
    # Exempt SvelteKit prerendering requests from public read limits.
    if request.headers.get("origin") == "http://sveltekit-prerender":
        return None
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)
