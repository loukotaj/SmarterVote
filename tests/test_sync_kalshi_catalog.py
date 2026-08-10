"""Tests for scripts/sync_kalshi_catalog.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.sync_kalshi_catalog import build_catalog_source_code, fetch_kalshi_election_markets, sync_kalshi_catalog
from shared.data.kalshi_market_catalog import KalshiMarketMapping


def test_build_catalog_source_code() -> None:
    test_data = {
        "ga-senate-2026": [
            KalshiMarketMapping(
                market_ticker="KXSENGA-26-JOSS",
                matched_to="Jon Ossoff",
                yes_party="Democratic",
                no_party=None,
                event_ticker="KXSENGA-26",
                notes="Georgia Senate contest",
            )
        ]
    }
    code = build_catalog_source_code(test_data)
    assert "KALSHI_RACE_MARKETS: dict[str, list[KalshiMarketMapping]] = {" in code
    assert '"ga-senate-2026": [' in code
    assert 'market_ticker="KXSENGA-26-JOSS"' in code
    assert 'matched_to="Jon Ossoff"' in code


@patch("scripts.sync_kalshi_catalog.httpx.Client")
def test_fetch_kalshi_election_markets(mock_client_cls: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "markets": [
            {
                "ticker": "KXGOVAK-26-BWAL",
                "event_ticker": "KXGOVAK-26",
                "title": "Who will win the governorship in Alaska?",
            },
            {
                "ticker": "UNRELATED-MARKET",
                "event_ticker": "CPI-2026",
                "title": "Consumer Price Index annual change",
            },
        ],
        "cursor": None,
    }
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value.__enter__.return_value = mock_client

    markets = fetch_kalshi_election_markets()
    assert len(markets) == 1
    assert markets[0]["ticker"] == "KXGOVAK-26-BWAL"


@patch("scripts.sync_kalshi_catalog.fetch_kalshi_election_markets")
def test_sync_kalshi_catalog_dry_run(mock_fetch: MagicMock) -> None:
    mock_fetch.return_value = [
        {
            "ticker": "KXGOVAK-26-BWAL",
            "event_ticker": "KXGOVAK-26",
            "title": "Who will win the governorship in Alaska?",
        }
    ]
    res = sync_kalshi_catalog(dry_run=True)
    assert res["dry_run"] is True
    assert res["fetched_markets_count"] == 1
    assert res["validated_tickers_count"] >= 1
