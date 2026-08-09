"""Image URL validation, accessibility checking, and candidate image resolution."""

import asyncio
import logging
import re
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx

from .ballotpedia import lookup_candidate_image as _ballotpedia_lookup
from .run_budget import RunBudget, RunBudgetExceeded
from .utils import make_logger
from .web_tools import _serper_image_search

logger = logging.getLogger("pipeline")

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"})

_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_WIKIMEDIA_API_UA = "SmarterVoteBot/1.0 (https://smarter.vote; contact: dev@smarter.vote)"

_NON_PHOTO_TOKENS = frozenset(
    {
        "avatar",
        "badge",
        "background",
        "banner",
        "collage",
        "favicon",
        "footerbg",
        "herobg",
        "homepage",
        "icon",
        "landscape",
        "logo",
        "mountain",
        "placeholder",
        "seal",
        "socialshare",
        "social-share",
        "sprite",
        "torch",
        "wordmark",
    }
)


class _PageImageParser(HTMLParser):
    """Collect image metadata from a candidate's known web page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: List[Tuple[str, str, int, int, str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta":
            property_name = (values.get("property") or values.get("name") or "").lower()
            if property_name in {"og:image", "og:image:url", "og:image:secure_url", "twitter:image"}:
                self.images.append((values.get("content", ""), property_name, 0, 0, ""))
            return
        if tag.lower() != "img":
            return

        source = values.get("data-image") or values.get("data-src") or values.get("src") or ""
        alt = values.get("alt") or values.get("title") or ""
        try:
            width = int(values.get("width", "0"))
            height = int(values.get("height", "0"))
        except ValueError:
            width = height = 0
        self.images.append((source, "img", width, height, alt))


def _name_tokens(candidate_name: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", candidate_name.lower()) if len(token) >= 3}


def _candidate_surname_token(candidate_name: str) -> Optional[str]:
    """Return the candidate's surname (last name token, by naming convention), or None."""
    tokens = [t for t in re.findall(r"[a-zA-Z0-9]+", candidate_name) if len(t) >= 3]
    return tokens[-1].lower() if tokens else None


_WIKIMEDIA_NON_CANDIDATE_QUALIFIERS = frozenset(
    {"actor", "actress", "band", "composer", "director", "footballer", "musician", "singer"}
)


def _is_untrusted_wikimedia_match(url: str, candidate_name: str) -> bool:
    """True if an upload.wikimedia.org filename does not match the full name.

    Guards against the same fuzzy-match risk as Wikipedia's opensearch API
    (e.g. "Sam Mead" resolving to "Sam Mendes"), but for a URL that was
    already persisted onto the candidate from an earlier run rather than a
    fresh search result — the existing-URL fast path below would otherwise
    just re-validate it's still *accessible* without checking it's still the
    right person.
    """
    if "upload.wikimedia.org" not in url:
        return False
    candidate_tokens = _name_tokens(candidate_name)
    if not candidate_tokens:
        return False
    url_tokens = _name_tokens(unquote(url))
    return not candidate_tokens.issubset(url_tokens) or bool(url_tokens & _WIKIMEDIA_NON_CANDIDATE_QUALIFIERS)


# Generic Open-Graph / social-share cards served by data and reference sites
# (e.g. https://www.fec.gov/static/img/social/fec-data.png) are never a
# candidate headshot even though they pass the extension check.
_GENERIC_CARD_MARKERS = (
    "/static/img/social",
    "/social/",
    "fec-data",
    "og-default",
    "default-og",
    "opengraph",
    "twitter-card",
    "sharecard",
    "share-card",
)


def _looks_like_non_photo(url: str, alt: str = "") -> bool:
    haystack = unquote(f"{url} {alt}").lower()
    if any(token in haystack for token in _NON_PHOTO_TOKENS):
        return True
    return any(marker in haystack for marker in _GENERIC_CARD_MARKERS)


def _looks_like_govtrack_reference_headshot(url: str) -> bool:
    """Return True for GovTrack's small legislator headshots worth upgrading."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    netloc = parsed.netloc.lower()
    path = unquote(parsed.path).lower()
    return netloc == "www.govtrack.us" and "/static/legislator-photos/" in path


def _extract_page_image_urls(html: str, page_url: str, candidate_name: str) -> List[str]:
    """Return candidate page images ordered from most to least likely portrait."""
    parser = _PageImageParser()
    parser.feed(html)
    name_tokens = _name_tokens(candidate_name)
    ranked: List[Tuple[int, int, str]] = []
    seen: set[str] = set()

    for index, (raw_url, source, width, height, alt) in enumerate(parser.images):
        if not raw_url:
            continue
        url = urljoin(page_url, raw_url)
        if url.startswith("http://"):
            url = f"https://{url[7:]}"
        if url in seen or not _is_valid_image_url(url) or _looks_like_non_photo(url, alt):
            continue
        seen.add(url)

        searchable = unquote(f"{url} {alt}").lower()
        score = (
            50 if source == "og:image" else 45 if source.startswith("og:image") else 35 if source == "twitter:image" else 20
        )
        score += 25 * len(name_tokens.intersection(re.findall(r"[a-z0-9]+", searchable)))
        if "photo" in searchable or "headshot" in searchable or "portrait" in searchable:
            score += 15
        if width >= 600 and height >= 600:
            score += 20
        elif width >= 300 and height >= 300:
            score += 10
        if source == "img" and width and height and width / max(height, 1) > 3:
            score -= 20
        ranked.append((score, -index, url))

    ranked.sort(reverse=True)
    return [url for _, _, url in ranked]


# Data / reference / finance sites never host a personal headshot on their
# pages — their Open-Graph image is a generic site card — so skip them when
# crawling candidate pages for a photo (Ballotpedia is handled via its own API).
_NON_HEADSHOT_HOSTS = (
    "fec.gov",
    "opensecrets.org",
    "followthemoney.org",
    "ballotpedia.org",
    "votesmart.org",
    "congress.gov",
    "govtrack.us",
)


def _candidate_page_urls(candidate: Dict[str, Any]) -> List[str]:
    """Return known candidate pages, preferring candidate-specific profile URLs."""
    name_tokens = _name_tokens(str(candidate.get("name", "")))
    pages: List[Tuple[int, str]] = []
    website = candidate.get("website")
    if isinstance(website, str) and website.startswith(("http://", "https://")):
        pages.append((20, website))

    for link in candidate.get("links", []):
        if not isinstance(link, dict):
            continue
        url = link.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if any(host in urlparse(url).netloc.lower() for host in _NON_HEADSHOT_HOSTS):
            continue
        parsed_path = unquote(urlparse(url).path).lower()
        score = 10
        if link.get("type") == "official":
            score += 20
        if "/candidate/" in parsed_path or name_tokens.intersection(re.findall(r"[a-z0-9]+", parsed_path)):
            score += 30
        pages.append((score, url))

    deduped: List[str] = []
    seen: set[str] = set()
    for _, url in sorted(pages, key=lambda item: item[0], reverse=True):
        normalized = url.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(url)
    return deduped[:8]


async def _lookup_known_page_image(candidate: Dict[str, Any]) -> Optional[str]:
    """Extract a direct image URL from known candidate website/profile pages."""
    headers = {"User-Agent": _BROWSER_UA}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            for page_url in _candidate_page_urls(candidate):
                try:
                    response = await client.get(page_url, headers=headers)
                    response.raise_for_status()
                except Exception:
                    continue
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type.lower():
                    continue
                for image_url in _extract_page_image_urls(response.text, str(response.url), candidate.get("name", "")):
                    accessible, final_url = await _check_url_accessible(image_url)
                    if accessible:
                        store_url = final_url if _is_valid_image_url(final_url) else image_url
                        if _looks_like_govtrack_reference_headshot(store_url):
                            continue
                        return store_url
    except Exception as exc:
        logger.debug("Candidate page image lookup failed: %s", exc)
    return None


def _is_valid_image_url(url: Any) -> bool:
    """Return True only if the URL looks like a direct image file, not a web page.

    Deliberately strict: only accepts URLs with known image extensions or from
    image-serving hosts. Rejects commons.wikimedia.org/wiki/File: page URLs even
    though they contain 'wikimedia.org' — only upload.wikimedia.org serves files.
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        netloc = parsed.netloc.lower()

        # File extension check (most reliable signal)
        if any(path.rstrip("/").endswith(ext) for ext in _IMAGE_EXTENSIONS):
            return True

        # upload.wikimedia.org always serves image files directly.
        # Do NOT accept commons.wikimedia.org (file pages) or en.wikipedia.org (articles).
        if netloc == "upload.wikimedia.org":
            return True

        # Ballotpedia stores images under /wiki/images/
        if "ballotpedia.org" in netloc and "/wiki/images/" in path:
            return True

        # Common image CDNs
        if any(host in netloc for host in ("cloudfront.net", "githubusercontent.com", "twimg.com", "fbcdn.net")):
            return True

    except Exception:
        return False
    return False


async def _check_url_accessible(url: str) -> Tuple[bool, str]:
    """Check whether a URL is accessible, returning (accessible, final_url).

    Follows redirects and returns the final URL, which may differ from the input
    — useful for resolving Wikimedia Special:FilePath redirects to upload URLs.

    Strategy:
    1. HEAD with browser UA — fast, most servers support it.
    2. If HEAD returns 405/501, fall back to byte-range GET.
    """
    headers = {"User-Agent": _BROWSER_UA}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.head(url, headers=headers)
            final_url = str(resp.url)
            if resp.status_code < 400:
                return True, final_url
            if resp.status_code in (405, 501):
                resp2 = await client.get(url, headers={**headers, "Range": "bytes=0-0"})
                return resp2.status_code in (200, 206), str(resp2.url)
            return False, url
    except Exception:
        return False, url


def _wikimedia_original_image_url(url: str) -> Optional[str]:
    """Return the original Wikimedia upload URL for thumbnail URLs."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.netloc.lower() != "upload.wikimedia.org":
        return None
    parts = parsed.path.split("/")
    try:
        thumb_index = parts.index("thumb")
    except ValueError:
        return None
    if thumb_index < 2 or len(parts) <= thumb_index + 3:
        return None
    original_parts = parts[:thumb_index] + parts[thumb_index + 1 : -1]
    if not original_parts or not original_parts[-1]:
        return None
    return parsed._replace(path="/".join(original_parts), query="", fragment="").geturl()


async def _best_accessible_image_url(url: str) -> Optional[str]:
    """Return the best accessible direct URL for an image candidate."""
    candidates: List[str] = []
    original = _wikimedia_original_image_url(url)
    if original:
        candidates.append(original)
    candidates.append(url)

    seen: set[str] = set()
    for candidate_url in candidates:
        if candidate_url in seen or not _is_valid_image_url(candidate_url):
            continue
        seen.add(candidate_url)
        accessible, final_url = await _check_url_accessible(candidate_url)
        if accessible:
            return final_url if _is_valid_image_url(final_url) else candidate_url
    return None


async def _lookup_wikipedia_image(candidate_name: str, context: str = "") -> Optional[str]:
    """Query the Wikipedia API to get a candidate's headshot URL.

    Uses opensearch to find the best matching page, then pageimages to get the
    image. Returns a direct upload.wikimedia.org URL, or None if not found.

    If ``context`` is provided (e.g. "Senator Arkansas Republican") it is
    appended to a second search pass so that a common name like "Mike Johnson"
    can be disambiguated when the bare-name search returns no thumbnail.
    """
    # opensearch is a fuzzy/autocomplete match, not an exact lookup — for a name
    # with no Wikipedia page (common for down-ballot candidates) it can return a
    # similarly-spelled but unrelated person (e.g. "Sam Mead" -> "Sam Mendes").
    # Require the candidate's full normalized name to appear in the matched
    # title before trusting its image. Surname-only matching accepted unrelated
    # entities such as "Dave Matthews Band" for candidate David Matthews.
    candidate_tokens = _name_tokens(candidate_name)

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:

            async def _search_and_fetch(query: str) -> Optional[str]:
                search_resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "opensearch",
                        "search": query,
                        "limit": "3",
                        "format": "json",
                    },
                    headers={"User-Agent": _WIKIMEDIA_API_UA},
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
                titles = search_data[1] if len(search_data) > 1 else []
                for title in titles:
                    if candidate_tokens and not candidate_tokens.issubset(_name_tokens(title)):
                        logger.debug(
                            "Rejected Wikipedia match %r for candidate %r — full name not present", title, candidate_name
                        )
                        continue
                    img_resp = await client.get(
                        "https://en.wikipedia.org/w/api.php",
                        params={
                            "action": "query",
                            "titles": title,
                            "prop": "pageimages",
                            "pithumbsize": "1000",
                            "format": "json",
                            "redirects": "1",
                        },
                        headers={"User-Agent": _WIKIMEDIA_API_UA},
                    )
                    img_resp.raise_for_status()
                    data = img_resp.json()
                    for page in data.get("query", {}).get("pages", {}).values():
                        thumb = page.get("thumbnail", {}).get("source", "")
                        resolved_title = str(page.get("title") or title)
                        if candidate_tokens and (
                            not candidate_tokens.issubset(_name_tokens(resolved_title))
                            or _name_tokens(resolved_title) & _WIKIMEDIA_NON_CANDIDATE_QUALIFIERS
                        ):
                            logger.debug(
                                "Rejected resolved Wikipedia title %r for candidate %r", resolved_title, candidate_name
                            )
                            continue
                        if (
                            thumb
                            and urlparse(thumb).netloc.casefold() == "upload.wikimedia.org"
                            and not _is_untrusted_wikimedia_match(thumb, candidate_name)
                        ):
                            return thumb
                return None

            # First pass: bare name search
            result = await _search_and_fetch(candidate_name)
            if result:
                return result

            # Second pass: name + context to disambiguate (e.g. common names)
            if context:
                result = await _search_and_fetch(f"{candidate_name} {context}")
                if result:
                    return result

    except Exception as e:
        logger.debug("Candidate image lookup failed: %s", e)
    return None


async def _lookup_ballotpedia_image(candidate_name: str) -> Optional[str]:
    """Return a Ballotpedia thumbnail URL for *candidate_name*, or None.

    Delegates to the shared :mod:`.ballotpedia` module so all Ballotpedia API
    logic lives in one place.
    """
    return await _ballotpedia_lookup(candidate_name)


async def _resolve_wikimedia_commons(url: str) -> Optional[str]:
    """Convert a commons.wikimedia.org/wiki/File: URL to a direct upload URL.

    Uses the Special:FilePath redirect endpoint which always resolves to the
    canonical upload.wikimedia.org URL. Returns the upload URL, or None on failure.
    """
    if "commons.wikimedia.org/wiki/File:" not in url:
        return None
    filename = url.split("/wiki/File:", 1)[1]
    special_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename}"
    accessible, final_url = await _check_url_accessible(special_url)
    if accessible and "upload.wikimedia.org" in final_url:
        return final_url
    return None


async def _lookup_serper_image(
    candidate_name: str, context: Optional[str] = None, run_budget: RunBudget | None = None
) -> Optional[str]:
    """Search for a candidate headshot via Serper Images, ranked by relevance.

    Runs a few query variants, scores each result by how strongly its title/source
    references the candidate (to avoid generic party graphics or the wrong person),
    prefers portrait-shaped images, then returns the best accessible one.
    """
    name_tokens = _name_tokens(candidate_name)
    queries: List[str] = []
    if context:
        queries.append(f"{candidate_name} {context} headshot")
    queries.append(f"{candidate_name} candidate portrait")
    queries.append(candidate_name)

    scored: List[Tuple[int, str]] = []
    seen: set[str] = set()
    try:
        for query in queries:
            results = await _serper_image_search(query, num_results=10, run_budget=run_budget)
            for r in results:
                if not isinstance(r, dict):
                    continue
                img_url = r.get("imageUrl")
                if not isinstance(img_url, str) or img_url in seen:
                    continue
                seen.add(img_url)
                meta = f"{r.get('title', '')} {r.get('source', '')} {r.get('link', '') or r.get('domain', '')}"
                if not _is_valid_image_url(img_url) or _looks_like_non_photo(img_url, meta):
                    continue
                meta_tokens = set(re.findall(r"[a-z0-9]+", meta.lower()))
                overlap = len(name_tokens & meta_tokens)
                score = overlap * 10
                try:
                    width = int(r.get("imageWidth") or 0)
                    height = int(r.get("imageHeight") or 0)
                except (TypeError, ValueError):
                    width = height = 0
                if width and height:
                    ratio = width / max(height, 1)
                    if 0.6 <= ratio <= 1.4:  # portrait/square headshot shape
                        score += 4
                    elif ratio > 2.5 or ratio < 0.35:  # banner / sliver
                        score -= 6
                    if width < 200 or height < 200:
                        score -= 4
                scored.append((score, img_url))
            # A result whose title/source names the candidate is a strong hit; stop early.
            if any(s >= 10 for s, _ in scored):
                break

        for _, img_url in sorted(scored, key=lambda item: item[0], reverse=True):
            accessible, final_url = await _check_url_accessible(img_url)
            if accessible:
                return final_url if _is_valid_image_url(final_url) else img_url
    except Exception as e:
        logger.debug("Serper image fast path failed: %s", e)
    return None


async def _resolve_single_image(
    candidate: Dict[str, Any],
    *,
    agent_loop_fn: Callable,
    model: str,
    on_log: Optional[Callable] = None,
    race_id: Optional[str] = None,
    max_iterations: int = 10,
    office: str = "",
    jurisdiction: str = "",
    run_budget: RunBudget | None = None,
) -> None:
    """Validate and resolve image_url for a single candidate in-place."""
    log = make_logger(on_log)
    name = candidate.get("name", "unknown")
    current_url = candidate.get("image_url") or None  # Treat "" and None identically
    low_resolution_fallback: Optional[str] = None

    # Normalise empty string to None
    if not current_url:
        candidate["image_url"] = None

    if current_url and _looks_like_govtrack_reference_headshot(current_url):
        low_resolution_fallback = current_url
        candidate["image_url"] = None
        current_url = None
        log("info", f"  [{name}] Existing image is a low-resolution reference photo - searching for better")

    if current_url and _is_untrusted_wikimedia_match(current_url, name):
        log(
            "info",
            f"  [{name}] Existing Wikimedia image's filename doesn't match this candidate's surname - discarding and re-searching",
        )
        candidate["image_url"] = None
        current_url = None

    # Commons file-page URL: resolve via Special:FilePath redirect
    if current_url and "commons.wikimedia.org/wiki/File:" in current_url:
        log("info", f"  [{name}] Commons page URL detected — resolving via Special:FilePath")
        direct = await _resolve_wikimedia_commons(current_url)
        if direct:
            candidate["image_url"] = direct
            log("info", f"  [{name}] Commons resolved → {direct[:80]}")
            return
        log("info", f"  [{name}] Commons resolution failed — will search for replacement")
        candidate["image_url"] = None
        current_url = None

    # Validate existing URL (extension / host check + live HEAD request)
    if current_url:
        if _is_valid_image_url(current_url) and not _looks_like_non_photo(current_url):
            log("info", f"  [{name}] Checking URL accessibility: {current_url[:80]}")
            best_url = await _best_accessible_image_url(current_url)
            if best_url:
                candidate["image_url"] = best_url
                if best_url != current_url:
                    log("info", f"  [{name}] URL upgraded to better form: {best_url[:80]}")
                else:
                    log("info", f"  [{name}] URL OK - keeping existing image")
                return
            accessible, final_url = await _check_url_accessible(current_url)
            if accessible:
                if final_url != current_url and _is_valid_image_url(final_url):
                    candidate["image_url"] = final_url
                    log("info", f"  [{name}] URL redirected to better form → {final_url[:80]}")
                else:
                    log("info", f"  [{name}] URL OK — keeping existing image")
                return
            log("info", f"  [{name}] URL is dead (HTTP error or timeout) — searching for replacement")
        else:
            log("info", f"  [{name}] URL failed validation (not a direct image file): {current_url[:80]}")
        candidate["image_url"] = None

    else:
        log("info", f"  [{name}] No image URL — starting search")

    # Build a context string from available race/candidate metadata to help
    # disambiguate common names (e.g. "Mike Johnson" → "Mike Johnson Senator Louisiana")
    context_parts = [p for p in (jurisdiction, office) if p]
    search_context = " ".join(context_parts)

    # Fast path 1: Ballotpedia API (politics-specific, no name-collision risk)
    log("info", f"  [{name}] Trying Ballotpedia API lookup...")
    bp_url = await _lookup_ballotpedia_image(name)
    if bp_url:
        log("info", f"  [{name}] Ballotpedia API returned: {bp_url[:80]}")
        accessible, final_url = await _check_url_accessible(bp_url)
        if accessible:
            store_url = final_url if _is_valid_image_url(final_url) else bp_url
            candidate["image_url"] = store_url
            log("info", f"  [{name}] Ballotpedia image confirmed → {store_url[:80]}")
            return
        log("info", f"  [{name}] Ballotpedia URL not accessible — trying Wikipedia")
    else:
        log("info", f"  [{name}] Ballotpedia API found no image — trying Wikipedia")

    # Fast path 2: query Wikipedia API directly (no LLM call needed)
    # Note: tried after Ballotpedia to avoid name-collision false positives
    # (e.g. "Jeff Wadlin" matching "Jeff Wadlow" the film director).
    log("info", f"  [{name}] Trying Wikipedia API lookup...")
    wiki_url = await _lookup_wikipedia_image(name, context=search_context)
    if wiki_url:
        log("info", f"  [{name}] Wikipedia API returned: {wiki_url[:80]}")
        best_url = await _best_accessible_image_url(wiki_url)
        if best_url:
            candidate["image_url"] = best_url
            log("info", f"  [{name}] Wikipedia image confirmed -> {best_url[:80]}")
            return
        accessible, final_url = await _check_url_accessible(wiki_url)
        if accessible:
            store_url = final_url if _is_valid_image_url(final_url) else wiki_url
            candidate["image_url"] = store_url
            log("info", f"  [{name}] Wikipedia image confirmed → {store_url[:80]}")
            return
        log("info", f"  [{name}] Wikipedia URL not accessible — falling back to agent search")
    else:
        log("info", f"  [{name}] Wikipedia API found no image — falling back to agent search")

    # Fast path 3: inspect candidate website/profile pages for image metadata.
    log("info", f"  [{name}] Inspecting known candidate pages for image metadata...")
    page_url = await _lookup_known_page_image(candidate)
    if page_url:
        candidate["image_url"] = page_url
        log("info", f"  [{name}] Candidate page image confirmed -> {page_url[:80]}")
        return
    log("info", f"  [{name}] Known pages yielded no usable image - trying Serper Image Search")

    # Fast path 4: query Serper Images API directly
    log("info", f"  [{name}] Trying Serper Images API lookup...")
    serper_img = await _lookup_serper_image(name, context=search_context, run_budget=run_budget)
    if serper_img:
        candidate["image_url"] = serper_img
        log("info", f"  [{name}] Serper image confirmed -> {serper_img[:80]}")
        return
    log("info", f"  [{name}] Serper Images found no accessible photo - falling back to agent search")

    if low_resolution_fallback:
        candidate["image_url"] = low_resolution_fallback
        log("info", f"  [{name}] Keeping low-resolution fallback -> {low_resolution_fallback[:80]}")
        return

    # Ask the agent to find a working image URL
    from .prompts import IMAGE_SEARCH_SYSTEM, IMAGE_SEARCH_USER

    log("info", f"  [{name}] Running agent image search...")
    try:
        result = await agent_loop_fn(
            IMAGE_SEARCH_SYSTEM,
            IMAGE_SEARCH_USER.format(candidate_name=name),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
            phase_name=f"image-{name[:20]}",
            max_tokens=2048,
            run_budget=run_budget,
        )
        found_url = result.get("image_url")
        if not found_url:
            log("info", f"  [{name}] Agent returned null — no image found")
            return

        log("info", f"  [{name}] Agent returned: {found_url[:80]}")

        # Agent returned a Commons page URL — resolve it
        if "commons.wikimedia.org/wiki/File:" in found_url:
            log("info", f"  [{name}] Agent URL is Commons page — resolving via Special:FilePath")
            direct = await _resolve_wikimedia_commons(found_url)
            if direct:
                candidate["image_url"] = direct
                log("info", f"  [{name}] Commons resolved → {direct[:80]}")
                return
            log("info", f"  [{name}] Agent Commons URL resolution failed — no image stored")
            return

        # Validate and check accessibility
        if _is_valid_image_url(found_url):
            accessible, final_url = await _check_url_accessible(found_url)
            if accessible:
                store_url = final_url if _is_valid_image_url(final_url) else found_url
                candidate["image_url"] = store_url
                log("info", f"  [{name}] Agent image confirmed → {store_url[:80]}")
                return
            log("info", f"  [{name}] Agent URL is not accessible — no image stored")
        else:
            log("info", f"  [{name}] Agent URL failed validation (not a direct image file) — no image stored")

    except RunBudgetExceeded:
        raise
    except Exception as exc:
        log("warning", f"  [{name}] Image resolution error: {exc}")


async def resolve_candidate_images(
    race_json: Dict[str, Any],
    *,
    agent_loop_fn: Callable,
    model: str,
    on_log: Optional[Callable] = None,
    race_id: Optional[str] = None,
    max_iterations: int = 10,
    on_progress: Optional[Callable[[int, str], None]] = None,
    run_budget: RunBudget | None = None,
) -> None:
    """Validate and resolve image URLs for all candidates, running in parallel.

    *on_progress* is an optional ``(pct: int, candidate_name: str) -> None`` callback
    invoked after each candidate's image is resolved, with cumulative completion
    percentage (0-100) and the candidate name.
    """
    candidates = [c for c in race_json.get("candidates", []) if isinstance(c, dict)]
    if not candidates:
        return
    office = race_json.get("office", "")
    jurisdiction = race_json.get("jurisdiction", "")
    total = len(candidates)
    done = 0

    async def _resolve_with_progress(c: Dict[str, Any]) -> None:
        nonlocal done
        resolve_call = _resolve_single_image(
            c,
            agent_loop_fn=agent_loop_fn,
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
            office=office,
            jurisdiction=jurisdiction,
            run_budget=run_budget,
        )
        if run_budget:
            timeout = run_budget.bounded_timeout(60.0, minimum_seconds=5.0, operation="candidate image resolution")
            await asyncio.wait_for(resolve_call, timeout=timeout)
        else:
            await resolve_call
        done += 1
        if on_progress:
            try:
                on_progress(int(done / total * 100), c.get("name", ""))
            except Exception as e:
                logger.debug("Image progress callback failed: %s", e)

    await asyncio.gather(*[_resolve_with_progress(c) for c in candidates])
