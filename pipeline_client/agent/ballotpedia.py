"""Ballotpedia MediaWiki API helpers.

Provides structured lookups against ``ballotpedia.org/w/api.php``.  Used both
by the image-resolution pipeline (images.py) and exposed as a first-class agent
tool so the LLM can retrieve clean candidate data without burning Serper quota.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("pipeline")

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# External-link prefixes that are useful for electoral research.
# We filter the full extlinks list down to these so the agent isn't buried in
# social-sharing trackers and other noise.
_USEFUL_LINK_PREFIXES = (
    "house.gov",
    "senate.gov",
    "governor.",
    "fec.gov",
    "votesmart.org",
    "opensecrets.org",
    "followthemoney.org",
    "congress.gov",
    "ballotpedia.org",
    "wikipedia.org",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "linkedin.com",
    # campaign sites — very hard to enumerate exhaustively, so keep everything
    # that survived the other filters and looks like a campaign URL
)


def _is_useful_link(url: str) -> bool:
    """Return True for external links that are likely useful to the research agent."""
    url_lower = url.lower()
    # Always keep government / research / finance / social links
    for prefix in _USEFUL_LINK_PREFIXES:
        if prefix in url_lower:
            return True
    # Keep anything that looks like an official campaign site (contains the
    # candidate's role keyword and ends in a real TLD)
    for keyword in ("forsenate", "forgovernor", "forhouse", "forcongress", "forassembly", "campaign"):
        if keyword in url_lower:
            return True
    return False


async def lookup_candidate_image(candidate_name: str) -> Optional[str]:
    """Return a Ballotpedia thumbnail URL for *candidate_name*, or None.

    Uses ``opensearch`` to find the Ballotpedia page then ``pageimages`` to get
    the thumbnail.  This is a focused helper used by the image-resolution
    pipeline (images.py) — for full candidate data use ``lookup_candidate_data``.
    """
    result = await lookup_candidate_data(candidate_name)
    return result.get("image_url") if result else None


async def lookup_candidate_data(candidate_name: str) -> Dict[str, Any]:
    """Query the Ballotpedia MediaWiki API for structured candidate data.

    Makes two parallel API calls:
    - ``pageimages`` — thumbnail URL (reused by images.py)
    - ``extracts``   — plain-text intro paragraph (clean bio, no HTML)
    - ``extlinks``   — external links on the page (campaign site, FEC, VoteSmart, …)
    - ``info``       — canonical page URL

    Returns a dict with keys:
        found (bool), page_url (str|None), extract (str|None),
        external_links (list[str]), image_url (str|None)

    Returns ``{"found": False}`` if the candidate is not found or an error occurs.
    """
    empty: Dict[str, Any] = {"found": False}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            # Step 1: find the best-matching Ballotpedia page title
            search_resp = await client.get(
                "https://ballotpedia.org/w/api.php",
                params={
                    "action": "opensearch",
                    "search": candidate_name,
                    "limit": "3",
                    "format": "json",
                },
                headers={"User-Agent": _BROWSER_UA},
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()
            titles: List[str] = search_data[1] if len(search_data) > 1 else []
            if not titles:
                return empty

            # Use the first (best-match) title
            title = titles[0]

            # Step 2: fetch pageimages + extracts + extlinks + info in one call
            detail_resp = await client.get(
                "https://ballotpedia.org/w/api.php",
                params={
                    "action": "query",
                    "titles": title,
                    "prop": "pageimages|extracts|extlinks|info",
                    "pithumbsize": "400",
                    "exintro": "1",
                    "explaintext": "1",
                    "inprop": "url",
                    "format": "json",
                    "redirects": "1",
                },
                headers={"User-Agent": _BROWSER_UA},
            )
            detail_resp.raise_for_status()
            data = detail_resp.json()

            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return empty

            page = next(iter(pages.values()))
            if page.get("missing") is not None:
                return empty

            # Extract thumbnail
            image_url: Optional[str] = page.get("thumbnail", {}).get("source") or None

            # Extract plain-text intro (may be empty for stubs)
            extract: Optional[str] = (page.get("extract") or "").strip() or None

            # Canonical page URL
            page_url: Optional[str] = page.get("fullurl") or None

            # External links — filter to research-useful ones
            raw_links: List[Dict] = page.get("extlinks", [])
            external_links: List[str] = [
                lnk.get("*", "") or lnk.get("url", "")
                for lnk in raw_links
                if _is_useful_link(lnk.get("*", "") or lnk.get("url", ""))
            ]
            # Deduplicate while preserving order
            seen: set = set()
            deduped_links: List[str] = []
            for lnk in external_links:
                if lnk and lnk not in seen:
                    seen.add(lnk)
                    deduped_links.append(lnk)

            return {
                "found": True,
                "page_url": page_url,
                "extract": extract,
                "external_links": deduped_links,
                "image_url": image_url,
            }

    except Exception as exc:
        logger.debug("Ballotpedia lookup failed for %r: %s", candidate_name, exc)
        return empty
