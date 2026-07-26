"""Behavioral tests for shared.kalshi_markets catalog validation and helpers.

tests/test_kalshi_market_data.py already exercises normalize_kalshi_market and
sanity-checks the real KALSHI_RACE_MARKETS catalog; this file targets
get_kalshi_market_mappings, mapping_from_dict, and the _validate_catalog
error branches that only trigger on a malformed catalog.
"""

import pytest

import shared.kalshi_markets as kalshi_markets
from shared.data.kalshi_market_catalog import KalshiMarketMapping
from shared.kalshi_markets import get_kalshi_market_mappings, mapping_from_dict


def test_get_kalshi_market_mappings_returns_copy_for_known_race():
    mappings = get_kalshi_market_mappings("ga-senate-2026")

    assert isinstance(mappings, list)
    # Mutating the returned list must not affect the underlying catalog.
    original_len = len(mappings)
    mappings.append(KalshiMarketMapping(market_ticker="FAKE", matched_to="Nobody", event_ticker="FAKE-EVT"))
    assert len(get_kalshi_market_mappings("ga-senate-2026")) == original_len


def test_get_kalshi_market_mappings_unknown_race_returns_empty_list():
    assert get_kalshi_market_mappings("not-a-real-race-id") == []


def test_mapping_from_dict_builds_full_mapping():
    mapping = mapping_from_dict(
        {
            "market_ticker": "KXTEST-26-R",
            "matched_to": "Republican",
            "yes_party": "Republican",
            "no_party": "Democratic",
            "event_ticker": "KXTEST-26",
            "notes": "example",
        }
    )

    assert mapping == KalshiMarketMapping(
        market_ticker="KXTEST-26-R",
        matched_to="Republican",
        yes_party="Republican",
        no_party="Democratic",
        event_ticker="KXTEST-26",
        notes="example",
    )


def test_mapping_from_dict_omits_optional_fields_when_absent():
    mapping = mapping_from_dict({"market_ticker": "KXTEST-26-R", "matched_to": "Republican"})

    assert mapping.yes_party is None
    assert mapping.no_party is None
    assert mapping.event_ticker is None
    assert mapping.notes is None


def test_validate_catalog_raises_on_empty_race_entry(monkeypatch):
    monkeypatch.setattr(kalshi_markets, "KALSHI_RACE_MARKETS", {"empty-race": []})

    with pytest.raises(ValueError, match="empty race entry"):
        kalshi_markets._validate_catalog()


def test_validate_catalog_raises_on_incomplete_mapping(monkeypatch):
    bad_mapping = KalshiMarketMapping(market_ticker="", matched_to="Republican")
    monkeypatch.setattr(kalshi_markets, "KALSHI_RACE_MARKETS", {"race-1": [bad_mapping]})

    with pytest.raises(ValueError, match="incomplete mapping"):
        kalshi_markets._validate_catalog()


def test_validate_catalog_raises_on_duplicate_ticker_across_races(monkeypatch):
    shared_ticker = KalshiMarketMapping(market_ticker="DUPLICATE", matched_to="Republican")
    other_race_ticker = KalshiMarketMapping(market_ticker="DUPLICATE", matched_to="Democratic")
    monkeypatch.setattr(
        kalshi_markets,
        "KALSHI_RACE_MARKETS",
        {"race-1": [shared_ticker], "race-2": [other_race_ticker]},
    )

    with pytest.raises(ValueError, match="assigned to both"):
        kalshi_markets._validate_catalog()


def test_validate_catalog_allows_well_formed_catalog(monkeypatch):
    good_mapping = KalshiMarketMapping(market_ticker="GOOD", matched_to="Republican")
    monkeypatch.setattr(kalshi_markets, "KALSHI_RACE_MARKETS", {"race-1": [good_mapping]})

    kalshi_markets._validate_catalog()  # must not raise
