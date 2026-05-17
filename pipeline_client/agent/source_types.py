"""Helpers for normalizing agent-provided source metadata."""

from __future__ import annotations

from typing import Any

VALID_SOURCE_TYPES = {"website", "finance", "pdf", "api", "social_media", "news", "government", "fresh_search"}

SOURCE_TYPE_ALIASES = {
    "advocacy": "website",
    "analysis": "website",
    "ballotpedia": "website",
    "campaign": "website",
    "campaign issue page": "website",
    "campaign policy page": "website",
    "campaign-issue-page": "website",
    "campaign-issues": "website",
    "campaign-policy-page": "website",
    "campaign_issues": "website",
    "campaign_plan": "website",
    "campaign_platform": "website",
    "fact sheet": "pdf",
    "fact-sheet": "pdf",
    "govtrack": "government",
    "government proclamation": "government",
    "government-proclamation": "government",
    "legislature": "government",
    "official": "government",
    "official campaign page": "government",
    "official page": "government",
    "official policy page": "government",
    "official press release": "government",
    "official senate page": "government",
    "official site": "government",
    "official-site": "government",
    "official-press-release": "government",
    "official-senate-education-priorities": "government",
    "official_policy": "government",
    "official_policy_page": "government",
    "policy document": "pdf",
    "policy quote": "website",
    "policy-quote": "website",
    "press release": "government",
    "press releases": "government",
    "social": "social_media",
    "votesmart": "website",
    "wiki": "website",
}


def normalize_source_type(source_type: Any, *, url: str | None = None, default_type: str = "website") -> str:
    """Return a schema-valid SourceType value for free-form agent source labels."""
    value = str(source_type or default_type).strip().lower().replace("_", " ")
    normalized = SOURCE_TYPE_ALIASES.get(value, value.replace(" ", "_"))
    if normalized in VALID_SOURCE_TYPES:
        return normalized

    lower_url = (url or "").lower()
    if lower_url.endswith(".pdf") or ".pdf" in lower_url:
        return "pdf"
    if ".gov/" in lower_url or lower_url.endswith(".gov"):
        return "government"
    if any(domain in lower_url for domain in ("facebook.com", "instagram.com", "x.com/", "twitter.com")):
        return "social_media"

    return default_type if default_type in VALID_SOURCE_TYPES else "website"
