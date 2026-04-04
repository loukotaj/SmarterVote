"""Ballotpedia HTML scraping helpers.

Provides structured lookups against ``ballotpedia.org`` candidate pages.  Used
both by the image-resolution pipeline (images.py) and exposed as a first-class
agent tool so the LLM can retrieve clean candidate data without burning Serper
quota.

Note: The Ballotpedia MediaWiki API (``/w/api.php``) was disabled; this module
now scrapes the public HTML pages directly.
"""

import logging
import re
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
    """Scrape a Ballotpedia candidate page for structured data.

    Tries the direct URL first (``/First_Last``), then falls back to
    ``Special:Search`` which redirects on a unique match.

    Returns a dict with keys:
        found (bool), page_url (str|None), extract (str|None),
        external_links (list[str]), image_url (str|None)

    Returns ``{"found": False}`` if the candidate is not found or an error occurs.
    """
    empty: Dict[str, Any] = {"found": False}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            # Step 1: try the canonical URL derived from the name
            url_name = candidate_name.strip().replace(" ", "_")
            resp = await client.get(
                f"https://ballotpedia.org/{url_name}",
                headers={"User-Agent": _BROWSER_UA},
            )

            # Step 2: fall back to Special:Search (redirects when there is a unique match)
            if resp.status_code != 200:
                resp = await client.get(
                    "https://ballotpedia.org/Special:Search",
                    params={"search": candidate_name},
                    headers={"User-Agent": _BROWSER_UA},
                )

            if resp.status_code != 200:
                return empty

            page_url = str(resp.url)

            # If we ended up on the search-results page the candidate wasn't found
            if "Special:Search" in page_url:
                return empty

            html = resp.text

            # --- Image: first widget-img inside the infobox -----------------
            image_url: Optional[str] = None
            # The infobox renders as: <img src="https://s3.amazonaws.com/..." class="widget-img" />
            infobox_m = re.search(r'class="infobox person".*?<img\s[^>]*src="([^"]+)"[^>]*>', html, re.DOTALL)
            if infobox_m:
                image_url = infobox_m.group(1)

            # --- Extract: first non-trivial <p> inside mw-parser-output -----
            extract: Optional[str] = None
            parser_idx = html.find("mw-parser-output")
            if parser_idx >= 0:
                for para_m in re.finditer(r"<p>(.*?)</p>", html[parser_idx : parser_idx + 30000], re.DOTALL):
                    text = re.sub(r"<[^>]+>", "", para_m.group(1))
                    # Unescape common HTML entities
                    text = text.replace("&#91;", "[").replace("&#93;", "]").replace("&amp;", "&").strip()
                    if len(text) > 30:
                        extract = text[:1200]
                        break

            # --- External links filtered to research-useful domains ---------
            seen: set = set()
            deduped_links: List[str] = []
            for lnk in re.findall(r'href="(https?://[^"]+)"', html):
                if lnk not in seen and _is_useful_link(lnk):
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
