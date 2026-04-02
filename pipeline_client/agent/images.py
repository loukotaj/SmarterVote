"""Image URL validation, accessibility checking, and candidate image resolution."""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, quote

import httpx

from .ballotpedia import lookup_candidate_image as _ballotpedia_lookup
from .utils import make_logger

logger = logging.getLogger("pipeline")

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"})

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


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
        if any(host in netloc for host in (
            "cloudfront.net", "githubusercontent.com", "twimg.com", "fbcdn.net"
        )):
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


async def _lookup_wikipedia_image(candidate_name: str, context: str = "") -> Optional[str]:
    """Query the Wikipedia API to get a candidate's headshot URL.

    Uses opensearch to find the best matching page, then pageimages to get the
    image. Returns a direct upload.wikimedia.org URL, or None if not found.

    If ``context`` is provided (e.g. "Senator Arkansas Republican") it is
    appended to a second search pass so that a common name like "Mike Johnson"
    can be disambiguated when the bare-name search returns no thumbnail.
    """
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
                    headers={"User-Agent": _BROWSER_UA},
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
                titles = search_data[1] if len(search_data) > 1 else []
                for title in titles:
                    img_resp = await client.get(
                        "https://en.wikipedia.org/w/api.php",
                        params={
                            "action": "query",
                            "titles": title,
                            "prop": "pageimages",
                            "pithumbsize": "400",
                            "format": "json",
                            "redirects": "1",
                        },
                        headers={"User-Agent": _BROWSER_UA},
                    )
                    img_resp.raise_for_status()
                    data = img_resp.json()
                    for page in data.get("query", {}).get("pages", {}).values():
                        thumb = page.get("thumbnail", {}).get("source", "")
                        if thumb and "upload.wikimedia.org" in thumb:
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

    except Exception:
        pass
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
) -> None:
    """Validate and resolve image_url for a single candidate in-place."""
    log = make_logger(on_log)
    name = candidate.get("name", "unknown")
    current_url = candidate.get("image_url") or None  # Treat "" and None identically

    # Normalise empty string to None
    if not current_url:
        candidate["image_url"] = None

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
        if _is_valid_image_url(current_url):
            log("info", f"  [{name}] Checking URL accessibility: {current_url[:80]}")
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

    # Fast path 1: query Wikipedia API directly (no LLM call needed)
    log("info", f"  [{name}] Trying Wikipedia API lookup...")
    wiki_url = await _lookup_wikipedia_image(name, context=search_context)
    if wiki_url:
        log("info", f"  [{name}] Wikipedia API returned: {wiki_url[:80]}")
        accessible, final_url = await _check_url_accessible(wiki_url)
        if accessible:
            store_url = final_url if _is_valid_image_url(final_url) else wiki_url
            candidate["image_url"] = store_url
            log("info", f"  [{name}] Wikipedia image confirmed → {store_url[:80]}")
            return
        log("info", f"  [{name}] Wikipedia URL not accessible — trying Ballotpedia")
    else:
        log("info", f"  [{name}] Wikipedia API found no image — trying Ballotpedia")

    # Fast path 2: Ballotpedia API (covers virtually every US candidate)
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
        log("info", f"  [{name}] Ballotpedia URL not accessible — falling back to agent search")
    else:
        log("info", f"  [{name}] Ballotpedia API found no image — falling back to agent search")

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
) -> None:
    """Validate and resolve image URLs for all candidates, running in parallel."""
    candidates = [c for c in race_json.get("candidates", []) if isinstance(c, dict)]
    if not candidates:
        return
    office = race_json.get("office", "")
    jurisdiction = race_json.get("jurisdiction", "")
    await asyncio.gather(*[
        _resolve_single_image(
            c,
            agent_loop_fn=agent_loop_fn,
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
            office=office,
            jurisdiction=jurisdiction,
        )
        for c in candidates
    ])
