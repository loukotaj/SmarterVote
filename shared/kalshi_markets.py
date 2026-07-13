"""Validated public interface for the curated Kalshi market catalog."""

from __future__ import annotations

from typing import Any

from shared.data.kalshi_market_catalog import KALSHI_RACE_MARKETS, KalshiMarketMapping


def _validate_catalog() -> None:
    seen_tickers: dict[str, str] = {}
    for race_id, mappings in KALSHI_RACE_MARKETS.items():
        if not race_id or not mappings:
            raise ValueError(f"Kalshi catalog has an empty race entry: {race_id!r}")
        for mapping in mappings:
            if not mapping.market_ticker or not mapping.matched_to:
                raise ValueError(f"Kalshi catalog has an incomplete mapping for {race_id}")
            previous_race = seen_tickers.setdefault(mapping.market_ticker, race_id)
            if previous_race != race_id:
                raise ValueError(
                    f"Kalshi ticker {mapping.market_ticker!r} is assigned to both {previous_race!r} and {race_id!r}"
                )


_validate_catalog()


def get_kalshi_market_mappings(race_id: str) -> list[KalshiMarketMapping]:
    return list(KALSHI_RACE_MARKETS.get(race_id, []))


def mapping_from_dict(data: dict[str, Any]) -> KalshiMarketMapping:
    return KalshiMarketMapping(
        market_ticker=str(data["market_ticker"]),
        matched_to=str(data["matched_to"]),
        yes_party=str(data["yes_party"]) if data.get("yes_party") else None,
        no_party=str(data["no_party"]) if data.get("no_party") else None,
        event_ticker=str(data["event_ticker"]) if data.get("event_ticker") else None,
        notes=str(data["notes"]) if data.get("notes") else None,
    )
