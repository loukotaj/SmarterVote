from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Literal

Party = Literal["Democratic", "Republican", "Other"]
Chamber = Literal["house", "senate", "governors"]

SENATE_HOLDOVERS: Dict[str, list[Party]] = {
    "Arizona": ["Democratic", "Democratic"],
    "California": ["Democratic", "Democratic"],
    "Connecticut": ["Democratic", "Democratic"],
    "Hawaii": ["Democratic", "Democratic"],
    "Indiana": ["Republican", "Republican"],
    "Maryland": ["Democratic", "Democratic"],
    "Missouri": ["Republican", "Republican"],
    "Nevada": ["Democratic", "Democratic"],
    "New York": ["Democratic", "Democratic"],
    "North Dakota": ["Republican", "Republican"],
    "Pennsylvania": ["Democratic", "Republican"],
    "Utah": ["Republican", "Republican"],
    "Vermont": ["Democratic", "Democratic"],
    "Washington": ["Democratic", "Democratic"],
    "Wisconsin": ["Democratic", "Republican"],
    "Virginia": ["Democratic", "Democratic"],
    "West Virginia": ["Republican", "Republican"],
    "Colorado": ["Democratic"],
    "Delaware": ["Democratic"],
    "Georgia": ["Democratic"],
    "Illinois": ["Democratic"],
    "Maine": ["Democratic"],
    "Massachusetts": ["Democratic"],
    "Michigan": ["Democratic"],
    "Minnesota": ["Democratic"],
    "New Hampshire": ["Democratic"],
    "New Jersey": ["Democratic"],
    "New Mexico": ["Democratic"],
    "Oregon": ["Democratic"],
    "Rhode Island": ["Democratic"],
    "Alabama": ["Republican"],
    "Alaska": ["Republican"],
    "Arkansas": ["Republican"],
    "Florida": ["Republican"],
    "Idaho": ["Republican"],
    "Iowa": ["Republican"],
    "Kansas": ["Republican"],
    "Kentucky": ["Republican"],
    "Louisiana": ["Republican"],
    "Mississippi": ["Republican"],
    "Montana": ["Republican"],
    "Nebraska": ["Republican"],
    "North Carolina": ["Republican"],
    "Ohio": ["Republican"],
    "Oklahoma": ["Republican"],
    "South Carolina": ["Republican"],
    "South Dakota": ["Republican"],
    "Tennessee": ["Republican"],
    "Texas": ["Republican"],
    "Wyoming": ["Republican"],
}

GOVERNOR_HOLDOVERS: Dict[str, Party] = {
    "Delaware": "Democratic",
    "Kentucky": "Democratic",
    "North Carolina": "Democratic",
    "New Jersey": "Democratic",
    "Washington": "Democratic",
    "Virginia": "Democratic",
    "Indiana": "Republican",
    "Louisiana": "Republican",
    "Mississippi": "Republican",
    "Missouri": "Republican",
    "Montana": "Republican",
    "North Dakota": "Republican",
    "Utah": "Republican",
    "West Virginia": "Republican",
}

INCUMBENT_FALLBACKS: Dict[Chamber, Dict[str, Party]] = {
    "governors": {
        "Illinois": "Democratic",
        "New York": "Democratic",
        "Vermont": "Republican",
        "Wisconsin": "Democratic",
    },
    "senate": {
        "Virginia": "Democratic",
        "West Virginia": "Republican",
    },
    "house": {},
}


EXPECTED_TOTALS: Dict[Chamber, int] = {"house": 435, "senate": 100, "governors": 50}
THRESHOLDS: Dict[Chamber, int] = {"house": 218, "senate": 51, "governors": 26}
ABBR_TO_STATE = {
    "ak": "Alaska",
    "al": "Alabama",
    "ar": "Arkansas",
    "az": "Arizona",
    "ca": "California",
    "co": "Colorado",
    "ct": "Connecticut",
    "de": "Delaware",
    "fl": "Florida",
    "ga": "Georgia",
    "hi": "Hawaii",
    "ia": "Iowa",
    "id": "Idaho",
    "il": "Illinois",
    "ks": "Kansas",
    "ky": "Kentucky",
    "la": "Louisiana",
    "ma": "Massachusetts",
    "md": "Maryland",
    "me": "Maine",
    "mi": "Michigan",
    "mn": "Minnesota",
    "mo": "Missouri",
    "ms": "Mississippi",
    "mt": "Montana",
    "nc": "North Carolina",
    "nd": "North Dakota",
    "ne": "Nebraska",
    "nh": "New Hampshire",
    "nj": "New Jersey",
    "nm": "New Mexico",
    "nv": "Nevada",
    "ny": "New York",
    "oh": "Ohio",
    "ok": "Oklahoma",
    "or": "Oregon",
    "pa": "Pennsylvania",
    "ri": "Rhode Island",
    "sc": "South Carolina",
    "sd": "South Dakota",
    "tn": "Tennessee",
    "tx": "Texas",
    "ut": "Utah",
    "va": "Virginia",
    "vt": "Vermont",
    "wa": "Washington",
    "wi": "Wisconsin",
    "wv": "West Virginia",
    "wy": "Wyoming",
}


def normalize_party(party: Any) -> Party:
    value = str(party or "").lower()
    if "democrat" in value or value == "dfl":
        return "Democratic"
    if "republican" in value or value == "gop":
        return "Republican"
    return "Other"


def office_group(race: Dict[str, Any]) -> Chamber | None:
    office = str(race.get("office") or "").lower()
    if "senate" in office:
        return "senate"
    if "governor" in office or "gubernatorial" in office:
        return "governors"
    if "house" in office or "representative" in office:
        return "house"
    return None


def race_state(race: Dict[str, Any]) -> str | None:
    state = race.get("state") or race.get("jurisdiction")
    if state:
        return str(state)
    race_id = str(race.get("id") or race.get("race_id") or "")
    return ABBR_TO_STATE.get(race_id.split("-")[0].lower())


def fallback_party_for_race(race: Dict[str, Any]) -> Party:
    candidates = race.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("incumbent"):
                return normalize_party(candidate.get("party"))
        party_counts: Dict[Party, int] = {"Democratic": 0, "Republican": 0, "Other": 0}
        for candidate in candidates:
            if isinstance(candidate, dict):
                party_counts[normalize_party(candidate.get("party"))] += 1
        if party_counts["Democratic"] > party_counts["Republican"]:
            return "Democratic"
        if party_counts["Republican"] > party_counts["Democratic"]:
            return "Republican"

    chamber = office_group(race)
    state = race_state(race)
    if chamber and state and state in INCUMBENT_FALLBACKS.get(chamber, {}):
        return INCUMBENT_FALLBACKS[chamber][state]

    if chamber == "senate" and state and state in SENATE_HOLDOVERS:
        return SENATE_HOLDOVERS[state][-1]
    return "Other"


def _default_probability_for_rating(rating: str, party: Party) -> Dict[Party, float]:
    confidence = {
        "safe": 0.97,
        "likely": 0.86,
        "lean": 0.68,
        "tilt": 0.57,
        "tossup": 0.5,
    }
    rating_value = rating.lower()
    winner_probability = next((prob for key, prob in confidence.items() if key in rating_value), 0.5)
    if party == "Democratic":
        return {"Democratic": winner_probability, "Republican": 1 - winner_probability, "Other": 0.0}
    if party == "Republican":
        return {"Democratic": 1 - winner_probability, "Republican": winner_probability, "Other": 0.0}
    return {"Democratic": 0.5, "Republican": 0.5, "Other": 0.0}


def _race_party_probabilities(forecast: Dict[str, Any]) -> Dict[Party, float]:
    raw = forecast.get("party_probabilities")
    if isinstance(raw, dict):
        dem = float(raw.get("Democratic") or raw.get("Democrat") or raw.get("D") or 0)
        rep = float(raw.get("Republican") or raw.get("GOP") or raw.get("R") or 0)
        other = max(0.0, 1.0 - dem - rep)
        if dem or rep:
            return {"Democratic": dem, "Republican": rep, "Other": other}

    party = normalize_party(forecast.get("predicted_winner_party"))
    win_probability = forecast.get("win_probability")
    if isinstance(win_probability, (int, float)) and party in ("Democratic", "Republican"):
        probability = max(0.0, min(1.0, float(win_probability)))
        if party == "Democratic":
            return {"Democratic": probability, "Republican": 1 - probability, "Other": 0.0}
        return {"Democratic": 1 - probability, "Republican": probability, "Other": 0.0}
    return _default_probability_for_rating(str(forecast.get("rating") or ""), party)


def _chamber_races(summaries: Iterable[Dict[str, Any]], chamber: Chamber) -> list[Dict[str, Any]]:
    return [
        race
        for race in summaries
        if office_group(race) == chamber and not (chamber == "governors" and race.get("id") == "in-governor-2026")
    ]


def _projected_control(projected: Dict[Party, int], chamber: Chamber) -> Party:
    if chamber == "senate" and projected.get("Democratic", 0) == 50 and projected.get("Republican", 0) == 50:
        return "Republican"
    if projected.get("Democratic", 0) >= THRESHOLDS[chamber]:
        return "Democratic"
    if projected.get("Republican", 0) >= THRESHOLDS[chamber]:
        return "Republican"
    return "Other"


def _chamber_label(chamber: Chamber) -> str:
    return {"house": "House", "senate": "Senate", "governors": "governors"}[chamber]


def _party_label(party: Party) -> str:
    if party == "Democratic":
        return "Democrats"
    if party == "Republican":
        return "Republicans"
    return "Neither party"


def _opposing_party(party: Party) -> Party:
    return "Democratic" if party == "Republican" else "Republican"


def _race_phrase(races: list[str], empty: str = "the remaining competitive races") -> str:
    if not races:
        return empty
    if len(races) == 1:
        return races[0]
    if len(races) == 2:
        return f"{races[0]} and {races[1]}"
    return f"{', '.join(races[:-1])}, and {races[-1]}"


def _rating_label(rating: str) -> str:
    value = rating.lower().replace("_", " ")
    labels = {
        "safe d": "Safe D",
        "likely d": "Likely D",
        "lean d": "Lean D",
        "tilt d": "Tilt D",
        "tossup": "Toss-up",
        "toss-up": "Toss-up",
        "tilt r": "Tilt R",
        "lean r": "Lean R",
        "likely r": "Likely R",
        "safe r": "Safe R",
    }
    return labels.get(value, rating or "Unrated")


def _race_note(race: Dict[str, Any]) -> str:
    title = str(race.get("title") or race.get("id") or "Unknown race")
    forecast = race.get("forecast") if isinstance(race.get("forecast"), dict) else {}
    rating = _rating_label(str(forecast.get("rating") or ""))
    party = normalize_party(forecast.get("predicted_winner_party"))
    prob = forecast.get("win_probability")
    if isinstance(prob, (int, float)):
        return f"{title} ({rating}, {_party_label(party).rstrip('s')} {float(prob) * 100:.0f}%)"
    return f"{title} ({rating})"


def summarize_chamber(
    summaries: list[Dict[str, Any]], chamber: Chamber, narrative: str | None = None, analysis: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    races = _chamber_races(summaries, chamber)
    active_states = {state for race in races if (state := race_state(race))}
    projected: Dict[Party, int] = {"Democratic": 0, "Republican": 0, "Other": 0}
    expected: Dict[Party, float] = {"Democratic": 0.0, "Republican": 0.0, "Other": 0.0}
    tossups = 0
    competitive: list[str] = []
    competitive_race_notes: list[tuple[int, str]] = []

    rep_holdovers = 0
    if chamber == "senate":
        for state, parties in SENATE_HOLDOVERS.items():
            seats = parties[:1] if state in active_states else parties
            for party in seats:
                projected[party] += 1
                expected[party] += 1
                if party == "Republican":
                    rep_holdovers += 1
    elif chamber == "governors":
        for party in GOVERNOR_HOLDOVERS.values():
            projected[party] += 1
            expected[party] += 1
            if party == "Republican":
                rep_holdovers += 1

    for race in races:
        forecast = race.get("forecast") if isinstance(race.get("forecast"), dict) else None
        if not forecast:
            fallback_party = fallback_party_for_race(race)
            projected[fallback_party] += 1
            expected[fallback_party] += 1
            continue
        party = normalize_party(forecast.get("predicted_winner_party"))
        if party == "Other":
            probs = _race_party_probabilities(forecast)
            if probs.get("Democratic", 0.0) > probs.get("Republican", 0.0):
                party = "Democratic"
            elif probs.get("Republican", 0.0) > probs.get("Democratic", 0.0):
                party = "Republican"
            else:
                party = fallback_party_for_race(race)
        projected[party] += 1
        for key, value in _race_party_probabilities(forecast).items():
            expected[key] += value
        rating = str(forecast.get("rating") or "")
        if "tossup" in rating.lower() or "toss-up" in rating.lower():
            tossups += 1
        if any(key in rating.lower() for key in ("tossup", "tilt", "lean")):
            competitive.append(str(race.get("title") or race.get("id")))
            priority = 0 if "toss" in rating.lower() else 1 if "tilt" in rating.lower() else 2
            competitive_race_notes.append((priority, _race_note(race)))

    control_party = _projected_control(projected, chamber)
    dem_expected = expected["Democratic"]
    rep_expected = expected["Republican"]

    seat_distribution = {}
    rep_probs = []
    for race in races:
        forecast = race.get("forecast") if isinstance(race.get("forecast"), dict) else None
        if forecast:
            probs = _race_party_probabilities(forecast)
            rep_probs.append(probs.get("Republican", 0.0))
        else:
            fallback_party = fallback_party_for_race(race)
            rep_probs.append(1.0 if fallback_party == "Republican" else 0.0)

    # Exact Poisson binomial distribution using dynamic programming
    dp = [1.0]
    for p in rep_probs:
        next_dp = [0.0] * (len(dp) + 1)
        for j, val in enumerate(dp):
            next_dp[j] += val * (1.0 - p)
            next_dp[j + 1] += val * p
        dp = next_dp

    # Exact control and tie probabilities from DP
    if chamber == "senate":
        dem_control_probability = sum(prob for j, prob in enumerate(dp) if rep_holdovers + j <= 49)
        tie_probability = sum(prob for j, prob in enumerate(dp) if rep_holdovers + j == 50)
        republican_probability = sum(prob for j, prob in enumerate(dp) if rep_holdovers + j >= 50)
    elif chamber == "governors":
        dem_control_probability = sum(prob for j, prob in enumerate(dp) if rep_holdovers + j <= 24)
        tie_probability = sum(prob for j, prob in enumerate(dp) if rep_holdovers + j == 25)
        republican_probability = sum(prob for j, prob in enumerate(dp) if rep_holdovers + j >= 26)
    else:  # house
        dem_control_probability = sum(prob for j, prob in enumerate(dp) if rep_holdovers + j <= 217)
        tie_probability = 0.0
        republican_probability = sum(prob for j, prob in enumerate(dp) if rep_holdovers + j >= 218)

    # Populate seat distribution keys e.g. "51R-49D"
    total_chamber_seats = EXPECTED_TOTALS[chamber]
    for j, prob in enumerate(dp):
        r_seats = rep_holdovers + j
        d_seats = total_chamber_seats - r_seats
        if r_seats > d_seats:
            key = f"{r_seats}R-{d_seats}D"
        elif r_seats < d_seats:
            key = f"{d_seats}D-{r_seats}R"
        else:
            key = f"{r_seats}R-{d_seats}D"  # tie split
        if prob > 0.0005:  # Keep only non-trivial probabilities to limit payload size
            seat_distribution[key] = round(prob, 4)

    dem_control_probability = max(0.01, min(0.99, dem_control_probability))
    republican_probability = max(0.01, min(0.99, republican_probability))

    if control_party == "Republican":
        control_probability = republican_probability
    elif control_party == "Democratic":
        control_probability = dem_control_probability
    else:
        control_probability = max(dem_control_probability, republican_probability)

    chamber_label = _chamber_label(chamber)
    favored_party = control_party
    opposing_party = _opposing_party(favored_party)
    favored_label = _party_label(favored_party)
    opposing_label = _party_label(opposing_party)
    key_races = [note for _, note in sorted(competitive_race_notes, key=lambda item: item[0])][:4]
    key_race_text = _race_phrase(key_races)
    expected_gap = abs(dem_expected - rep_expected)

    default_narrative = (
        f"The {chamber_label} forecast starts from a {projected['Democratic']}-{projected['Republican']} projected split, "
        f"leaving {favored_label.lower()} with the inside track but little room for drift. "
        f"The races most able to move the chamber are {key_race_text}; a shift across those contests would matter more "
        f"than changes in seats already rated likely or safe."
    )
    if chamber == "senate" and projected["Democratic"] == 50 and projected["Republican"] == 50:
        default_narrative += " A 50-50 Senate is counted as Republican control because the VP tie-break is assumed Republican."

    # Prepare structured fallback analysis fields
    default_bottom_line = (
        f"{favored_label} are projected to control the {chamber_label.lower()} "
        f"on a {projected['Democratic']}-{projected['Republican']} seat split."
    )
    if chamber == "senate" and projected["Democratic"] == 50 and projected["Republican"] == 50:
        default_bottom_line += " A 50-50 Senate counts as Republican control under the VP tie-break assumption."

    default_why_favored = (
        f"{favored_label} are favored because the central projection gives them {projected[favored_party]} seats "
        f"and the mean forecast is separated by about {expected_gap:.1f} seats."
    )
    default_opposing_path = (
        f"{opposing_label} need to convert {key_race_text} into wins and avoid losing any current lean or tilt advantages "
        f"to reach the {THRESHOLDS[chamber]}-seat threshold."
    )
    default_uncertainty = (
        f"The uncertainty is concentrated in {_race_phrase(key_races, 'the toss-up and tilt-rated races')}: "
        f"{tossups} toss-up and {len(competitive)} total competitive contests carry most of the distribution's movement."
    )

    res = {
        "narrative": narrative or default_narrative,
        "control_party": control_party,
        "control_probability": round(control_probability, 3),
        "outcome_probabilities": {
            "Democratic": round(dem_control_probability, 3),
            "Republican": round(republican_probability, 3),
            "Other": 0.0,
            "tie_50_50": round(tie_probability, 3) if chamber in ("senate", "governors") else 0.0,
        },
        "projected_seats": projected,
        "expected_seats": {key: round(value, 1) for key, value in expected.items()},
        "threshold": THRESHOLDS[chamber],
        "total_seats": EXPECTED_TOTALS[chamber],
        "tossup_count": tossups,
        "competitive_race_count": len(competitive),
        "competitive_races": competitive[:12],
        "method": "Aggregates published race forecast probabilities and known holdover seats. Senate 50-50 outcomes count as Republican control via VP tie-break.",
        "bottom_line": (analysis or {}).get("bottom_line") or default_bottom_line,
        "why_party_favored": (analysis or {}).get("why_party_favored") or default_why_favored,
        "opposing_party_path": (analysis or {}).get("opposing_party_path") or default_opposing_path,
        "key_uncertainty": (analysis or {}).get("key_uncertainty") or default_uncertainty,
    }

    res["seat_distribution"] = seat_distribution
    if chamber == "senate":
        res["vp_tiebreak_party"] = "Republican"

    return res


def build_chamber_forecasts(
    summaries: list[Dict[str, Any]],
    narratives: Dict[Chamber, str] | None = None,
    analyses: Dict[Chamber, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    narratives = narratives or {}
    analyses = analyses or {}
    chambers = {
        chamber: summarize_chamber(summaries, chamber, narratives.get(chamber), analyses.get(chamber))
        for chamber in ("house", "senate", "governors")
    }
    return {
        "schema_version": "chamber_forecasts.v2",
        "house": chambers["house"]["narrative"],
        "senate": chambers["senate"]["narrative"],
        "governors": chambers["governors"]["narrative"],
        "chambers": chambers,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
