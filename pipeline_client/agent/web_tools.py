"""Web fetching, HTML stripping, and Serper search with caching.

All HTTP-level infrastructure for the research agent lives here.
"""

import asyncio
import ipaddress
import logging
import os
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Search cache
# ---------------------------------------------------------------------------


def _get_search_cache():
    """Return the shared SearchCache instance, or None if unavailable."""
    try:
        from pipeline_client.agent.search_cache import get_search_cache

        return get_search_cache()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------


def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace to get readable page text."""
    # Remove script/style blocks entirely
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Replace block-level tags with newlines so paragraphs stay readable
    text = re.sub(r"</(p|div|li|h[1-6]|tr|br)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    for entity, char in [
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&nbsp;", " "),
        ("&quot;", '"'),
        ("&#39;", "'"),
    ]:
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip ASCII control characters that are invalid in JSON strings
    # (keep \x09 tab, \x0a newline, \x0d carriage-return)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAGE_MAX_CHARS = 16000
_PAGE_MIN_USEFUL_CHARS = 300
_PAGE_PROXY_RETRY_CHARS = 900
_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# ---------------------------------------------------------------------------
# URL validation (SSRF protection)
# ---------------------------------------------------------------------------

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),  # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / GCP metadata
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
]


def _validate_url(url: str) -> None:
    """Raise ValueError if the URL targets a private/internal address or uses a disallowed scheme."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme: {parsed.scheme!r}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")
    try:
        # Resolve to IP and check against private ranges
        addr = ipaddress.ip_address(socket.gethostbyname(hostname))
        for network in _PRIVATE_NETWORKS:
            if addr in network:
                raise ValueError(f"URL resolves to private/internal address: {addr}")
    except socket.gaierror:
        # DNS failure — let the actual fetch fail naturally; don't block
        pass


async def _get_validated(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: Dict[str, str] | None = None,
    max_redirects: int = 5,
) -> httpx.Response:
    """GET a URL while validating each redirect target before following it."""
    current_url = url
    for _ in range(max_redirects + 1):
        _validate_url(current_url)
        resp = await client.get(current_url, headers=headers)
        if not getattr(resp, "is_redirect", False):
            return resp
        location = resp.headers.get("location")
        if not location:
            return resp
        current_url = urljoin(str(resp.url), location)
    raise ValueError(f"Too many redirects while fetching {url}")


_UNUSABLE_PAGE_MARKERS = [
    "enable javascript",
    "please enable javascript",
    "turn javascript on",
    "access denied",
    "forbidden",
    "attention required",
    "verify you are human",
    "captcha",
    "cloudflare",
    "security check",
    "temporarily unavailable",
    "the request could not be satisfied",
    "request blocked",
    "error 403",
    "403 error",
    "generated by cloudfront",
    "you don't have permission to access",
    "our systems have detected unusual traffic",
]

_POLICY_PATH_TOKENS = [
    "issue",
    "issues",
    "policy",
    "policies",
    "platform",
    "priorit",
    "learn",
    "blog",
    "about",
]

_NON_POLICY_PATH_TOKENS = [
    "donate",
    "volunteer",
    "events",
    "join",
    "orientation",
    "testing",
    "sitemap",
]

_POLICY_TEXT_TOKENS = [
    "issues",
    "healthcare",
    "econom",
    "tax",
    "immigration",
    "border",
    "guns",
    "education",
    "abortion",
    "reproductive",
    "climate",
    "energy",
    "foreign",
    "defense",
    "election",
    "voting",
    "social justice",
    "technology",
    "liberty",
    "freedom",
    "democracy",
    "rights",
    "responsibility",
    "constitution",
    "federal",
    "inflation",
    "debt",
    "artificial intelligence",
]

_LOW_SIGNAL_PAGE_MARKERS = [
    "lorem ipsum",
    "created with nationbuilder",
    "please check your email for a link to activate",
]

_BOILERPLATE_SEGMENT_MARKERS = [
    "paid for by",
    "all rights reserved",
    "created with nationbuilder",
    "join my campaign",
    "contributions are not tax deductible",
    "dolor sit amet",
    "consectetur adipiscing",
    "eiusmod tempor incididunt",
    "ut enim ad minim veniam",
    "duis aute irure",
    "excepteur sint occaecat",
    "mollit anim id est laborum",
]

_POLICY_URL_PATH_TOKENS = [
    "/issue",
    "/policy",
    "/polic",
    "/platform",
    "/priorit",
    "/position",
    "/stance",
    "/agenda",
    "/on-the-issues",
    "/where-i-stand",
    "/values",
    "/beliefs",
    "/stands",
]

# ---------------------------------------------------------------------------
# Per-event-loop HTTP client singletons
# ---------------------------------------------------------------------------

_fetch_clients_by_loop: Dict[int, httpx.AsyncClient] = {}
_serper_clients_by_loop: Dict[int, httpx.AsyncClient] = {}


def _get_fetch_client() -> httpx.AsyncClient:
    """Return a per-event-loop AsyncClient for page fetches."""
    loop_id = id(asyncio.get_running_loop())
    # Prune entries for closed clients / defunct event loops
    for k in [k for k, v in _fetch_clients_by_loop.items() if v.is_closed]:
        del _fetch_clients_by_loop[k]
    client = _fetch_clients_by_loop.get(loop_id)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=20,
            follow_redirects=False,
            headers={"User-Agent": _BROWSER_UA},
        )
        _fetch_clients_by_loop[loop_id] = client
    return client


def _get_serper_client() -> httpx.AsyncClient:
    """Return a per-event-loop AsyncClient for Serper API calls."""
    loop_id = id(asyncio.get_running_loop())
    # Prune entries for closed clients / defunct event loops
    for k in [k for k, v in _serper_clients_by_loop.items() if v.is_closed]:
        del _serper_clients_by_loop[k]
    client = _serper_clients_by_loop.get(loop_id)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=15)
        _serper_clients_by_loop[loop_id] = client
    return client


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------


async def _fetch_page(url: str) -> str:
    """Fetch a URL and return stripped text content, with caching and fallback."""
    try:
        _validate_url(url)
    except ValueError as exc:
        logger.warning("Blocked fetch of disallowed URL %s: %s", url, exc)
        return f"[Blocked: {exc}]"

    cache = _get_search_cache()
    if cache:
        cached = cache.get_page(url)
        if cached:
            logger.debug(f"Page cache HIT: {url[:60]}")
            return cached

    client = _get_fetch_client()
    failure_reasons: List[str] = []

    # Some campaign sites block one header/profile but allow another.
    header_profiles = [
        {},
        {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    ]

    for headers in header_profiles:
        try:
            resp = await _get_validated(client, url, headers=headers or None)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type or "text" in content_type:
                text = _strip_html(resp.text)
            else:
                text = f"[Non-text content: {content_type}]"

            if _is_unusable_page_text(text):
                failure_reasons.append("primary_fetch_unusable_content")
                continue

            # Some anti-bot pages return HTTP 200 with short generic text. For very
            # short pages, opportunistically try the proxy and prefer richer content.
            if len(text.strip()) < _PAGE_PROXY_RETRY_CHARS:
                try:
                    proxy_url = f"https://r.jina.ai/{url}"
                    proxy_resp = await _get_validated(client, proxy_url)
                    proxy_resp.raise_for_status()
                    proxy_text = proxy_resp.text.strip()
                    if (not _is_unusable_page_text(proxy_text)) and (len(proxy_text) > len(text) + 200):
                        if len(proxy_text) > _PAGE_MAX_CHARS:
                            proxy_text = proxy_text[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"
                        if cache:
                            cache.set_page(url, proxy_text)
                        return proxy_text
                except Exception as exc:
                    failure_reasons.append(f"short-page proxy probe: {exc}")

            if len(text) > _PAGE_MAX_CHARS:
                text = text[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"

            if cache:
                cache.set_page(url, text)
            return text
        except Exception as exc:
            failure_reasons.append(str(exc))

    # Fallback: jina text proxy often succeeds when direct fetches hit bot checks.
    proxy_url = f"https://r.jina.ai/{url}"
    try:
        proxy_resp = await _get_validated(client, proxy_url)
        proxy_resp.raise_for_status()
        proxy_text = proxy_resp.text.strip()
        if not _is_unusable_page_text(proxy_text):
            if len(proxy_text) > _PAGE_MAX_CHARS:
                proxy_text = proxy_text[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"
            if cache:
                cache.set_page(url, proxy_text)
            return proxy_text
        failure_reasons.append("proxy_unusable_content")
    except Exception as exc:
        failure_reasons.append(f"proxy: {exc}")

    # Campaign issue pages are often blocked while other site pages remain accessible.
    # If the requested URL looks like policy/issues content, attempt sitemap-driven recovery.
    fallback_text = await _try_sitemap_policy_fallback(url, client, failure_reasons)
    if fallback_text:
        if cache:
            cache.set_page(url, fallback_text)
        return fallback_text

    return f"[Failed to fetch {url}: {' | '.join(failure_reasons[:3])}]"


# ---------------------------------------------------------------------------
# Sitemap / policy page helpers
# ---------------------------------------------------------------------------


def _extract_sitemap_urls(xml_text: str, site_host: str) -> List[str]:
    urls = re.findall(r"<loc>(.*?)</loc>", xml_text or "", flags=re.IGNORECASE)
    out: List[str] = []
    for raw in urls:
        u = (raw or "").strip()
        if not u:
            continue
        parsed = urlparse(u)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower() != site_host.lower():
            continue
        if u not in out:
            out.append(u)
    return out


def _extract_policy_segments(text: str) -> List[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    segments = re.split(r"\n+|(?<=[.!?])\s+", cleaned)
    selected: List[str] = []
    seen: set[str] = set()

    for segment in segments:
        s = re.sub(r"\s+", " ", segment).strip()
        if len(s) < 30:
            continue
        low = s.lower()
        if any(token in low for token in _LOW_SIGNAL_PAGE_MARKERS):
            continue
        if any(marker in low for marker in _BOILERPLATE_SEGMENT_MARKERS):
            continue
        if s.count(",") > 20:
            continue
        if not any(token in low for token in _POLICY_TEXT_TOKENS):
            continue
        key = low[:180]
        if key in seen:
            continue
        seen.add(key)
        selected.append(s)
        if len(selected) >= 16:
            break

    if selected:
        return selected

    # Fallback to general substantive prose for campaign pages with sparse issue keywords.
    for segment in segments:
        s = re.sub(r"\s+", " ", segment).strip()
        if len(s) < 60:
            continue
        low = s.lower()
        if any(marker in low for marker in _LOW_SIGNAL_PAGE_MARKERS):
            continue
        if any(marker in low for marker in _BOILERPLATE_SEGMENT_MARKERS):
            continue
        if s.count(",") > 20:
            continue
        if "skip to main content" in low:
            continue
        if low.startswith("login") or low.startswith("volunteer"):
            continue
        key = low[:180]
        if key in seen:
            continue
        seen.add(key)
        selected.append(s)
        if len(selected) >= 8:
            break

    if selected:
        return selected

    compact = re.sub(r"\s+", " ", cleaned)
    compact = re.sub(
        r"\b(skip to main content|volunteer|events|donate|login|home|learn more|created with nationbuilder|please check your email for a link to activate|lorem ipsum)\b",
        " ",
        compact,
        flags=re.IGNORECASE,
    )
    compact = re.sub(r"\s+", " ", compact).strip()
    compact_low = compact.lower()
    if len(compact) >= 120 and not any(marker in compact_low for marker in _BOILERPLATE_SEGMENT_MARKERS):
        selected.append(compact[:1200])

    return selected


async def _try_sitemap_policy_fallback(url: str, client: httpx.AsyncClient, failure_reasons: List[str]) -> Optional[str]:
    if not _is_likely_policy_url(url):
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    sitemap_urls = [
        urljoin(base, "/sitemap.xml"),
        urljoin(base, "/sitemap_index.xml"),
    ]

    discovered_pages: List[str] = []
    homepage_url = urljoin(base, "/")
    discovered_pages.append(homepage_url)
    for sitemap_url in sitemap_urls:
        try:
            resp = await _get_validated(client, sitemap_url, headers=headers)
            resp.raise_for_status()
            discovered = _extract_sitemap_urls(resp.text, parsed.netloc)
            for page_url in discovered:
                if page_url not in discovered_pages:
                    discovered_pages.append(page_url)
        except Exception as exc:
            failure_reasons.append(f"sitemap({sitemap_url}): {exc}")

    if not discovered_pages:
        return None

    def _priority(page_url: str) -> tuple[int, int]:
        lowered = page_url.lower()
        if any(token in lowered for token in _NON_POLICY_PATH_TOKENS):
            return (1000, len(page_url))
        token_score = sum(1 for token in _POLICY_PATH_TOKENS if token in lowered)
        return (-token_score, len(page_url))

    ranked_candidates = sorted(discovered_pages, key=_priority)
    candidates = [u for u in ranked_candidates if _priority(u)[0] < 1000][:8]
    if not candidates:
        candidates = [homepage_url]
    recovered_segments: List[str] = []
    source_urls: List[str] = []

    for candidate_url in candidates:
        try:
            resp = await _get_validated(client, candidate_url, headers=headers)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type or "text" in content_type:
                text = _strip_html(resp.text)
            else:
                text = resp.text or ""

            if _is_unusable_page_text(text):
                continue

            segments = _extract_policy_segments(text)
            if not segments:
                continue

            recovered_segments.extend(segments)
            source_urls.append(candidate_url)
            if len(recovered_segments) >= 12:
                break
        except Exception as exc:
            failure_reasons.append(f"policy-page({candidate_url}): {exc}")

    if not recovered_segments:
        return None

    unique_sources = source_urls[:4]
    header = "Recovered issue-related content from campaign sitemap pages after direct/proxy issue URL fetch failed."
    source_block = "\n".join(f"- {u}" for u in unique_sources)
    content_block = "\n".join(f"- {s}" for s in recovered_segments[:12])
    combined = f"{header}\nSources:\n{source_block}\n\nExtracted points:\n{content_block}"

    if len(combined) > _PAGE_MAX_CHARS:
        combined = combined[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"
    return combined


# ---------------------------------------------------------------------------
# Page content helpers
# ---------------------------------------------------------------------------


def _is_unusable_page_text(text: str) -> bool:
    """Return True for empty/blocked/placeholder pages that lack usable substance."""
    if not text or not text.strip():
        return True

    lowered = text.lower()
    if any(marker in lowered for marker in _UNUSABLE_PAGE_MARKERS):
        return True

    if len(text.strip()) < _PAGE_MIN_USEFUL_CHARS and "[failed to fetch" not in lowered:
        return True

    return False


def _is_likely_policy_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(token in lowered for token in _POLICY_URL_PATH_TOKENS)


def _page_fetch_log_hint(url: str, page_text: str) -> Optional[str]:
    """Return a concise warning hint for suspicious fetch results, else None."""
    text = (page_text or "").strip()
    lowered = text.lower()

    if lowered.startswith("[failed to fetch"):
        return f"fetch failed for {url[:80]} — {text[:220]}"

    matched_markers = [marker for marker in _UNUSABLE_PAGE_MARKERS if marker in lowered]
    if matched_markers:
        marker = matched_markers[0]
        return f"content appears blocked/unusable for {url[:80]} (marker='{marker}', chars={len(text)})"

    if _is_likely_policy_url(url) and 0 < len(text) < _PAGE_PROXY_RETRY_CHARS:
        preview = " ".join(text.split())[:180]
        return f"short policy-page content for {url[:80]} ({len(text)} chars). preview='{preview}'"

    return None


# ---------------------------------------------------------------------------
# Serper web search (with caching)
# ---------------------------------------------------------------------------


async def _serper_search(query: str, *, num_results: int = 8, race_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Execute a web search via the Serper API, with caching."""
    if not query or not query.strip():
        logger.warning("_serper_search called with empty query — skipping")
        return []

    cache = _get_search_cache()
    if cache:
        cached = cache.get(query, race_id)
        if cached:
            logger.debug(f"Search cache HIT: {query[:60]}")
            return cached["results"]

    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return [{"error": "SERPER_API_KEY not configured"}]

    client = _get_serper_client()
    resp = await client.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": num_results},
    )
    resp.raise_for_status()
    data = resp.json()

    results: List[Dict[str, Any]] = []
    for item in data.get("organic", []):
        results.append(
            {
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "url": item.get("link", ""),
            }
        )

    kg = data.get("knowledgeGraph")
    if kg:
        results.insert(
            0,
            {
                "title": kg.get("title", ""),
                "snippet": kg.get("description", ""),
                "url": kg.get("website", kg.get("descriptionLink", "")),
                "type": "knowledge_graph",
            },
        )

    if cache:
        cache.set(query, results, race_id=race_id, provider="serper")

    return results
