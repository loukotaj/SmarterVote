"""Reviews carried onto a changed roster must not block publication.

Covers the lifecycle bug behind #323 and #325: a refresh does not re-run
`review`, so an earlier run's reviews ride along unchanged. When the refresh
also changed the roster, those reviews judged people who are no longer in the
race, yet their error flags still failed the grade and blocked the publish.
"""

from pipeline_client.agent.review import (
    compute_validation_grade,
    invalidate_stale_reviews,
    roster_fingerprint,
    stamp_roster_fingerprint,
)


def _race(names, *, with_stance=True):
    candidates = []
    for name in names:
        candidate = {"name": name}
        if with_stance:
            candidate["issues"] = {"Healthcare": {"stance": "Supports expansion."}}
        candidates.append(candidate)
    return {"id": "ne-senate-2026", "candidates": candidates}


def _review(*, score=95, flags=None, fingerprint=None):
    review = {"model": "claude", "verdict": "approved", "score": score, "flags": flags or []}
    if fingerprint is not None:
        review["roster_fingerprint"] = fingerprint
    return review


def test_fingerprint_tracks_membership_and_order():
    a = roster_fingerprint(_race(["Pete Ricketts", "Dan Osborn"]))
    assert a == roster_fingerprint(_race(["pete  ricketts", "DAN OSBORN"]))
    # Flags are positional, so a reorder invalidates them just as a swap does.
    assert a != roster_fingerprint(_race(["Dan Osborn", "Pete Ricketts"]))
    assert a != roster_fingerprint(_race(["Pete Ricketts", "Cindy Burbank"]))


def test_review_judging_a_replaced_roster_is_marked_stale():
    race = _race(["Pete Ricketts", "Dan Osborn"])
    race["reviews"] = [
        _review(
            fingerprint=roster_fingerprint(_race(["Cindy Burbank", "Mike Marvin"])),
            flags=[
                {"field": "candidates[1].issues", "concern": "missing canonical issues", "severity": "error"},
                {"field": "title", "concern": "race title is wrong", "severity": "error"},
            ],
        )
    ]

    assert invalidate_stale_reviews(race) == 1

    review = race["reviews"][0]
    assert review["stale"] is True
    assert review["stale_reason"]
    # Positional flags no longer describe anyone on this roster...
    assert review["flags"][0]["stale"] is True
    # ...but a race-level concern is just as true after the roster changes.
    assert "stale" not in review["flags"][1]


def test_review_matching_the_current_roster_is_untouched():
    race = _race(["Pete Ricketts", "Dan Osborn"])
    race["reviews"] = [
        _review(
            fingerprint=roster_fingerprint(race),
            flags=[{"field": "candidates[0].image_url", "concern": "wrong face", "severity": "error"}],
        )
    ]

    assert invalidate_stale_reviews(race) == 0
    assert "stale" not in race["reviews"][0]
    assert "stale" not in race["reviews"][0]["flags"][0]


def test_legacy_review_without_a_fingerprint_falls_back_to_the_run_baseline():
    baseline = _race(["Cindy Burbank", "Mike Marvin"])
    race = _race(["Pete Ricketts", "Dan Osborn"])
    race["reviews"] = [_review(flags=[{"field": "candidates[2].image_url", "concern": "a high school", "severity": "error"}])]

    assert invalidate_stale_reviews(race, baseline_race_json=baseline) == 1
    assert race["reviews"][0]["flags"][0]["stale"] is True


def test_legacy_review_survives_a_run_that_left_the_roster_alone():
    race = _race(["Pete Ricketts", "Dan Osborn"])
    baseline = _race(["Pete Ricketts", "Dan Osborn"])
    race["reviews"] = [_review(flags=[{"field": "candidates[0].summary", "concern": "wrong district", "severity": "error"}])]

    assert invalidate_stale_reviews(race, baseline_race_json=baseline) == 0
    assert "stale" not in race["reviews"][0]


def test_staleness_is_never_guessed_without_evidence():
    """No fingerprint and no baseline means unprovable, and guessing would discard sound work."""
    race = _race(["Pete Ricketts", "Dan Osborn"])
    race["reviews"] = [_review(flags=[{"field": "candidates[0].summary", "concern": "x", "severity": "error"}])]

    assert invalidate_stale_reviews(race) == 0
    assert "stale" not in race["reviews"][0]


def test_stamp_records_the_roster_actually_judged():
    race = _race(["Pete Ricketts", "Dan Osborn"])
    reviews = [_review(), _review()]
    stamp_roster_fingerprint(reviews, race)

    assert all(r["roster_fingerprint"] == roster_fingerprint(race) for r in reviews)
    race["reviews"] = reviews
    assert invalidate_stale_reviews(race) == 0


def test_stale_error_flags_no_longer_pin_the_grade_below_passing():
    """The #325 unblock: a roster correction stops inheriting the old run's failing grade."""
    race = _race(["Pete Ricketts", "Dan Osborn"])
    error_flag = {"field": "candidates[1].issues", "concern": "missing canonical issues", "severity": "error"}
    reviews = [_review(score=95, flags=[error_flag])]

    blocked = compute_validation_grade(reviews, race)
    assert blocked["passed"] is False

    race["reviews"] = reviews
    race["reviews"][0]["roster_fingerprint"] = roster_fingerprint(_race(["Cindy Burbank", "Mike Marvin"]))
    invalidate_stale_reviews(race)

    cleared = compute_validation_grade(race["reviews"], race)
    assert cleared["passed"] is True
