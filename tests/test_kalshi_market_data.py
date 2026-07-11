from datetime import datetime, timezone

from pipeline_client.agent.market_data.kalshi import normalize_kalshi_market
from shared.kalshi_markets import KALSHI_RACE_MARKETS, KalshiMarketMapping


def test_normalize_kalshi_market_uses_bid_ask_midpoint_for_yes_party():
    signal = normalize_kalshi_market(
        {
            "ticker": "KXGASENATE-26-GOP",
            "event_ticker": "KXGASENATE-26",
            "title": "Will a Republican win the Georgia Senate race?",
            "yes_bid": 62,
            "yes_ask": 66,
            "last_price": 61,
            "volume": 1500,
            "liquidity": 2000,
            "last_update_time": "2026-06-23T12:00:00Z",
        },
        KalshiMarketMapping(
            market_ticker="KXGASENATE-26-GOP",
            matched_to="Republican",
            yes_party="Republican",
            no_party="Democratic",
        ),
    )

    assert signal["provider"] == "kalshi"
    assert signal["implied_probability"] == 0.64
    assert signal["yes_bid"] == 0.62
    assert signal["yes_ask"] == 0.66
    assert signal["matched_party"] == "Republican"
    assert signal["confidence"] == "high"
    assert signal["as_of"] == "2026-06-23T12:00:00+00:00"


def test_normalize_kalshi_market_accepts_dollar_price_fields():
    signal = normalize_kalshi_market(
        {
            "ticker": "SENATEMI-26-D",
            "title": "Will Democratics win the Senate race in Michigan?",
            "yes_bid_dollars": "0.7000",
            "yes_ask_dollars": "0.7300",
            "last_price_dollars": "0.7200",
            "volume_fp": "113708.62",
            "liquidity_dollars": "0.0000",
            "updated_time": "2026-06-23T12:00:00Z",
        },
        KalshiMarketMapping(
            market_ticker="SENATEMI-26-D",
            matched_to="Democratic",
            yes_party="Democratic",
            no_party="Republican",
        ),
    )

    assert signal["implied_probability"] == 0.715
    assert signal["yes_bid"] == 0.7
    assert signal["yes_ask"] == 0.73
    assert signal["volume"] == "113708.62"


def test_normalize_kalshi_market_does_not_use_future_close_time_as_as_of():
    signal = normalize_kalshi_market(
        {
            "ticker": "SENATEAK-26-R",
            "title": "Will a Republican win?",
            "yes_bid": 40,
            "yes_ask": 42,
            "close_time": "2027-11-03T15:00:00Z",
        },
        KalshiMarketMapping(
            market_ticker="SENATEAK-26-R",
            matched_to="Republican",
            yes_party="Republican",
            no_party="Democratic",
        ),
    )

    assert datetime.fromisoformat(signal["as_of"]) <= datetime.now(timezone.utc)
    assert signal["as_of"] != "2027-11-03T15:00:00+00:00"


def test_normalize_kalshi_market_inverts_probability_for_no_party():
    signal = normalize_kalshi_market(
        {
            "ticker": "KXGASENATE-26-GOP",
            "title": "Will a Republican win the Georgia Senate race?",
            "yes_bid": 62,
            "yes_ask": 66,
            "volume": 100,
        },
        KalshiMarketMapping(
            market_ticker="KXGASENATE-26-GOP",
            matched_to="Democratic",
            yes_party="Republican",
            no_party="Democratic",
        ),
    )

    assert signal["implied_probability"] == 0.36
    assert signal["matched_party"] == "Democratic"


def test_normalize_kalshi_candidate_market_keeps_candidate_party():
    signal = normalize_kalshi_market(
        {
            "ticker": "KXCA17PERSON-26-RKHA",
            "title": "Who will win California 17th congressional district?",
            "yes_bid": 92,
            "yes_ask": 96,
        },
        KalshiMarketMapping(
            market_ticker="KXCA17PERSON-26-RKHA",
            matched_to="Ro Khanna",
            yes_party="Democratic",
            event_ticker="KXCA17PERSON-26",
        ),
    )

    assert signal["matched_to"] == "Ro Khanna"
    assert signal["matched_party"] == "Democratic"


def test_kalshi_race_mappings_are_party_pairs_without_duplicate_tickers():
    assert len(KALSHI_RACE_MARKETS) == 146

    for race_id, mappings in KALSHI_RACE_MARKETS.items():
        tickers = [mapping.market_ticker for mapping in mappings]
        assert len(tickers) == len(set(tickers)), race_id
        assert all(mapping.matched_to for mapping in mappings), race_id
        assert all(mapping.event_ticker and "-26" in mapping.event_ticker for mapping in mappings), race_id

    party_pair_races = {
        race_id
        for race_id, mappings in KALSHI_RACE_MARKETS.items()
        if {"Democratic", "Republican"}.issubset({mapping.matched_to for mapping in mappings})
    }
    assert len(party_pair_races) == 144
