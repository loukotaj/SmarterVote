"""Image URL validation, accessibility checking, and candidate image resolution."""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

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
        direct = await _resolve_wikimedia_commons(current_url)
        if direct:
            candidate["image_url"] = direct
            log("info", f"  Resolved Commons URL for {name}: {direct[:80]}")
            return
        log("info", f"  Could not resolve Commons URL for {name} — searching for replacement")
        candidate["image_url"] = None
        current_url = None

    # Validate existing URL (extension / host check + live HEAD request)
    if current_url:
        if _is_valid_image_url(current_url):
            accessible, final_url = await _check_url_accessible(current_url)
            if accessible:
                # If redirect gave us a better URL, store that
                if final_url != current_url and _is_valid_image_url(final_url):
                    candidate["image_url"] = final_url
                log("info", f"  Image OK for {name}")
                return
            log("info", f"  Dead image URL for {name} — searching for replacement")
        else:
            log("info", f"  Invalid image URL for {name} (not a direct image file) — searching")
        candidate["image_url"] = None

    else:
        log("info", f"  No image URL for {name} — searching")

    # Ask the agent to find a working image URL
    from .prompts import IMAGE_SEARCH_SYSTEM, IMAGE_SEARCH_USER
    try:
        result = await agent_loop_fn(
            IMAGE_SEARCH_SYSTEM,
            IMAGE_SEARCH_USER.format(candidate_name=name),
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
            phase_name=f"image-{name[:20]}",
            max_tokens=512,
        )
        found_url = result.get("image_url")
        if not found_url:
            log("info", f"  No working image found for {name}")
            return

        # Agent returned a Commons page URL — resolve it
        if "commons.wikimedia.org/wiki/File:" in found_url:
            direct = await _resolve_wikimedia_commons(found_url)
            if direct:
                candidate["image_url"] = direct
                log("info", f"  Agent found + resolved Commons image for {name}: {direct[:80]}")
                return
            log("info", f"  Agent found Commons URL for {name} but resolution failed")
            return

        # Validate and check accessibility
        if _is_valid_image_url(found_url):
            accessible, final_url = await _check_url_accessible(found_url)
            if accessible:
                store_url = final_url if _is_valid_image_url(final_url) else found_url
                candidate["image_url"] = store_url
                log("info", f"  Agent found image for {name}: {store_url[:80]}")
                return

        log("info", f"  Agent returned unusable URL for {name}: {found_url[:80]}")

    except Exception as exc:
        log("warning", f"  Image resolution error for {name}: {exc}")


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
    await asyncio.gather(*[
        _resolve_single_image(
            c,
            agent_loop_fn=agent_loop_fn,
            model=model,
            on_log=on_log,
            race_id=race_id,
            max_iterations=max_iterations,
        )
        for c in candidates
    ])
