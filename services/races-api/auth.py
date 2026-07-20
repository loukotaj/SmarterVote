"""Auth0 JWT verification dependency for the races-api admin endpoints."""

import asyncio
import os
import secrets
import time
from typing import Optional

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

_http_bearer = HTTPBearer(auto_error=False)

# In-memory cache for Auth0 JWKS to prevent network overhead on every request
_jwks_cache: Optional[dict] = None
_jwks_fetched_at: float = 0.0
_jwks_lock = asyncio.Lock()
_JWKS_CACHE_TTL = 3600.0  # Cache for 1 hour


async def _decode_jwt(token: str) -> dict:
    global _jwks_cache, _jwks_fetched_at
    auth0_domain = os.getenv("AUTH0_DOMAIN", "")
    auth0_audience = os.getenv("AUTH0_AUDIENCE", "")
    jwks_url = f"https://{auth0_domain}/.well-known/jwks.json"

    now = time.monotonic()
    if _jwks_cache is None or (now - _jwks_fetched_at) > _JWKS_CACHE_TTL:
        async with _jwks_lock:
            # Recheck cache after acquiring lock
            now = time.monotonic()
            if _jwks_cache is None or (now - _jwks_fetched_at) > _JWKS_CACHE_TTL:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(jwks_url)
                    resp.raise_for_status()
                    _jwks_cache = resp.json()
                    _jwks_fetched_at = now

    unverified = jwt.get_unverified_header(token)
    rsa_key = next((k for k in _jwks_cache["keys"] if k.get("kid") == unverified.get("kid")), None)
    if not rsa_key:
        raise HTTPException(status_code=401, detail="Invalid token: signing key not found")
    return jwt.decode(
        token,
        rsa_key,
        algorithms=["RS256"],
        audience=auth0_audience,
        issuer=f"https://{auth0_domain}/",
    )


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
    x_admin_key: str = Header(default=""),
) -> dict:
    """Dependency: verify Auth0 JWT bearer token or admin API key.

    Set SKIP_AUTH=true (or 1 or yes) to bypass verification in local dev.
    Set ADMIN_API_KEY to allow non-browser admin clients with X-Admin-Key.
    """
    # Read env at call time so tests can set it without module reload.
    skip_auth = os.getenv("SKIP_AUTH", "").lower() in ("1", "true", "yes")
    if skip_auth:
        return {}

    if not isinstance(x_admin_key, str):
        x_admin_key = ""
    admin_api_key = os.getenv("ADMIN_API_KEY", "")
    if admin_api_key and x_admin_key:
        if secrets.compare_digest(x_admin_key, admin_api_key):
            return {"auth": "admin_api_key"}
        if credentials is None:
            raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key")

    auth0_domain = os.getenv("AUTH0_DOMAIN", "")
    auth0_audience = os.getenv("AUTH0_AUDIENCE", "")
    if not auth0_domain or not auth0_audience:
        raise HTTPException(
            status_code=503,
            detail="Auth not configured (AUTH0_DOMAIN/AUTH0_AUDIENCE missing). Set SKIP_AUTH=true for local dev.",
        )
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return await _decode_jwt(credentials.credentials)
    except (JWTError, httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication") from exc
