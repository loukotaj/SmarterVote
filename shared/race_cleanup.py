"""Deterministic, non-LLM cleanup and evidence checks for RaceJSON."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from shared.run_health import RunFailureReason, record_step_failure

_TEXT_REPLACEMENTS = {
    " after advanced ": " after advancing ",
}


def _clean_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    cleaned = re.sub(r"[ \t]+", " ", value).strip()
    padded = f" {cleaned} "
    for old, new in _TEXT_REPLACEMENTS.items():
        padded = padded.replace(old, new)
    return padded.strip()


def _dedupe_urls(values: Iterable[Any]) -> List[str]:
    urls: List[str] = []
    seen: set[str] = set()
    for value in values:
        url = str(value or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _dedupe_sources(values: Any) -> Any:
    if not isinstance(values, list):
        return values
    result = []
    seen_urls: set[str] = set()
    for source in values:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        result.append(source)
    return result


def _normalize_url_key(value: Any) -> str:
    """Return a comparison key ignoring scheme, ``www.`` and trailing slashes."""
    url = str(value or "").strip().lower()
    if not url:
        return ""
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.rstrip("/")


def _race_retrieved_urls(race_data: Dict[str, Any]) -> set[str]:
    """Return comparison keys for every URL actually retrieved into the race.

    The forecast model is asked to cite only sources the pipeline fetched, but a
    model that cannot recall the exact address sometimes emits a plausible-looking
    address it never visited (an "official results" host with an invented path).
    Those URLs are unreachable and unverifiable, so lineage entries citing them
    must not survive into published data.  Only stored evidence counts here --
    never the forecast's own free-text fields, which is where the invented URLs
    appear in the first place.
    """
    keys: set[str] = set()

    def add(value: Any) -> None:
        key = _normalize_url_key(value)
        if key:
            keys.add(key)

    def add_sources(sources: Any) -> None:
        if not isinstance(sources, list):
            return
        for source in sources:
            if isinstance(source, dict):
                add(source.get("url"))
            elif isinstance(source, str):
                add(source)

    for field in ("ballotpedia_url", "how_to_vote_url", "register_to_vote_url"):
        add(race_data.get(field))

    for poll in race_data.get("polling", []) or []:
        if isinstance(poll, dict):
            add(poll.get("source_url"))

    forecast = race_data.get("forecast")
    if isinstance(forecast, dict):
        for signal in forecast.get("market_signals", []) or []:
            if isinstance(signal, dict):
                add(signal.get("url"))

    for candidate in race_data.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        add(candidate.get("website"))
        add(candidate.get("donor_source_url"))
        add(candidate.get("voting_source_url"))
        for field in ("summary_sources", "roster_sources", "donor_sources", "voting_sources", "links"):
            add_sources(candidate.get(field))
        issues = candidate.get("issues")
        if isinstance(issues, dict):
            for issue in issues.values():
                if isinstance(issue, dict):
                    add_sources(issue.get("sources"))

    return keys


def _forecast_evidence_urls(race_data: Dict[str, Any]) -> List[str]:
    urls: List[Any] = []
    for poll in race_data.get("polling", []):
        if isinstance(poll, dict):
            urls.append(poll.get("source_url"))
    forecast = race_data.get("forecast")
    if isinstance(forecast, dict):
        for signal in forecast.get("market_signals", []):
            if isinstance(signal, dict):
                urls.append(signal.get("url"))
    for candidate in race_data.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        urls.append(candidate.get("donor_source_url"))
        for source in candidate.get("donor_sources", []):
            if isinstance(source, dict):
                urls.append(source.get("url"))
    return _dedupe_urls(urls)


def cleanup_race_data(race_data: Dict[str, Any]) -> Dict[str, int]:
    """Apply safe text/source normalization and return mutation counts."""
    text_changes = 0
    source_duplicates_removed = 0
    forecast_sources_added = 0
    invalid_social_links_removed = 0
    placeholder_fields_cleared = 0
    fabricated_lineage_removed = 0

    for field in ("title", "description", "polling_note"):
        before = race_data.get(field)
        after = _clean_text(before)
        if after != before:
            race_data[field] = after
            text_changes += 1

    description = str(race_data.get("description") or "")
    jurisdiction = str(race_data.get("jurisdiction") or "").strip()
    district_match = re.search(r"\b\d+(?:st|nd|rd|th) Congressional District race\b", description, re.IGNORECASE)
    if jurisdiction and district_match:
        damaged_prefix = description[: district_match.start()]
        if damaged_prefix.count("'s") >= 4 or any(ord(char) > 127 for char in damaged_prefix):
            race_data["description"] = f"{jurisdiction} race{description[district_match.end():]}"
            text_changes += 1

    for candidate in race_data.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        for field in ("name", "summary", "donor_summary", "voting_summary"):
            before = candidate.get(field)
            after = _clean_text(before)
            if after != before:
                candidate[field] = after
                text_changes += 1
        for field in ("summary_sources", "donor_sources", "voting_sources", "roster_sources"):
            before = candidate.get(field)
            after = _dedupe_sources(before)
            if isinstance(before, list) and isinstance(after, list):
                source_duplicates_removed += len(before) - len(after)
                candidate[field] = after
        links = candidate.get("links")
        if isinstance(links, list):
            before_count = len(links)
            candidate["links"] = _dedupe_sources(links)
            source_duplicates_removed += before_count - len(candidate["links"])
        social_media = candidate.get("social_media")
        if isinstance(social_media, dict):
            cleaned_social_media = {
                str(platform): url.strip() for platform, url in social_media.items() if isinstance(url, str) and url.strip()
            }
            invalid_social_links_removed += len(social_media) - len(cleaned_social_media)
            candidate["social_media"] = cleaned_social_media
        # Years are Optional[int] in the schema, so an unknown year is None. A
        # model that reached for 0 as a "not known" sentinel writes data that
        # reviewers correctly flag as an invalid placeholder — costing grade
        # points for a defect no amount of further research can resolve. Clear
        # it here, before the review phase reads the race.
        for history_field, year_fields in (
            ("education", ("year",)),
            ("career_history", ("start_year", "end_year")),
        ):
            entries = candidate.get(history_field)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for year_field in year_fields:
                    if entry.get(year_field) == 0:
                        entry[year_field] = None
                        placeholder_fields_cleared += 1
                for text_field in ("degree", "field", "description", "organization"):
                    value = entry.get(text_field)
                    if isinstance(value, str) and not value.strip():
                        entry[text_field] = None
                        placeholder_fields_cleared += 1

        issues = candidate.get("issues")
        if isinstance(issues, dict):
            for issue in issues.values():
                if not isinstance(issue, dict):
                    continue
                before = issue.get("stance")
                after = _clean_text(before)
                if after != before:
                    issue["stance"] = after
                    text_changes += 1
                sources = issue.get("sources")
                deduped = _dedupe_sources(sources)
                if isinstance(sources, list) and isinstance(deduped, list):
                    source_duplicates_removed += len(sources) - len(deduped)
                    issue["sources"] = deduped

    forecast = race_data.get("forecast")
    if isinstance(forecast, dict):
        for field in ("rationale", "takeaway", "uncertainty"):
            before = forecast.get(field)
            after = _clean_text(before)
            if after != before:
                forecast[field] = after
                text_changes += 1
        reasons = forecast.get("key_reasons")
        if isinstance(reasons, list):
            cleaned_reasons = [_clean_text(reason) for reason in reasons if _clean_text(reason)]
            if cleaned_reasons != reasons:
                forecast["key_reasons"] = cleaned_reasons
                text_changes += 1
        existing_urls = _dedupe_urls(forecast.get("source_urls") or [])
        inferred_urls = _forecast_evidence_urls(race_data)
        merged_urls = _dedupe_urls([*existing_urls, *inferred_urls])
        source_duplicates_removed += max(0, len(forecast.get("source_urls") or []) - len(existing_urls))
        forecast_sources_added = len(merged_urls) - len(existing_urls)
        forecast["source_urls"] = merged_urls
        supplied_lineage = [
            item
            for item in forecast.get("evidence_lineage") or []
            if isinstance(item, dict) and item.get("claim") and item.get("source_url")
        ]
        retrieved_keys = _race_retrieved_urls(race_data)
        retrieved_keys.update(_normalize_url_key(url) for url in inferred_urls)
        existing_lineage = []
        for item in supplied_lineage:
            if _normalize_url_key(item.get("source_url")) in retrieved_keys:
                existing_lineage.append(item)
            else:
                fabricated_lineage_removed += 1
        lineage_urls = {str(item["source_url"]) for item in existing_lineage}
        poll_urls = {
            str(poll.get("source_url"))
            for poll in race_data.get("polling", [])
            if isinstance(poll, dict) and poll.get("source_url")
        }
        market_urls = {
            str(signal.get("url"))
            for signal in forecast.get("market_signals", [])
            if isinstance(signal, dict) and signal.get("url")
        }
        for url in inferred_urls:
            if url in lineage_urls:
                continue
            kind = "polling" if url in poll_urls else "market" if url in market_urls else "finance"
            existing_lineage.append(
                {
                    "claim": f"{kind.replace('_', ' ').title()} input used by the forecast",
                    "source_url": url,
                    "kind": kind,
                    "inferred": True,
                }
            )
        forecast["evidence_lineage"] = existing_lineage

    return {
        "text_changes": text_changes,
        "source_duplicates_removed": source_duplicates_removed,
        "forecast_sources_added": forecast_sources_added,
        "invalid_social_links_removed": invalid_social_links_removed,
        "placeholder_fields_cleared": placeholder_fields_cleared,
        "fabricated_lineage_removed": fabricated_lineage_removed,
    }


def forecast_evidence_gaps(race_data: Dict[str, Any]) -> List[str]:
    """Return deterministic claim/source mismatches for a narrative forecast."""
    forecast = race_data.get("forecast")
    if not isinstance(forecast, dict):
        return []
    claims = (
        " ".join(
            [
                str(forecast.get("rationale") or ""),
                str(forecast.get("takeaway") or ""),
                " ".join(str(reason) for reason in forecast.get("key_reasons") or []),
            ]
        )
        .strip()
        .casefold()
    )
    urls = _dedupe_urls(forecast.get("source_urls") or [])
    lowered_urls = " ".join(url.casefold() for url in urls)
    gaps: List[str] = []
    if claims and not urls:
        gaps.append("missing_explicit_sources")
    claim_domains = {
        "cook": "cookpolitical.com",
        "inside elections": "insideelections.com",
        "swing state project": "swingstateproject.com",
    }
    for marker, domain in claim_domains.items():
        if marker in claims and domain not in lowered_urls:
            gaps.append(f"missing_{marker.replace(' ', '_')}_source")
    if "poll" in claims and int(forecast.get("based_on_poll_count") or 0) > 0:
        polling_urls = {
            str(poll.get("source_url") or "").strip()
            for poll in race_data.get("polling", [])
            if isinstance(poll, dict) and poll.get("source_url")
        }
        if not polling_urls.intersection(urls):
            gaps.append("missing_poll_source")
    return gaps


#: Having no forecast sources at all is not a run-health problem. When search
#: turns up nothing usable, incumbency plus partisan lean is the honest basis for
#: a prediction, and saying so is the correct outcome rather than a degraded run.
#: It stays in ``forecast_evidence_gaps`` as an informational coverage signal.
#: The remaining gaps are different in kind: those fire only when the forecast
#: *names* a specific authority (Cook, Inside Elections) or claims polling it
#: never cites, which is an unsupported attribution worth degrading on.
_NON_DEGRADING_FORECAST_GAPS = frozenset({"missing_explicit_sources"})


def validate_forecast_evidence(race_data: Dict[str, Any]) -> bool:
    """Register a degraded run-health finding for deterministic evidence gaps."""
    forecast = race_data.get("forecast")
    if not isinstance(forecast, dict):
        return True
    gaps = [gap for gap in forecast_evidence_gaps(race_data) if gap not in _NON_DEGRADING_FORECAST_GAPS]
    if gaps:
        record_step_failure(
            race_data,
            "forecast",
            RunFailureReason.STEP_NO_DATA,
            "Forecast evidence gaps: " + ", ".join(gaps),
        )
        return False
    return True
