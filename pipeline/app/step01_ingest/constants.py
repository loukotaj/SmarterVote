"""Shared constants for Step01 ingestion."""

import re

SLUG_PATTERN = re.compile(
    r"^(?P<state>[a-z]{2})-(?P<office>[a-z]+(?:-[a-z]+)*?)"
    r"(?:-(?P<district>\d{1,2}|al))?-(?P<year>\d{4})"
    r"(?:-(?P<kind>primary|runoff|special))?$",
)

ALLOW = (
    "/issues",
    "/priorities",
    "/platform",
    "/policy",
    "/on-the-issues",
    "/agenda",
    "/plans",
    "/news",
    "/press",
    "/about",
)

DENY = (
    "/donate",
    "/volunteer",
    "/shop",
    "/store",
    "/events",
    "/privacy",
    "/terms",
)
