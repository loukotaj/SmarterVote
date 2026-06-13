"""Candidate selection and source-hint helpers for phase orchestration."""

from typing import Any, Dict, List, Optional


def _scale_iterations(base: int, n_candidates: int, per_candidate: int, minimum: int = 12) -> int:
    """Return an iteration budget scaled to the number of candidates."""
    return max(base, n_candidates * per_candidate + minimum)


def _candidate_info_score(candidate: Dict[str, Any]) -> int:
    """Score a candidate by how much issue data they already have."""
    issues = candidate.get("issues", {})
    score = 0
    for v in issues.values():
        if isinstance(v, dict) and v.get("stance"):
            score += 1
    return score


def _select_candidates_for_research(
    candidate_names: List[str],
    race_json: Dict[str, Any],
    *,
    max_candidates: Optional[int],
    target_no_info: bool,
    log: Any,
) -> List[str]:
    """Return the (possibly truncated) list of candidates to research.

    Sorts candidates by existing info density.  When *target_no_info* is True
    the least-informed candidates come first; otherwise the most-informed do.
    """
    if max_candidates is None and not target_no_info:
        return candidate_names

    cand_by_name: Dict[str, Dict[str, Any]] = {
        str(c.get("name")).strip(): c
        for c in race_json.get("candidates", [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    }
    scored = [(name, _candidate_info_score(cand_by_name.get(name, {}))) for name in candidate_names]
    scored.sort(key=lambda t: t[1], reverse=not target_no_info)

    selected = [name for name, _ in scored]
    if max_candidates is not None and max_candidates < len(selected):
        skipped = selected[max_candidates:]
        selected = selected[:max_candidates]
        log(
            "info",
            f"  Candidate limit: researching {len(selected)} of {len(candidate_names)} " f"(skipped: {', '.join(skipped)})",
        )
    return selected


def _select_target_candidates(
    available_names: List[str],
    target_names: Optional[List[str]],
    log: Any,
) -> List[str]:
    """Filter available candidates to an explicit target list, if provided."""
    if not target_names:
        return available_names

    wanted = [n.strip() for n in target_names if isinstance(n, str) and n.strip()]
    if not wanted:
        return available_names

    by_lower = {n.lower(): n for n in available_names}
    selected: List[str] = []
    missing: List[str] = []
    for name in wanted:
        match = by_lower.get(name.lower())
        if match:
            if match not in selected:
                selected.append(match)
        else:
            missing.append(name)

    if missing:
        log("warning", f"  Candidate filter ignored unknown names: {', '.join(missing)}")
    if not selected:
        raise ValueError(
            "No candidate names in candidate_names matched this race. " f"Available: {', '.join(available_names)}"
        )

    log("info", f"  Candidate filter active: {', '.join(selected)}")
    return selected


async def _candidate_source_hints(
    race_json: Dict[str, Any],
    candidate_name: str,
) -> tuple[str, List[str]]:
    """Return known website and likely issue/policy URLs for candidate prompts."""
    candidate = next(
        (
            c
            for c in race_json.get("candidates", [])
            if isinstance(c, dict) and str(c.get("name") or "").strip() == candidate_name
        ),
        None,
    )
    if not candidate:
        return "(unknown)", []

    website = candidate.get("website") or "(unknown)"
    hints: List[str] = []

    if isinstance(website, str) and website.startswith("http"):
        # Crawl actual homepage links as primary source hints instead of blind guesses
        from .web_tools import get_homepage_policy_links

        crawled_links = await get_homepage_policy_links(website)
        hints.extend(crawled_links)
        # Fall back to standard guesses if crawl returned nothing (maintains backwards compatibility)
        if not crawled_links:
            base = website.rstrip("/")
            hints.extend(
                [
                    f"{base}/issues",
                    f"{base}/issue",
                    f"{base}/policy",
                    f"{base}/policies",
                    f"{base}/priorities",
                    f"{base}/platform",
                ]
            )

    for link in candidate.get("links", []):
        if not isinstance(link, dict):
            continue
        url = link.get("url")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        lowered = url.lower()
        if any(token in lowered for token in ("/issues", "/issue", "policy", "priorities", "platform")):
            hints.append(url)

    deduped: List[str] = []
    seen: set[str] = set()
    for url in hints:
        if url in seen:
            continue
        deduped.append(url)
        seen.add(url)

    return website, deduped[:8]
