"""Cloudflare Web Analytics client for static-site traffic reporting."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import httpx

_GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"


class CloudflareAnalytics:
    """Query and briefly cache Cloudflare Web Analytics aggregates."""

    def __init__(self) -> None:
        self.api_token = os.getenv("CLOUDFLARE_ANALYTICS_API_TOKEN", "")
        self.account_tag = os.getenv("CLOUDFLARE_ANALYTICS_ACCOUNT_TAG", "")
        self.site_tag = os.getenv("CLOUDFLARE_ANALYTICS_SITE_TAG", "")
        self.cache_ttl = max(60, int(os.getenv("CLOUDFLARE_ANALYTICS_CACHE_TTL_SECONDS", "300")))
        self._cache: dict[int, tuple[float, Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.api_token and self.account_tag and self.site_tag)

    async def get_summary(self, hours: int) -> Dict[str, Any]:
        if not self.configured:
            return _unavailable(hours, "Cloudflare Web Analytics is not configured")

        cached = self._cache.get(hours)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        async with self._lock:
            cached = self._cache.get(hours)
            if cached and cached[0] > time.monotonic():
                return cached[1]

            result = await self._query_summary(hours)
            self._cache[hours] = (time.monotonic() + self.cache_ttl, result)
            return result

    async def _query_summary(self, hours: int) -> Dict[str, Any]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        time_dimension = "date" if hours > 14 * 24 else "datetimeHour"
        query = _build_query(time_dimension)
        variables = {
            "accountTag": self.account_tag,
            "filter": {
                "AND": [
                    {
                        "datetime_geq": start.isoformat().replace("+00:00", "Z"),
                        "datetime_leq": end.isoformat().replace("+00:00", "Z"),
                    },
                    {"siteTag": self.site_tag},
                ]
            },
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    _GRAPHQL_URL,
                    headers={"Authorization": f"Bearer {self.api_token}", "Accept": "application/json"},
                    json={"query": query, "variables": variables},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return _unavailable(hours, f"Cloudflare analytics request failed: {exc}")

        if payload.get("errors"):
            message = "; ".join(str(item.get("message", item)) for item in payload["errors"])
            return _unavailable(hours, f"Cloudflare analytics query failed: {message}")

        accounts = ((payload.get("data") or {}).get("viewer") or {}).get("accounts") or []
        if not accounts:
            return _unavailable(hours, "Cloudflare analytics account was not found")

        account = accounts[0]
        total_groups = account.get("totals") or []
        pageviews = sum(_estimated_count(group) for group in total_groups)
        visits = sum(_visits(group) for group in total_groups)

        return {
            "configured": True,
            "provider": "cloudflare",
            "hours": hours,
            "pageviews": pageviews,
            "visits": visits,
            "pages_per_visit": round(pageviews / visits, 2) if visits else 0.0,
            "timeseries": [
                {
                    "time": (group.get("dimensions") or {}).get(time_dimension, ""),
                    "pageviews": _estimated_count(group),
                    "visits": _visits(group),
                }
                for group in account.get("series") or []
            ],
            "top_pages": _dimension_rows(account.get("pages") or [], "requestPath"),
            "top_referrers": _dimension_rows(account.get("referrers") or [], "refererHost", empty_label="Direct"),
            "countries": _dimension_rows(account.get("countries") or [], "countryName", empty_label="Unknown"),
            "devices": _dimension_rows(account.get("devices") or [], "deviceType", empty_label="Unknown"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }


def _estimated_count(group: Dict[str, Any]) -> int:
    """Scale sampled RUM page-load counts by Cloudflare's sample interval."""
    count = int(group.get("count") or 0)
    interval = float((group.get("avg") or {}).get("sampleInterval") or 1)
    return max(0, round(count * interval))


def _visits(group: Dict[str, Any]) -> int:
    return max(0, round(float((group.get("sum") or {}).get("visits") or 0)))


def _dimension_rows(groups: list[Dict[str, Any]], field: str, empty_label: str = "Unknown") -> list[Dict[str, Any]]:
    rows = []
    for group in groups:
        value = (group.get("dimensions") or {}).get(field) or empty_label
        rows.append({"name": value, "pageviews": _estimated_count(group), "visits": _visits(group)})
    return rows


def _unavailable(hours: int, error: str) -> Dict[str, Any]:
    return {
        "configured": False,
        "provider": "cloudflare",
        "hours": hours,
        "pageviews": 0,
        "visits": 0,
        "pages_per_visit": 0.0,
        "timeseries": [],
        "top_pages": [],
        "top_referrers": [],
        "countries": [],
        "devices": [],
        "fetched_at": None,
        "error": error,
    }


def _build_query(time_dimension: str) -> str:
    return f"""
query SmarterVoteTraffic($accountTag: string, $filter: AccountRumPageloadEventsAdaptiveGroupsFilter_InputObject) {{
  viewer {{
    accounts(filter: {{accountTag: $accountTag}}) {{
      totals: rumPageloadEventsAdaptiveGroups(limit: 1, filter: $filter) {{
        count
        avg {{ sampleInterval }}
        sum {{ visits }}
      }}
      series: rumPageloadEventsAdaptiveGroups(
        limit: 1000
        filter: $filter
        orderBy: [{time_dimension}_ASC]
      ) {{
        count
        avg {{ sampleInterval }}
        sum {{ visits }}
        dimensions {{ {time_dimension} }}
      }}
      pages: rumPageloadEventsAdaptiveGroups(limit: 20, filter: $filter, orderBy: [count_DESC]) {{
        count
        avg {{ sampleInterval }}
        sum {{ visits }}
        dimensions {{ requestPath }}
      }}
      referrers: rumPageloadEventsAdaptiveGroups(limit: 10, filter: $filter, orderBy: [count_DESC]) {{
        count
        avg {{ sampleInterval }}
        sum {{ visits }}
        dimensions {{ refererHost }}
      }}
      countries: rumPageloadEventsAdaptiveGroups(limit: 10, filter: $filter, orderBy: [count_DESC]) {{
        count
        avg {{ sampleInterval }}
        sum {{ visits }}
        dimensions {{ countryName }}
      }}
      devices: rumPageloadEventsAdaptiveGroups(limit: 10, filter: $filter, orderBy: [count_DESC]) {{
        count
        avg {{ sampleInterval }}
        sum {{ visits }}
        dimensions {{ deviceType }}
      }}
    }}
  }}
}}
"""
