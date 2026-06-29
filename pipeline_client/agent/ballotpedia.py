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
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import quote, quote_plus

import httpx

logger = logging.getLogger("pipeline")

_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_UNUSABLE_MARKERS = (
    "verify that you're not a robot",
    "verify you are not a robot",
    "enable javascript",
    "captcha",
    "access denied",
)

# Containers that only appear on a real Ballotpedia article / election page.
# Normal pages embed a hidden reCAPTCHA widget (``g-recaptcha``) and a
# ``<noscript>`` fallback, so the bare markers above false-positive on fully
# usable content. We only treat a page as a bot challenge when none of these
# real-content containers are present.
_CONTENT_MARKERS = (
    "mw-parser-output",
    "votebox",
    'class="infobox',
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
                fallback_image = await _lookup_candidate_thumbnail_by_convention(client, candidate_name)
                if fallback_image:
                    return {
                        "found": True,
                        "page_url": f"https://ballotpedia.org/{url_name}",
                        "extract": None,
                        "external_links": [],
                        "image_url": fallback_image,
                    }
                return empty

            page_url = str(resp.url)

            # If we ended up on the search-results page the candidate wasn't found
            if "Special:Search" in page_url:
                fallback_image = await _lookup_candidate_thumbnail_by_convention(client, candidate_name)
                if fallback_image:
                    return {
                        "found": True,
                        "page_url": f"https://ballotpedia.org/{url_name}",
                        "extract": None,
                        "external_links": [],
                        "image_url": fallback_image,
                    }
                return empty

            html = resp.text
            if _is_unusable_ballotpedia_html(html):
                proxy_resp = await client.get(
                    f"https://r.jina.ai/{page_url}",
                    headers={"User-Agent": _BROWSER_UA},
                )
                if proxy_resp.status_code == 200 and not _is_unusable_ballotpedia_html(proxy_resp.text):
                    html = proxy_resp.text
                else:
                    fallback_image = await _lookup_candidate_thumbnail_by_convention(client, candidate_name)
                    if fallback_image:
                        return {
                            "found": True,
                            "page_url": page_url,
                            "extract": None,
                            "external_links": [],
                            "image_url": fallback_image,
                        }
                    return empty

            # --- Image: first widget-img inside the infobox -----------------
            image_url: Optional[str] = None
            # The infobox renders as: <img src="https://s3.amazonaws.com/..." class="widget-img" />
            infobox_m = re.search(r'class="infobox person".*?<img\s[^>]*src="([^"]+)"[^>]*>', html, re.DOTALL)
            if infobox_m:
                image_url = infobox_m.group(1)
            if not image_url:
                image_m = re.search(
                    r"https://s3\.amazonaws\.com/ballotpedia-api4/files/thumbs/[^\s)\"'<]+",
                    html,
                    re.IGNORECASE,
                )
                if image_m:
                    image_url = image_m.group(0)
            if not image_url:
                image_url = await _lookup_candidate_thumbnail_by_convention(client, candidate_name)

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
        logger.warning("Ballotpedia lookup failed for %r: %s", candidate_name, exc)
        return empty


def _is_unusable_ballotpedia_html(html: str) -> bool:
    lowered = (html or "").lower()
    if not lowered.strip():
        return True
    # A real article/election page contains a MediaWiki content container; if one
    # is present, treat the page as usable even though it embeds a hidden
    # reCAPTCHA widget and <noscript> fallback (which would otherwise trip the
    # bare "captcha"/"enable javascript" markers below).
    if any(marker in lowered for marker in _CONTENT_MARKERS):
        return False
    return any(marker in lowered for marker in _UNUSABLE_MARKERS)


async def _lookup_candidate_thumbnail_by_convention(client: httpx.AsyncClient, candidate_name: str) -> Optional[str]:
    """Try Ballotpedia's stable thumbnail path when page HTML is blocked."""
    base_name = quote(candidate_name.strip().replace(" ", "_"), safe="_()")
    if not base_name:
        return None
    for ext in (".jpg", ".jpeg", ".png"):
        url = f"https://s3.amazonaws.com/ballotpedia-api4/files/thumbs/200/300/{base_name}{ext}"
        try:
            resp = await client.head(url, headers={"User-Agent": _BROWSER_UA})
            if resp.status_code < 400:
                return url
            if resp.status_code in (405, 501):
                get_resp = await client.get(url, headers={"User-Agent": _BROWSER_UA, "Range": "bytes=0-0"})
                if get_resp.status_code in (200, 206):
                    return url
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Race / election page lookup
# ---------------------------------------------------------------------------

_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}


def _district_label_from_parts(district_parts: List[str]) -> str:
    district_num_str = district_parts[0] if district_parts else ""
    try:
        n = int(district_num_str)
        suffix_map = {1: "st", 2: "nd", 3: "rd"}
        ordinal = suffix_map.get(n % 10 if n % 100 not in (11, 12, 13) else 0, "th")
        return f"{n}{ordinal}"
    except ValueError:
        return district_num_str or "at-large"


def _state_possessive_url(state_url: str) -> str:
    return f"{state_url}'" if state_url.endswith("s") else f"{state_url}'s"


def _parse_house_race_parts(race_id: str) -> Optional[tuple[str, str, str]]:
    parts = race_id.lower().split("-")
    if len(parts) < 4:
        return None

    state_abbr = parts[0].upper()
    state_name = _STATE_NAMES.get(state_abbr)
    if not state_name:
        return None

    year: Optional[str] = None
    office_parts: List[str] = []
    for i, p in enumerate(parts[1:], 1):
        if p.isdigit() and len(p) == 4:
            year = p
            office_parts = parts[1:i]
            break
    if not year or "house" not in office_parts:
        return None

    district_parts = [p for p in office_parts if p != "house"]
    state_url = state_name.replace(" ", "_")
    return state_url, _district_label_from_parts(district_parts), year


def _race_id_to_ballotpedia_district_url(race_id: str) -> Optional[str]:
    house_parts = _parse_house_race_parts(race_id)
    if not house_parts:
        return None
    state_url, district_label, _year = house_parts
    return f"https://ballotpedia.org/{_state_possessive_url(state_url)}_{district_label}_Congressional_District"


def default_ballotpedia_race_url(race_id: str) -> Optional[str]:
    """Return the best deterministic race-level Ballotpedia URL for a race id."""
    return _race_id_to_ballotpedia_district_url(race_id) or _race_id_to_ballotpedia_url(race_id)


def _race_id_to_ballotpedia_url(race_id: str) -> Optional[str]:
    """Attempt to derive a Ballotpedia election page URL from a race_id.

    Handles common patterns:
      {state}-senate-{year}          → United_States_Senate_election_in_{State},{year}
      {state}-governor-{year}        → {State}_gubernatorial_election,{year}
      {state}-house-{district}-{year}→ {State}'s_{N}th/st/nd/rd_congressional_district_election,{year}
      {state}-senate-{year}-special  → United_States_Senate_special_election_in_{State},{year}
    """
    parts = race_id.lower().split("-")
    if len(parts) < 3:
        return None

    state_abbr = parts[0].upper()
    state_name = _STATE_NAMES.get(state_abbr)
    if not state_name:
        return None

    # Detect year (last numeric part or second-to-last if suffix like "special")
    year: Optional[str] = None
    suffix = ""
    office_parts: List[str] = []
    for i, p in enumerate(parts[1:], 1):
        if p.isdigit() and len(p) == 4:
            year = p
            remaining = parts[i + 1 :]
            suffix = "_".join(remaining) if remaining else ""
            office_parts = parts[1:i]
            break
    if not year:
        return None

    office = "_".join(office_parts)
    state_url = state_name.replace(" ", "_")
    special_infix = "_special" if "special" in suffix else ""

    # Support both {state}-house-{district}-{year} and {state}-{district}-house-{year}
    is_house = "house" in office_parts
    district_parts = []
    if is_house:
        district_parts = [p for p in office_parts if p != "house"]
        office = "house"

    if office == "senate":
        title = f"United_States_Senate{special_infix}_election_in_{state_url},_{year}"
    elif office == "governor":
        title = f"{state_url}_gubernatorial{special_infix}_election,_{year}"
    elif office.startswith("house"):
        district_label = _district_label_from_parts(district_parts)
        title = f"{_state_possessive_url(state_url)}_{district_label}_Congressional_District_election,_{year}"
    elif "attorney" in office or "ag" == office:
        title = f"Attorney_General_election_in_{state_url},_{year}"
    elif "secretary" in office or "sos" == office:
        title = f"Secretary_of_State_election_in_{state_url},_{year}"
    elif "treasurer" in office:
        title = f"State_Treasurer_election_in_{state_url},_{year}"
    elif "lieutenant" in office or "lt-gov" in office:
        title = f"Lieutenant_Governor_election_in_{state_url},_{year}"
    else:
        return None

    return f"https://ballotpedia.org/{title}"


def _race_id_to_search_query(race_id: str) -> str:
    parts = race_id.lower().split("-")
    state_name = _STATE_NAMES.get(parts[0].upper(), parts[0].upper() if parts else "")
    year = next((part for part in parts if part.isdigit() and len(part) == 4), "")
    office_parts = [part for part in parts[1:] if part != year and part != "special"]
    if "house" in office_parts:
        district_parts = [part for part in office_parts if part != "house"]
        district = _district_label_from_parts(district_parts)
        return f"{state_name} {district} Congressional District election {year}".strip()
    if "senate" in office_parts:
        special = " special" if "special" in parts else ""
        return f"United States Senate{special} election in {state_name} {year}".strip()
    if "governor" in office_parts:
        return f"{state_name} gubernatorial election {year}".strip()
    return f"{race_id} Ballotpedia".strip()


# ---------------------------------------------------------------------------
# Wikipedia election-page fallback
#
# Ballotpedia bot-blocks data-center IPs (e.g. Cloud Run), so the election
# lookup frequently fails in production even though the page is fine from a
# residential IP. Wikipedia is not IP-blocked and its election articles list
# the full candidate roster, so we use it as an authoritative fallback.
# ---------------------------------------------------------------------------

_WIKI_PARTY_KEYWORDS = (
    ("republican", "Republican"),
    ("democratic", "Democratic"),
    ("democrat", "Democratic"),
    ("libertarian", "Libertarian"),
    ("green", "Green"),
    ("independent", "Independent"),
    ("constitution", "Constitution"),
)

# Section labels (anywhere in a list item's heading trail) that mean the listed
# people are NOT active candidates and must be skipped.
_WIKI_EXCLUDE_SECTIONS = (
    "endorsement",
    "withdrawn",
    "declined",
    "disqualified",
    "potential",
    "removed",
    "defeated",
    "eliminated",
    "did not",
)


def _race_id_to_wikipedia_url(race_id: str) -> Optional[str]:
    """Derive a Wikipedia election-article URL from a race_id (governor/senate)."""
    parts = race_id.lower().split("-")
    if len(parts) < 3:
        return None
    state_name = _STATE_NAMES.get(parts[0].upper())
    if not state_name:
        return None

    year: Optional[str] = None
    office_parts: List[str] = []
    suffix = ""
    for i, p in enumerate(parts[1:], 1):
        if p.isdigit() and len(p) == 4:
            year = p
            office_parts = parts[1:i]
            suffix = "_".join(parts[i + 1 :])
            break
    if not year:
        return None

    state_url = state_name.replace(" ", "_")
    special = "_special" if ("special" in suffix or "special" in office_parts) else ""

    if "governor" in office_parts:
        return f"https://en.wikipedia.org/wiki/{year}_{state_url}_gubernatorial{special}_election"
    if "senate" in office_parts:
        return f"https://en.wikipedia.org/wiki/{year}_United_States_Senate{special}_election_in_{state_url}"
    return None


def _parse_wikipedia_candidate_list(html: str) -> List[Dict[str, Any]]:
    """Parse declared candidates from a Wikipedia election article.

    Candidates appear as ``<li>`` items whose heading trail contains a party
    section (e.g. "Republican primary") and a "Candidates" subsection, while
    endorsements/withdrawn entries live under other subsections that we skip.
    """
    candidates: List[Dict[str, Any]] = []
    seen: set = set()
    trail: List[str] = []

    for lvl, htext, litext in re.findall(r"<h([1-6])[^>]*>(.*?)</h\1>|<li[^>]*>(.*?)</li>", html, re.DOTALL):
        if htext:
            heading = unescape(re.sub(r"&#\d+;", "", re.sub(r"<[^>]+>", "", htext))).strip()
            trail = trail[: int(lvl) - 1] + [heading]
            continue

        trail_lower = " > ".join(trail).lower()
        # Only list items inside a "Candidates" subsection of a party section.
        if "candidate" not in trail_lower:
            continue
        if any(marker in trail_lower for marker in _WIKI_EXCLUDE_SECTIONS):
            continue

        # Use the NEAREST (deepest) party heading in the trail, so a leaked
        # ancestor party section can't override the candidate's actual party.
        party = None
        for heading in reversed(trail):
            heading_lower = heading.lower()
            for keyword, label in _WIKI_PARTY_KEYWORDS:
                if keyword in heading_lower:
                    party = label
                    break
            if party:
                break
        if not party:
            continue

        text = unescape(re.sub(r"&#\d+;", "", re.sub(r"<[^>]+>", "", litext)))
        text = re.sub(r"\s+", " ", text).strip()
        # Candidate entries read "Name, descriptor" — take the name, drop footnote digits.
        name = re.sub(r"\d+$", "", text.split(",")[0]).strip()
        if len(name.split()) < 2 or not re.match(r"^[A-Za-z.'\- ]+$", name):
            continue

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "name": name,
                "party": party,
                "incumbent": "incumbent" in text.lower(),
            }
        )

    return candidates


def _parse_candidate_list_from_html(html: str) -> List[Dict[str, Any]]:
    """Parse a candidate list from a Ballotpedia election page.

    Returns a list of dicts with keys: name, party, incumbent (bool).
    """
    candidates: List[Dict[str, Any]] = []
    seen: set = set()
    current_html = html.split('id="Past_elections"', 1)[0]

    # Ballotpedia pages include many unrelated/historical tables. Only parse the
    # current election's votebox sections headed "... election" or "... convention".
    for section_m in re.finditer(
        r"<h4>(?P<label>[^<]*(?:election|convention)[^<]*)</h4>(?P<body>.*?)(?=<h4>|<h3>|<h2>|$)",
        current_html,
        re.DOTALL | re.IGNORECASE,
    ):
        label = unescape(section_m.group("label"))
        body = section_m.group("body")

        is_primary = "primary" in label.lower()
        # Completed primary tables mark the advancing candidate with a winner class or checkmark.
        winner_pattern = r"class=['\"][^'\"]*winner[^'\"]*['\"]|&#10004;"
        is_completed = bool(re.search(winner_pattern, body, re.IGNORECASE))

        section_party = "Unknown"
        for p_kw, p_label in [
            ("republican", "Republican"),
            ("democratic", "Democratic"),
            ("democrat", "Democratic"),
            ("libertarian", "Libertarian"),
            ("green", "Green"),
            ("independent", "Independent"),
            ("constitution", "Constitution"),
        ]:
            if p_kw in label.lower() or p_kw in body[:500].lower():
                section_party = p_label
                break

        for row_m in re.finditer(r'<tr[^>]*class="[^"]*results_row[^"]*"[^>]*>.*?</tr>', body, re.DOTALL | re.IGNORECASE):
            row_html = row_m.group(0)

            # Skip candidates who lost the primary explicitly
            if is_primary and is_completed:
                is_winner = bool(re.search(winner_pattern, row_html, re.IGNORECASE))
                if not is_winner:
                    continue

            party_m = re.search(r"\((R|D|L|I|G|C)\)", row_html)
            if party_m:
                party_map = {
                    "R": "Republican",
                    "D": "Democratic",
                    "L": "Libertarian",
                    "I": "Independent",
                    "G": "Green",
                    "C": "Constitution",
                }
                party = party_map.get(party_m.group(1), section_party)
            else:
                party = section_party

            name_m = re.search(
                r'class="votebox-results-cell--text"[^>]*>.*?<a href="https://ballotpedia\.org/([^"#?]+)"[^>]*>(.*?)</a>',
                row_html,
                re.DOTALL | re.IGNORECASE,
            )
            if not name_m:
                name_m = re.search(
                    r'class="votebox-results-cell--text"[^>]*>.*?<a href="/([^"#?]+)"[^>]*>(.*?)</a>',
                    row_html,
                    re.DOTALL | re.IGNORECASE,
                )
            if not name_m:
                continue

            page_slug = unescape(name_m.group(1))
            if any(kw in page_slug.lower() for kw in ("election", "primary", "general", "party", "district")):
                continue
            raw_name = re.sub(r"<[^>]+>", "", name_m.group(2)).strip()
            raw_name = unescape(raw_name)
            slug_name = re.sub(r"_\([^)]*\)$", "", page_slug).replace("_", " ").strip()
            if slug_name and len(slug_name.split()) >= len(raw_name.split()):
                raw_name = slug_name
            if not raw_name or len(raw_name) < 3:
                continue

            incumbent = bool(re.search(r"incumbent", row_html, re.IGNORECASE))
            key = raw_name.lower()
            if key not in seen:
                seen.add(key)
                candidates.append({"name": raw_name, "party": party, "incumbent": incumbent})

    if candidates:
        return candidates

    # Fallback for older/non-votebox pages: scan table rows, preserving legacy behavior.
    for m in re.finditer(r"<tr[^>]*>.*?</tr>", html, re.DOTALL | re.IGNORECASE):
        row_html = m.group(0)
        if "<th" in row_html.lower() and "<td" not in row_html.lower():
            continue
        name_m = re.search(r'href="/([A-Z][^"#?]+)"[^>]*>([^<]+)</a>', row_html)
        if not name_m:
            continue
        raw_name = re.sub(r"<[^>]+>", "", name_m.group(2)).strip()
        raw_name = unescape(raw_name)
        if not raw_name or len(raw_name) < 3:
            continue
        page_slug = name_m.group(1)
        if any(kw in page_slug for kw in ("election", "primary", "general", "party", "district")):
            continue
        row_text = re.sub(r"<[^>]+>", " ", row_html)
        party = "Unknown"
        for p_kw, p_label in [
            ("republican", "Republican"),
            ("democrat", "Democratic"),
            ("libertarian", "Libertarian"),
            ("green", "Green"),
            ("independent", "Independent"),
            ("constitution", "Constitution"),
        ]:
            if p_kw in row_text.lower():
                party = p_label
                break
        incumbent = bool(re.search(r"incumbent", row_text, re.IGNORECASE))
        key = raw_name.lower()
        if key not in seen:
            seen.add(key)
            candidates.append({"name": raw_name, "party": party, "incumbent": incumbent})

    return candidates


async def lookup_election_page(race_id: str) -> Dict[str, Any]:
    """Fetch a Ballotpedia election page for a race and return a candidate roster.

    Tries the generated election URL first, then the stable district page for
    House races, then Ballotpedia search. Only returns found=True after fetching
    usable page HTML.
    """
    empty: Dict[str, Any] = {"found": False, "candidates": [], "page_url": None, "description": None}
    generated_url = _race_id_to_ballotpedia_url(race_id)
    district_url = _race_id_to_ballotpedia_district_url(race_id)
    search_query = quote_plus(_race_id_to_search_query(race_id))
    search_url = f"https://ballotpedia.org/wiki/index.php?search={search_query}&title=Special%3ASearch"
    urls = [url for url in (generated_url, district_url, search_url) if url]

    if not urls:
        logger.debug("Could not derive Ballotpedia URL for race_id %r", race_id)
        return empty

    try:
        import asyncio as _asyncio

        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:

            async def fetch_usable(page_url: str) -> tuple[Optional[str], Optional[str], Optional[int]]:
                resp = await client.get(page_url, headers={"User-Agent": _BROWSER_UA})

                if resp.status_code == 202:
                    logger.debug("Ballotpedia election page %s returned 202 — retrying after 2s", page_url)
                    await _asyncio.sleep(2)
                    resp = await client.get(page_url, headers={"User-Agent": _BROWSER_UA})

                if resp.status_code == 200 and not _is_unusable_ballotpedia_html(resp.text):
                    fetched_url = str(resp.url)
                    if "Special:Search" not in fetched_url and "title=Special%3ASearch" not in fetched_url:
                        return fetched_url, resp.text, resp.status_code

                logger.debug(
                    "Ballotpedia election page %s returned unusable status/html (%s) — trying proxy",
                    page_url,
                    resp.status_code,
                )
                proxy_resp = await client.get(
                    f"https://r.jina.ai/{page_url}",
                    headers={"User-Agent": _BROWSER_UA},
                    timeout=15,
                )
                if proxy_resp.status_code == 200 and not _is_unusable_ballotpedia_html(proxy_resp.text):
                    return page_url, proxy_resp.text, resp.status_code
                return None, None, resp.status_code

            last_status: Optional[int] = None
            last_url: Optional[str] = None
            bp_empty: Optional[Dict[str, Any]] = None
            for page_url in urls:
                fetched_url, html, status = await fetch_usable(page_url)
                last_url = page_url
                last_status = status
                if html is None or fetched_url is None:
                    continue

                candidates = _parse_candidate_list_from_html(html)
                desc = None
                m = re.search(r'<div[^>]+class="mw-parser-output"[^>]*>\s*<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
                if m:
                    desc = re.sub(r"<[^>]+>", " ", m.group(1))
                    desc = re.sub(r"\s+", " ", unescape(desc)).strip() or None

                logger.debug("Ballotpedia election page %s: found %d candidates", fetched_url, len(candidates))
                if candidates:
                    return {
                        "found": True,
                        "page_url": fetched_url,
                        "candidates": candidates,
                        "description": desc,
                        "http_status": status,
                    }
                # Page loaded but no roster parsed — remember it, then try Wikipedia.
                bp_empty = {
                    "found": True,
                    "page_url": fetched_url,
                    "candidates": [],
                    "description": desc,
                    "http_status": status,
                }
                break

            # Ballotpedia blocked or roster-less — fall back to the Wikipedia
            # election article, which is not IP-blocked from data-center IPs.
            wiki_url = _race_id_to_wikipedia_url(race_id)
            if wiki_url:
                try:
                    wiki_resp = await client.get(wiki_url, headers={"User-Agent": _BROWSER_UA})
                    if wiki_resp.status_code == 200:
                        wiki_candidates = _parse_wikipedia_candidate_list(wiki_resp.text)
                        if wiki_candidates:
                            logger.debug("Wikipedia election page %s: found %d candidates", wiki_url, len(wiki_candidates))
                            return {
                                "found": True,
                                "page_url": wiki_url,
                                "candidates": wiki_candidates,
                                "description": None,
                                "http_status": wiki_resp.status_code,
                                "source": "wikipedia",
                            }
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("Wikipedia election lookup failed for %r: %s", race_id, exc)

            if bp_empty is not None:
                return bp_empty
            return {**empty, "page_url": last_url, "http_status": last_status}

    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Ballotpedia election lookup failed for %r: %s", race_id, exc)
        return empty
