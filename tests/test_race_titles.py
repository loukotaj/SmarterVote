from shared.race_titles import canonical_race_title


def test_canonical_race_title_normalizes_federal_races():
    assert (
        canonical_race_title({"id": "ga-senate-2026", "state": "Georgia", "office": "United States Senate"})
        == "2026 Georgia U.S. Senate Election"
    )
    assert (
        canonical_race_title({"id": "fl-senate-2026-special", "state": "Florida", "office": "U.S. Senate"})
        == "2026 Florida U.S. Senate Special Election"
    )
    assert (
        canonical_race_title({"id": "ga-house-10-2026", "state": "Georgia", "office": "U.S. House of Representatives"})
        == "2026 Georgia's 10th Congressional District Election"
    )
    assert (
        canonical_race_title({"id": "wa-01-house-2026", "state": "Washington", "office": "U.S. Representative"})
        == "2026 Washington's 1st Congressional District Election"
    )
    assert (
        canonical_race_title(
            {
                "id": "e2e-oh-house-05-2026",
                "state": "Ohio",
                "office": "U.S. House",
                "jurisdiction": "Ohio's 5th Congressional District",
            }
        )
        == "2026 Ohio's 5th Congressional District Election"
    )


def test_canonical_race_title_normalizes_governor_and_preserves_other_offices():
    assert (
        canonical_race_title({"id": "ga-governor-2026", "state": "Georgia", "office": "Governor of Georgia"})
        == "2026 Georgia Governor Election"
    )
    assert (
        canonical_race_title(
            {
                "id": "md-governor-2026",
                "state": "Maryland",
                "office": "Governor and Lieutenant Governor of Maryland",
            }
        )
        == "2026 Maryland Governor and Lieutenant Governor Election"
    )
    assert (
        canonical_race_title(
            {
                "id": "ar-supreme-court-2026",
                "title": "Arkansas Supreme Court election, 2026",
                "office": "Arkansas Supreme Court",
            }
        )
        == "Arkansas Supreme Court election, 2026"
    )
