"""HTTP client used by the SmarterVote MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


def _clean_base_url(value: str) -> str:
    return value.rstrip("/") or "http://127.0.0.1:8080"


@dataclass(frozen=True)
class RacesApiClient:
    """Small async wrapper around the production-shaped races-api."""

    base_url: str = "http://127.0.0.1:8080"
    bearer_token: str = ""
    admin_key: str = ""
    cloud_run_id_token: str = ""
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "RacesApiClient":
        """Build a client from MCP process environment variables."""
        base_url = os.getenv("SMARTERVOTE_RACES_API_URL") or os.getenv("RACES_API_URL") or "http://127.0.0.1:8080"
        bearer_token = os.getenv("SMARTERVOTE_RACES_API_TOKEN") or os.getenv("RACES_API_BEARER_TOKEN") or ""
        admin_key = os.getenv("SMARTERVOTE_RACES_API_ADMIN_KEY") or os.getenv("ADMIN_API_KEY") or ""
        cloud_run_id_token = (
            os.getenv("SMARTERVOTE_RACES_API_CLOUD_RUN_ID_TOKEN")
            or os.getenv("SMARTERVOTE_RACES_API_ID_TOKEN")
            or os.getenv("RACES_API_CLOUD_RUN_ID_TOKEN")
            or ""
        )
        timeout_raw = os.getenv("SMARTERVOTE_RACES_API_TIMEOUT", "60")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 60.0
        return cls(
            base_url=_clean_base_url(base_url),
            bearer_token=bearer_token,
            admin_key=admin_key,
            cloud_run_id_token=cloud_run_id_token,
            timeout_seconds=timeout_seconds,
        )

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.cloud_run_id_token:
            headers["X-Serverless-Authorization"] = f"Bearer {self.cloud_run_id_token}"
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if self.admin_key:
            headers["X-Admin-Key"] = self.admin_key
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Call races-api and return decoded JSON."""
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers=self._headers(),
        ) as client:
            response = await client.request(method, path, params=params, json=json)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text
            try:
                parsed = response.json()
                detail = str(parsed.get("detail", parsed))
            except ValueError:
                pass
            raise RuntimeError(f"races-api {response.status_code} for {method} {path}: {detail}") from exc
        if not response.content:
            return None
        return response.json()

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        return await self.request("POST", path, json=json)

    async def delete(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self.request("DELETE", path, params=params)


def compact_options(**kwargs: Any) -> dict[str, Any]:
    """Drop unset option values before sending RunOptions-compatible payloads."""
    return {key: value for key, value in kwargs.items() if value is not None}
