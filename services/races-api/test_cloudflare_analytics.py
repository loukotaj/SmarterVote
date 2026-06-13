"""Tests for Cloudflare Web Analytics aggregation."""

import asyncio

import cloudflare_analytics


def test_unconfigured_summary_is_explicit(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ANALYTICS_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ANALYTICS_ACCOUNT_TAG", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ANALYTICS_SITE_TAG", raising=False)

    result = asyncio.run(cloudflare_analytics.CloudflareAnalytics().get_summary(24))

    assert result["configured"] is False
    assert result["pageviews"] == 0
    assert "not configured" in result["error"]


def test_adaptive_counts_are_already_estimated():
    group = {"count": 12, "avg": {"sampleInterval": 10}, "sum": {"visits": 45}}

    assert cloudflare_analytics._estimated_count(group) == 12
    assert cloudflare_analytics._visits(group) == 45


def test_dimension_rows_normalize_empty_labels():
    rows = cloudflare_analytics._dimension_rows(
        [{"count": 2, "avg": {"sampleInterval": 5}, "sum": {"visits": 3}, "dimensions": {"refererHost": ""}}],
        "refererHost",
        empty_label="Direct",
    )

    assert rows == [{"name": "Direct", "pageviews": 2, "visits": 3}]
