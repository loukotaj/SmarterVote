from shared.research_manifest import (
    EXPECTED_COVERAGE_COUNT,
    excluded_race_reason,
    get_research_manifest_entry,
    list_research_manifest_entries,
    load_research_manifest,
)


def test_manifest_is_exact_and_excludes_verified_phantoms():
    manifest = load_research_manifest()
    entries = list_research_manifest_entries()
    assert manifest["coverage_count"] == EXPECTED_COVERAGE_COUNT == 507
    assert len(entries) == len({entry["race_id"] for entry in entries}) == 507
    for race_id in ("nd-senate-2026", "vt-senate-2026", "ut-governor-2026", "ut-senate-2026"):
        assert get_research_manifest_entry(race_id) is None
        assert excluded_race_reason(race_id)


def test_manifest_encodes_known_schedule_exceptions():
    assert get_research_manifest_entry("al-house-01-2026")["primary_date"] == "2026-08-11"
    assert get_research_manifest_entry("al-house-03-2026")["primary_date"] == "2026-05-19"
    louisiana = get_research_manifest_entry("la-house-01-2026")
    assert louisiana["event_type"] == "open_primary"
    assert louisiana["primary_date"] == "2026-11-03"
    assert louisiana["runoff_date"] == "2026-12-12"


def test_manifest_corrects_state_independently_of_catalog_display_fields():
    assert get_research_manifest_entry("ut-house-04-2026")["state"] == "Utah"
