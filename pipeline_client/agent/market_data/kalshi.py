from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from shared.kalshi_markets import KalshiMarketMapping, get_kalshi_market_mappings
from shared.models import ConfidenceLevel

DEFAULT_KALSHI_API_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"


def _price_to_probability(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price > 1:
        price = price / 100.0
    return max(0.0, min(1.0, price))


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _market_updated_at(market: dict[str, Any]) -> datetime:
    """Return the observation time, never the market's future lifecycle date."""
    now = datetime.now(timezone.utc)
    for key in ("last_update_time", "updated_time", "updated_at"):
        parsed = _parse_datetime(market.get(key))
        if parsed is not None and parsed <= now:
            return parsed
    return now


def _market_confidence(market: dict[str, Any], yes_bid: float | None, yes_ask: float | None) -> ConfidenceLevel:
    spread = yes_ask - yes_bid if yes_bid is not None and yes_ask is not None else None
    volume = float(market.get("volume") or market.get("volume_24h") or market.get("volume_fp") or 0)
    liquidity = float(market.get("liquidity") or market.get("liquidity_dollars") or 0)

    if spread is not None and spread <= 0.08 and (volume >= 1000 or liquidity >= 1000):
        return ConfidenceLevel.HIGH
    if spread is not None and spread <= 0.18 and (volume > 0 or liquidity > 0):
        return ConfidenceLevel.MEDIUM
    if volume > 0 or liquidity > 0:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.UNKNOWN


def _market_probability_for_mapping(
    market: dict[str, Any], mapping: KalshiMarketMapping
) -> tuple[float | None, float | None, float | None, float | None]:
    yes_bid = _price_to_probability(market.get("yes_bid") or market.get("yes_bid_dollars"))
    yes_ask = _price_to_probability(market.get("yes_ask") or market.get("yes_ask_dollars"))
    last_price = _price_to_probability(market.get("last_price") or market.get("last_price_dollars") or market.get("yes_price"))

    if yes_bid is not None and yes_ask is not None:
        yes_probability = (yes_bid + yes_ask) / 2
    else:
        yes_probability = last_price

    implied_probability = yes_probability
    if mapping.no_party and mapping.matched_to == mapping.no_party and yes_probability is not None:
        implied_probability = 1 - yes_probability

    return implied_probability, yes_bid, yes_ask, last_price


def normalize_kalshi_market(market: dict[str, Any], mapping: KalshiMarketMapping) -> dict[str, Any]:
    implied_probability, yes_bid, yes_ask, last_price = _market_probability_for_mapping(market, mapping)
    as_of = _market_updated_at(market)
    ticker = str(market.get("ticker") or mapping.market_ticker)
    event_ticker = str(market.get("event_ticker") or mapping.event_ticker or "") or None
    matched_party = mapping.matched_to if mapping.matched_to in {mapping.yes_party, mapping.no_party} else mapping.yes_party

    return {
        "provider": "kalshi",
        "market_ticker": ticker,
        "event_ticker": event_ticker,
        "title": str(market.get("title") or market.get("subtitle") or ticker),
        "matched_to": mapping.matched_to,
        "matched_party": matched_party,
        "implied_probability": implied_probability,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "last_price": last_price,
        "volume": market.get("volume") or market.get("volume_24h") or market.get("volume_fp"),
        "liquidity": market.get("liquidity") or market.get("liquidity_dollars"),
        "as_of": as_of.isoformat(),
        "url": f"https://kalshi.com/markets/{ticker}",
        "confidence": _market_confidence(market, yes_bid, yes_ask).value,
    }


class KalshiMarketDataClient:
    def __init__(self, *, base_url: str | None = None, timeout: float = 8.0) -> None:
        self.base_url = (base_url or os.getenv("KALSHI_API_BASE_URL") or DEFAULT_KALSHI_API_BASE_URL).rstrip("/")
        self.timeout = timeout

    async def get_market(self, ticker: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get(f"/markets/{ticker}")
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("market"), dict):
            return payload["market"]
        if isinstance(payload, dict):
            return payload
        raise ValueError(f"Unexpected Kalshi market response for {ticker}")


async def fetch_kalshi_market_signals(race_id: str) -> list[dict[str, Any]]:
    mappings = get_kalshi_market_mappings(race_id)
    if not mappings:
        return []

    client = KalshiMarketDataClient()
    signals: list[dict[str, Any]] = []
    for mapping in mappings:
        market = await client.get_market(mapping.market_ticker)
        signals.append(normalize_kalshi_market(market, mapping))
    return signals
