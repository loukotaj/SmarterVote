import re

import pytest

from shared.forecast_summary import (
    ABBR_TO_STATE,
    GOVERNOR_HOLDOVERS,
    SENATE_HOLDOVERS,
    build_chamber_forecasts,
    election_cycle_year,
    get_chamber_forecast_system_prompt,
    is_chamber_control_race,
    office_group,
)
from shared.race_catalog import build_race_summary_fields


def test_race_summary_includes_forecast():
    summary = build_race_summary_fields(
        "ga-senate-2026",
        {
            "id": "ga-senate-2026",
            "election_date": "2026-11-03",
            "updated_utc": "2026-06-20T00:00:00Z",
            "candidates": [{"name": "Alice", "party": "Democratic", "incumbent": True}],
            "forecast": {
                "predicted_winner_name": "Alice",
                "predicted_winner_party": "Democratic",
                "win_probability": 0.61,
                "party_probabilities": {"Democratic": 0.61, "Republican": 0.39},
                "margin_estimate": 2.1,
                "rating": "tilt_d",
                "confidence": "medium",
                "rationale": "Alice has a narrow advantage.",
                "based_on_poll_count": 1,
                "generated_at": "2026-06-20T00:00:00Z",
                "model": "openai/gpt-5.4",
                "source_urls": ["https://example.com/poll"],
                "market_signals": [
                    {
                        "provider": "kalshi",
                        "market_ticker": "KXGASENATE-26-DEM",
                        "title": "Will a Democrat win the Georgia Senate race?",
                        "matched_to": "Democratic",
                        "matched_party": "Democratic",
                        "implied_probability": 0.6,
                        "as_of": "2026-06-23T12:00:00Z",
                        "confidence": "medium",
                    }
                ],
            },
        },
    )

    assert summary["forecast"]["rating"] == "tilt_d"
    assert summary["forecast"]["predicted_winner_name"] == "Alice"
    assert summary["forecast"]["market_signals"][0]["provider"] == "kalshi"


def test_chamber_forecast_counts_senate_tie_in_republican_probability():
    active_states = [
        "Colorado",
        "Delaware",
        "Georgia",
        "Illinois",
        "Maine",
        "Massachusetts",
        "Michigan",
        "Minnesota",
        "New Hampshire",
        "New Jersey",
        "New Mexico",
        "Oregon",
        "Rhode Island",
        "Alabama",
        "Alaska",
        "Arkansas",
        "Florida",
        "Idaho",
        "Iowa",
        "Kansas",
        "Kentucky",
        "Louisiana",
        "Mississippi",
        "Montana",
        "Nebraska",
        "North Carolina",
        "Ohio",
        "Oklahoma",
        "South Carolina",
        "South Dakota",
        "Tennessee",
        "Texas",
        "Wyoming",
    ]
    summaries = [
        {
            "id": f"{state.lower().replace(' ', '-')}-senate-2026",
            "title": f"{state} Senate",
            "office": "United States Senate",
            "state": state,
            "forecast": {
                "predicted_winner_party": "Democratic" if index < 15 else "Republican",
                "win_probability": 0.65,
                "rating": "lean_d" if index < 15 else "lean_r",
            },
        }
        for index, state in enumerate(active_states)
    ]

    forecast = build_chamber_forecasts(summaries)
    senate = forecast["chambers"]["senate"]

    assert senate["projected_seats"]["Democratic"] + senate["projected_seats"]["Republican"] == 100
    assert senate["projected_seats"]["Democratic"] == 50
    assert senate["projected_seats"]["Republican"] == 50
    assert senate["outcome_probabilities"]["Republican"] >= senate["outcome_probabilities"]["tie_50_50"]
    assert "50-50 Senate" in senate["narrative"]
    assert senate["competitive_race_count"] >= len(senate["competitive_races"])


def test_chamber_forecast_control_party_tracks_control_probability():
    active_states = [
        "Colorado",
        "Delaware",
        "Georgia",
        "Illinois",
        "Maine",
        "Massachusetts",
        "Michigan",
        "Minnesota",
        "New Hampshire",
        "New Jersey",
        "New Mexico",
        "Oregon",
        "Rhode Island",
        "Alabama",
        "Alaska",
        "Arkansas",
        "Florida",
        "Idaho",
        "Iowa",
        "Kansas",
        "Kentucky",
        "Louisiana",
        "Mississippi",
        "Montana",
        "Nebraska",
        "North Carolina",
        "Ohio",
        "Oklahoma",
        "South Carolina",
        "South Dakota",
        "Tennessee",
        "Texas",
        "Wyoming",
    ]
    summaries = [
        {
            "id": f"{state.lower().replace(' ', '-')}-senate-2026",
            "title": f"{state} Senate",
            "office": "United States Senate",
            "state": state,
            "forecast": {
                "predicted_winner_party": "Democratic" if index < 14 else "Republican",
                "win_probability": 0.51,
                "rating": "tilt_d" if index < 14 else "tilt_r",
                "party_probabilities": {
                    "Democratic": 0.51 if index < 14 else 0.49,
                    "Republican": 0.49 if index < 14 else 0.51,
                },
            },
        }
        for index, state in enumerate(active_states)
    ]

    senate = build_chamber_forecasts(summaries)["chambers"]["senate"]

    assert senate["projected_seats"] == {"Democratic": 49, "Republican": 51, "Other": 0}
    assert senate["outcome_probabilities"]["Democratic"] > senate["outcome_probabilities"]["Republican"]
    assert senate["control_party"] == "Democratic"
    assert senate["control_probability"] == senate["outcome_probabilities"]["Democratic"]


def test_new_chamber_forecast_fields():
    summaries = [
        {
            "id": "ga-senate-2026",
            "office": "United States Senate",
            "state": "Georgia",
            "forecast": {
                "predicted_winner_party": "Democratic",
                "win_probability": 0.60,
                "rating": "tilt_d",
                "party_probabilities": {"Democratic": 0.60, "Republican": 0.40},
            },
        },
        {
            "id": "tx-senate-2026",
            "office": "United States Senate",
            "state": "Texas",
            "forecast": {
                "predicted_winner_party": "Republican",
                "win_probability": 0.70,
                "rating": "lean_r",
                "party_probabilities": {"Democratic": 0.30, "Republican": 0.70},
            },
        },
    ]

    forecast = build_chamber_forecasts(
        summaries,
        analyses={
            "senate": {
                "bottom_line": "Custom bottom line.",
                "why_party_favored": "Custom why favored.",
                "opposing_party_path": "Custom opposing path.",
                "key_uncertainty": "Custom uncertainty.",
            }
        },
    )
    senate = forecast["chambers"]["senate"]

    assert senate["vp_tiebreak_party"] == "Republican"
    assert senate["bottom_line"] == "Custom bottom line."
    assert senate["why_party_favored"] == "Custom why favored."
    assert senate["opposing_party_path"] == "Custom opposing path."
    assert senate["key_uncertainty"] == "Custom uncertainty."
    assert len(senate["seat_distribution"]) > 0
    for key, val in senate["seat_distribution"].items():
        assert "R-" in key or "D-" in key or key == "50R-50D"
        assert 0.0 <= val <= 1.0


def test_default_chamber_story_names_competitive_races():
    summaries = [
        {
            "id": "ga-senate-2026",
            "title": "Georgia Senate",
            "office": "United States Senate",
            "state": "Georgia",
            "forecast": {
                "predicted_winner_party": "Democratic",
                "win_probability": 0.57,
                "rating": "tilt_d",
                "party_probabilities": {"Democratic": 0.57, "Republican": 0.43},
            },
        },
        {
            "id": "tx-senate-2026",
            "title": "Texas Senate",
            "office": "United States Senate",
            "state": "Texas",
            "forecast": {
                "predicted_winner_party": "Republican",
                "win_probability": 0.68,
                "rating": "lean_r",
                "party_probabilities": {"Democratic": 0.32, "Republican": 0.68},
            },
        },
    ]

    forecast = build_chamber_forecasts(summaries)
    senate = forecast["chambers"]["senate"]

    assert "Georgia Senate" in senate["narrative"]
    assert "Texas Senate" in senate["opposing_party_path"]
    assert "competitive races to reach" not in senate["opposing_party_path"]


def test_governor_forecast_other_party_resolves_from_party_probabilities():
    forecast = build_chamber_forecasts(
        [
            {
                "id": "il-governor-2026",
                "title": "Illinois Governor",
                "office": "Governor",
                "state": "Illinois",
                "forecast": {
                    "predicted_winner_party": "Other",
                    "win_probability": 0.55,
                    "rating": "tilt_d",
                    "party_probabilities": {"Democratic": 0.55, "Republican": 0.45},
                },
            }
        ]
    )

    governors = forecast["chambers"]["governors"]

    assert governors["projected_seats"]["Other"] == 0
    assert governors["projected_seats"]["Democratic"] == 7
    assert governors["projected_seats"]["Republican"] == 8


def test_governor_context_exposes_tie_and_distinguishes_projection_from_control_probability():
    from shared.forecast_summary import build_chamber_context

    context = build_chamber_context(
        [{"id": "ga-governor-2026", "title": "Georgia Governor", "forecast": {"rating": "tossup"}}],
        "Governors",
        {
            "control_party": "Democratic",
            "control_probability": 0.409,
            "outcome_probabilities": {"Democratic": 0.409, "Republican": 0.404, "tie_50_50": 0.187},
            "projected_seats": {"Democratic": 24, "Republican": 26},
            "expected_seats": {"Democratic": 24.6, "Republican": 25.0},
        },
    )

    assert "Most likely outright-control party: Democratic (probability: 40.9%)" in context
    assert "Projected Seats: 24 Democratic, 26 Republican" in context
    assert "Probability of a 25-25 tie: 18.7%" in context
    assert "may differ" in context


# ---------------------------------------------------------------------------
# office_group / is_chamber_control_race
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "office",
    ["U.S. Senate", "US Senate", "United States Senate", "Senate", "Senator"],
)
def test_office_group_accepts_every_spelling_of_the_federal_senate(office):
    """`office` is model-written free text; no single spelling may be required."""
    assert office_group({"office": office}) == "senate"


@pytest.mark.parametrize(
    "office",
    [
        "Georgia State Senate District 5",
        "State Senator",
        "State House of Representatives",
        "Virginia House of Delegates",
        "State Assembly",
        "General Assembly",
    ],
)
def test_office_group_rejects_state_legislative_offices(office):
    assert office_group({"office": office}) is None


@pytest.mark.parametrize("office", ["U.S. House", "US House of Representatives", "Congress"])
def test_office_group_accepts_every_spelling_of_the_federal_house(office):
    assert office_group({"office": office}) == "house"


def test_governor_race_in_a_holdover_state_is_excluded_from_control_math():
    """Not Indiana-specific: any state whose governor is not up this cycle."""
    for state in ("Indiana", "Kentucky", "Louisiana", "Virginia"):
        race = {"id": "xx-governor-2026", "office": "Governor", "state": state}
        assert is_chamber_control_race(race, "governors") is False


def test_governor_race_in_a_contested_state_is_counted():
    race = {"id": "ga-governor-2026", "office": "Governor", "state": "Georgia"}
    assert is_chamber_control_race(race, "governors") is True


def test_holdover_exclusion_resolves_state_from_the_race_id():
    """Summaries without an explicit `state` still resolve via the ID prefix."""
    assert is_chamber_control_race({"id": "in-governor-2026", "office": "Governor"}, "governors") is False


def test_holdover_exclusion_does_not_apply_to_other_chambers():
    """Indiana holds no 2026 governor race but does hold House races."""
    race = {"id": "in-house-01-2026", "office": "U.S. House", "state": "Indiana"}
    assert is_chamber_control_race(race, "house") is True


def test_abbr_to_state_covers_all_fifty_states():
    """A missing abbreviation makes `race_state` return None for a whole state,
    silently dropping it from holdover/active-state math. Indiana was missing."""
    expected = {
        "al",
        "ak",
        "az",
        "ar",
        "ca",
        "co",
        "ct",
        "de",
        "fl",
        "ga",
        "hi",
        "id",
        "il",
        "in",
        "ia",
        "ks",
        "ky",
        "la",
        "me",
        "md",
        "ma",
        "mi",
        "mn",
        "ms",
        "mo",
        "mt",
        "ne",
        "nv",
        "nh",
        "nj",
        "nm",
        "ny",
        "nc",
        "nd",
        "oh",
        "ok",
        "or",
        "pa",
        "ri",
        "sc",
        "sd",
        "tn",
        "tx",
        "ut",
        "vt",
        "va",
        "wa",
        "wv",
        "wi",
        "wy",
    }
    assert set(ABBR_TO_STATE) == expected


def test_every_holdover_state_name_is_a_real_state():
    """Holdover tables are keyed by full state name; a typo silently drops seats."""
    valid = set(ABBR_TO_STATE.values())
    assert set(SENATE_HOLDOVERS) <= valid
    assert set(GOVERNOR_HOLDOVERS) <= valid


def test_election_cycle_year_reads_the_cycle_off_the_races():
    races = [{"id": "ga-senate-2026"}, {"id": "az-house-07-2026"}, {"id": "me-governor-2026"}]
    assert election_cycle_year(races) == "2026"


def test_election_cycle_year_falls_back_to_election_date():
    assert election_cycle_year([{"id": "no-year-slug", "election_date": "2028-11-07"}]) == "2028"


def test_election_cycle_year_is_not_swung_by_one_malformed_id():
    races = [{"id": "ga-senate-2026"}, {"id": "az-senate-2026"}, {"id": "stray-2018"}]
    assert election_cycle_year(races) == "2026"


def test_election_cycle_year_is_none_when_nothing_carries_a_year():
    assert election_cycle_year([{"id": "mystery"}]) is None


def test_chamber_forecast_prompt_names_the_cycle_it_was_given():
    assert "in the 2028 election cycle" in get_chamber_forecast_system_prompt("US Senate", "2028")


def test_chamber_forecast_prompt_stays_cycle_neutral_without_a_year():
    prompt = get_chamber_forecast_system_prompt("US Senate")
    assert "in the current election cycle" in prompt
    assert not re.search(r"\b20\d{2}\b", prompt), "prompt must not name a hardcoded cycle"
