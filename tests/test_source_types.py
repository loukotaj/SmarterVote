"""Behavioral tests for pipeline_client.agent.source_types.normalize_source_type."""

from pipeline_client.agent.source_types import normalize_source_type


def test_normalize_source_type_passes_through_valid_type():
    assert normalize_source_type("website") == "website"


def test_normalize_source_type_applies_alias_table():
    assert normalize_source_type("ballotpedia") == "website"
    assert normalize_source_type("Fact Sheet") == "pdf"
    assert normalize_source_type("official site") == "government"
    assert normalize_source_type("social") == "social_media"


def test_normalize_source_type_normalizes_underscores_and_case():
    assert normalize_source_type("SOCIAL_MEDIA") == "social_media"
    assert normalize_source_type("Fresh_Search") == "fresh_search"


def test_normalize_source_type_unrecognized_falls_back_to_url_pdf_sniff():
    assert normalize_source_type("mystery-label", url="https://example.com/plan.pdf") == "pdf"


def test_normalize_source_type_unrecognized_falls_back_to_url_gov_sniff():
    assert normalize_source_type("mystery-label", url="https://senate.gov/bio") == "government"
    assert normalize_source_type("mystery-label", url="https://example.gov") == "government"


def test_normalize_source_type_unrecognized_falls_back_to_url_social_sniff():
    assert normalize_source_type("mystery-label", url="https://facebook.com/candidate") == "social_media"
    assert normalize_source_type("mystery-label", url="https://x.com/candidate") == "social_media"


def test_normalize_source_type_unrecognized_with_no_url_hints_uses_default():
    assert normalize_source_type("mystery-label", url="https://example.com/about") == "website"


def test_normalize_source_type_invalid_default_type_falls_back_to_website():
    assert normalize_source_type(None, default_type="not-a-real-type") == "website"


def test_normalize_source_type_none_uses_default_type():
    assert normalize_source_type(None) == "website"
    assert normalize_source_type("", default_type="government") == "government"
