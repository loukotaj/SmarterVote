"""Auth0 JWT verification dependency for the races-api admin endpoints."""

import os
import secrets
from typing import Optional

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

_http_bearer = HTTPBearer(auto_error=False)


async def _decode_jwt(token: str) -> dict:
    auth0_domain = os.getenv("AUTH0_DOMAIN", "")
    auth0_audience = os.getenv("AUTH0_AUDIENCE", "")
    jwks_url = f"https://{auth0_domain}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        jwks = (await client.get(jwks_url)).json()
    unverified = jwt.get_unverified_header(token)
    rsa_key = next((k for k in jwks["keys"] if k.get("kid") == unverified.get("kid")), None)
    if not rsa_key:
        raise HTTPException(status_code=401, detail="Invalid token: signing key not found")
    return jwt.decode(
        token,
        rsa_key,
        algorithms=[unverified.get("alg", "RS256")],
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
    except (JWTError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication") from exc
