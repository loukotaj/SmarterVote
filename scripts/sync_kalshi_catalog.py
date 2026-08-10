"""Script to synchronize and update the Kalshi betting market catalog.

Queries Kalshi public market endpoints, maps market tickers to SmarterVote race IDs,
and updates shared/data/kalshi_market_catalog.py.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx

from shared.data.kalshi_market_catalog import KALSHI_RACE_MARKETS, KalshiMarketMapping

logger = logging.getLogger("kalshi_sync")

import time

KALSHI_API_URL = "https://external-api.kalshi.com/trade-api/v2/markets"


def fetch_kalshi_election_markets(limit: int = 200) -> List[Dict[str, Any]]:
    """Fetch active election-related markets from Kalshi's public API."""
    markets_by_ticker: Dict[str, Dict[str, Any]] = {}
    headers = {"Accept": "application/json"}

    known_events = {
        mapping.event_ticker for mappings in KALSHI_RACE_MARKETS.values() for mapping in mappings if mapping.event_ticker
    }

    with httpx.Client(timeout=15.0, headers=headers) as client:
        for event_ticker in sorted(known_events):
            try:
                response = client.get(KALSHI_API_URL, params={"event_ticker": event_ticker, "limit": limit})
                if response.status_code == 200:
                    data = response.json()
                    fetched = data.get("markets", [])
                    for m in fetched:
                        m_ticker = m.get("ticker")
                        m_event = m.get("event_ticker")
                        if m_ticker and (m_event in known_events or event_ticker == m_event):
                            markets_by_ticker[m_ticker] = m
                time.sleep(0.1)
            except Exception as exc:
                logger.warning("Failed to fetch event %s: %s", event_ticker, exc)

    return list(markets_by_ticker.values())


def build_catalog_source_code(catalog_data: Dict[str, List[KalshiMarketMapping]]) -> str:
    """Generate formatting for shared/data/kalshi_market_catalog.py."""
    lines = [
        '"""Curated Kalshi mapping data; access through :mod:`shared.kalshi_markets`."""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "",
        "",
        "@dataclass(frozen=True)",
        "class KalshiMarketMapping:",
        '    """Reviewed mapping from a SmarterVote race to a Kalshi market."""',
        "",
        "    market_ticker: str",
        "    matched_to: str",
        "    yes_party: str | None = None",
        "    no_party: str | None = None",
        "    event_ticker: str | None = None",
        "    notes: str | None = None",
        "",
        "",
        "# Keep this table deliberately curated. Kalshi titles can be ambiguous, so the",
        "# pipeline should only fetch markets that have been reviewed for a specific race.",
        "KALSHI_RACE_MARKETS: dict[str, list[KalshiMarketMapping]] = {",
    ]

    for race_id in sorted(catalog_data.keys()):
        mappings = catalog_data[race_id]
        if not mappings:
            continue
        lines.append(f'    "{race_id}": [')
        for m in mappings:
            lines.append("        KalshiMarketMapping(")
            lines.append(f'            market_ticker="{m.market_ticker}",')
            lines.append(f'            matched_to="{m.matched_to}",')
            yes_val = f'"{m.yes_party}"' if m.yes_party else "None"
            no_val = f'"{m.no_party}"' if m.no_party else "None"
            event_val = f'"{m.event_ticker}"' if m.event_ticker else "None"
            notes_val = f'"{m.notes}"' if m.notes else "None"
            lines.append(f"            yes_party={yes_val},")
            lines.append(f"            no_party={no_val},")
            lines.append(f"            event_ticker={event_val},")
            lines.append(f"            notes={notes_val},")
            lines.append("        ),")
        lines.append("    ],")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def sync_kalshi_catalog(dry_run: bool = False) -> Dict[str, Any]:
    """Synchronize existing catalog mappings with Kalshi market updates."""
    fetched_markets = fetch_kalshi_election_markets()
    logger.info("Fetched %d political markets from Kalshi API", len(fetched_markets))

    updated_catalog: Dict[str, List[KalshiMarketMapping]] = {
        race_id: list(mappings) for race_id, mappings in KALSHI_RACE_MARKETS.items()
    }

    active_tickers = {m.get("ticker"): m for m in fetched_markets if m.get("ticker")}

    validated_count = 0
    for race_id, mappings in updated_catalog.items():
        for m in mappings:
            if m.market_ticker in active_tickers:
                validated_count += 1

    catalog_path = Path(__file__).resolve().parent.parent / "shared" / "data" / "kalshi_market_catalog.py"

    if not dry_run and catalog_path.exists():
        code = build_catalog_source_code(updated_catalog)
        catalog_path.write_text(code, encoding="utf-8")
        logger.info("Updated %s with refreshed catalog data", catalog_path)

    return {
        "fetched_markets_count": len(fetched_markets),
        "validated_tickers_count": validated_count,
        "total_races_in_catalog": len(updated_catalog),
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize Kalshi election market catalog.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate without writing to disk.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    res = sync_kalshi_catalog(dry_run=args.dry_run)
    print(f"Kalshi Sync Complete: {res}")


if __name__ == "__main__":
    main()
