"""Web fetching, HTML stripping, and Serper search with caching.

All HTTP-level infrastructure for the research agent lives here.
"""

import asyncio
import ipaddress
import logging
import os
import random
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from .cost import (
    mark_search_provider_exhausted,
    record_fetched_chars,
    reserve_page_fetch,
    reserve_search_call,
    search_provider_exhausted,
)
from .run_budget import RunBudget

logger = logging.getLogger("pipeline")
_SERPER_MAX_QUERY_CHARS = 500

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


TEXT_PROXY_BASE = "https://r.jina.ai/"

# Anonymous r.jina.ai is aggressively rate limited and answers 403/429 once the
# shared quota is spent — which looks identical to "the site blocked us" at every
# call site. Configure JINA_API_KEY to get the authenticated quota.
_proxy_attempts = 0
_proxy_failures = 0
_proxy_outage_logged = False


def text_proxy_url(url: str) -> str:
    return f"{TEXT_PROXY_BASE}{url}"


def text_proxy_headers() -> Dict[str, str]:
    headers = {"User-Agent": _BROWSER_UA}
    api_key = os.environ.get("JINA_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def record_proxy_result(*, ok: bool) -> None:
    """Track proxy health so a systemic outage is visible instead of silent.

    Every roster/evidence path degrades to unsourced guesses when the proxy is
    down, so a run that never lands a single proxy fetch should say so loudly
    rather than emit one indistinguishable per-URL failure at a time.
    """
    global _proxy_attempts, _proxy_failures, _proxy_outage_logged
    _proxy_attempts += 1
    if not ok:
        _proxy_failures += 1
    if (
        not _proxy_outage_logged
        and _proxy_attempts >= 5
        and _proxy_failures == _proxy_attempts
        and not os.environ.get("JINA_API_KEY", "").strip()
    ):
        _proxy_outage_logged = True
        logger.warning(
            "Text proxy (%s) has failed all %d attempts this run. Anonymous quota is likely exhausted; "
            "set JINA_API_KEY so page fetches can reach retrievable (tier 1/2) evidence instead of "
            "falling back to search snippets.",
            TEXT_PROXY_BASE,
            _proxy_attempts,
        )


def proxy_health_snapshot() -> Dict[str, int]:
    return {"attempts": _proxy_attempts, "failures": _proxy_failures}


_TABULAR_EXTENSIONS = (".xlsx", ".xlsm", ".csv", ".tsv")


def is_tabular_document(url: str) -> bool:
    """True for spreadsheet/CSV URLs the text proxy cannot render.

    Several states publish their certified candidate list as a spreadsheet.
    r.jina.ai answers 422 for those even though the file downloads fine, so the
    authoritative roster source was simply unreadable and roster finalization
    deadlocked with no way forward.
    """
    path = urlparse(url or "").path.lower()
    return path.endswith(_TABULAR_EXTENSIONS)


def _xlsx_to_text(payload: bytes) -> str:
    """Extract readable rows from an .xlsx without a spreadsheet dependency.

    An .xlsx is a zip of XML. Shared strings plus the first worksheet is enough
    to make a candidate filing list legible to the agent, and avoids adding a
    parser to the worker image for one file format.
    """
    import io as _io
    import zipfile
    from xml.etree import ElementTree

    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(_io.BytesIO(payload)) as archive:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{ns}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{ns}t")))
        sheets = [name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")]
        if not sheets:
            return ""
        root = ElementTree.fromstring(archive.read(sorted(sheets)[0]))
        lines: List[str] = []
        for row in root.iter(f"{ns}row"):
            cells: List[str] = []
            for cell in row.findall(f"{ns}c"):
                value = cell.find(f"{ns}v")
                if value is None or value.text is None:
                    continue
                if cell.get("t") == "s":
                    index = int(value.text)
                    cells.append(shared[index] if 0 <= index < len(shared) else "")
                else:
                    cells.append(value.text)
            if any(cell.strip() for cell in cells):
                lines.append(" | ".join(cells))
        return "\n".join(lines)


async def _fetch_tabular_document(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Download and flatten a spreadsheet/CSV directly, bypassing the text proxy."""
    resp = await _get_validated(client, url)
    resp.raise_for_status()
    path = urlparse(url).path.lower()
    if path.endswith((".xlsx", ".xlsm")):
        return _xlsx_to_text(resp.content)
    # CSV/TSV are already text; httpx decodes using the response charset.
    return resp.text


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
    if not reserve_page_fetch():
        return "[Page fetch budget reached; use the evidence already collected.]"

    client = _get_fetch_client()
    failure_reasons: List[str] = []

    # Spreadsheets download fine but the text proxy rejects them, so fetch and
    # flatten them here rather than letting an authoritative candidate list come
    # back as an unusable error.
    if is_tabular_document(url):
        try:
            tabular_text = await _fetch_tabular_document(client, url)
            if tabular_text and tabular_text.strip():
                if len(tabular_text) > _PAGE_MAX_CHARS:
                    tabular_text = tabular_text[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"
                record_fetched_chars(len(tabular_text))
                if cache:
                    cache.set_page(url, tabular_text)
                return tabular_text
            failure_reasons.append("tabular document contained no readable rows")
        except Exception as exc:
            failure_reasons.append(f"tabular fetch: {exc}")

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
            record_fetched_chars(len(text))

            # Some anti-bot pages return HTTP 200 with short generic text. For very
            # short pages, opportunistically try the proxy and prefer richer content.
            if len(text.strip()) < _PAGE_PROXY_RETRY_CHARS:
                try:
                    proxy_url = text_proxy_url(url)
                    proxy_resp = await _get_validated(client, proxy_url, headers=text_proxy_headers())
                    proxy_resp.raise_for_status()
                    proxy_text = proxy_resp.text.strip()
                    record_proxy_result(ok=not _is_unusable_page_text(proxy_text))
                    if (not _is_unusable_page_text(proxy_text)) and (len(proxy_text) > len(text) + 200):
                        if len(proxy_text) > _PAGE_MAX_CHARS:
                            proxy_text = proxy_text[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"
                        record_fetched_chars(max(0, len(proxy_text) - len(text)))
                        if cache:
                            cache.set_page(url, proxy_text)
                        return proxy_text
                except Exception as exc:
                    record_proxy_result(ok=False)
                    failure_reasons.append(f"short-page proxy probe: {exc}")

            if len(text) > _PAGE_MAX_CHARS:
                text = text[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"

            if cache:
                cache.set_page(url, text)
            return text
        except Exception as exc:
            failure_reasons.append(str(exc))

    # Fallback: jina text proxy often succeeds when direct fetches hit bot checks.
    proxy_url = text_proxy_url(url)
    try:
        proxy_resp = await _get_validated(client, proxy_url, headers=text_proxy_headers())
        proxy_resp.raise_for_status()
        proxy_text = proxy_resp.text.strip()
        record_proxy_result(ok=not _is_unusable_page_text(proxy_text))
        if not _is_unusable_page_text(proxy_text):
            if len(proxy_text) > _PAGE_MAX_CHARS:
                proxy_text = proxy_text[:_PAGE_MAX_CHARS] + f"\n\n[...truncated at {_PAGE_MAX_CHARS} chars]"
            if cache:
                cache.set_page(url, proxy_text)
            record_fetched_chars(len(proxy_text))
            return proxy_text
        failure_reasons.append("proxy_unusable_content")
    except Exception as exc:
        record_proxy_result(ok=False)
        failure_reasons.append(f"proxy: {exc}")

    # Campaign issue pages are often blocked while other site pages remain accessible.
    # If the requested URL looks like policy/issues content, attempt sitemap-driven recovery.
    fallback_text = await _try_sitemap_policy_fallback(url, client, failure_reasons)
    if fallback_text:
        if cache:
            cache.set_page(url, fallback_text)
        record_fetched_chars(len(fallback_text))
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

    # If sitemap parsing yielded no links, crawl the homepage directly for links
    if len(discovered_pages) == 1:
        try:
            resp = await _get_validated(client, homepage_url, headers=headers)
            resp.raise_for_status()
            homepage_links = _extract_links_from_html(resp.text, homepage_url)
            for page_url in homepage_links:
                if page_url not in discovered_pages:
                    discovered_pages.append(page_url)
            failure_reasons.append(f"sitemap empty/failed; crawled homepage and found {len(homepage_links)} links")
        except Exception as exc:
            failure_reasons.append(f"homepage-crawl fallback: {exc}")

    if not discovered_pages:
        return None

    def _priority(page_url: str) -> tuple[int, int]:
        parsed_url = urlparse(page_url)
        path = parsed_url.path.lower()
        if any(token in path for token in _NON_POLICY_PATH_TOKENS):
            return (1000, len(page_url))
        token_score = sum(1 for token in _POLICY_PATH_TOKENS if token in path)
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


class SearchProviderUnavailable(RuntimeError):
    """Raised for non-retryable search credential or quota failures.

    Letting this escape the agent loop stops the run instead of silently
    substituting uncited model knowledge for web research.
    """


class SerperQuotaExhausted(SearchProviderUnavailable):
    """Raised when Serper explicitly reports that its credits are exhausted."""


def _raise_for_fatal_serper_error(status: int, response_text: str) -> None:
    normalized = response_text.lower()
    quota_error = status in {400, 402} and any(
        marker in normalized for marker in ("not enough credits", "insufficient credits", "quota")
    )
    if quota_error:
        raise SerperQuotaExhausted(f"Serper quota exhausted (HTTP {status})")
    if status in {401, 403}:
        raise SearchProviderUnavailable(f"Serper authentication rejected (HTTP {status}); stopping research run")


async def _searlo_search(
    query: str,
    *,
    num_results: int,
    race_id: Optional[str],
    run_budget: RunBudget | None,
    images: bool = False,
) -> List[Dict[str, Any]]:
    """Use Searlo after Serper explicitly reports exhausted credits."""
    api_key = os.environ.get("SEARLO_API_KEY", "")
    if not api_key:
        raise SearchProviderUnavailable("Serper quota exhausted and SEARLO_API_KEY is not configured; stopping research run")

    operation = "Searlo image search" if images else "Searlo search"
    if run_budget:
        run_budget.require_call_time(2.0, operation=operation)
    if not reserve_search_call("searlo"):
        return [{"error": "Run search budget reached; finish from cached evidence."}]

    timeout = run_budget.bounded_timeout(10.0, minimum_seconds=2.0, operation=operation) if run_budget else 10.0
    endpoint = "images" if images else "web"
    try:
        resp = await _get_serper_client().get(
            f"https://api.searlo.tech/api/v1/search/{endpoint}",
            headers={"x-api-key": api_key},
            params={"q": query, "limit": min(max(num_results, 1), 10), "gl": "us", "hl": "en"},
            timeout=timeout,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        raise SearchProviderUnavailable(f"Searlo search unavailable (HTTP {status or 'unknown'})") from exc
    except httpx.HTTPError as exc:
        raise SearchProviderUnavailable(f"Searlo search unavailable: {exc}") from exc

    data = resp.json()
    # Searlo currently serves the Google-style response shape (``organic`` /
    # ``images``), while its API reference documents the newer ``items``
    # envelope. Accept both so a provider-side rollout cannot silently turn a
    # successful fallback request into zero evidence.
    result_key = "images" if images else "organic"
    items = data.get(result_key)
    if items is None:
        items = data.get("items", [])
    if not isinstance(items, list):
        raise SearchProviderUnavailable(f"{operation} returned an invalid result payload")
    if images:
        results = []
        for item in items:
            image = item.get("image") if isinstance(item.get("image"), dict) else {}
            results.append(
                {
                    "title": item.get("title", ""),
                    "imageUrl": item.get("imageUrl") or image.get("src") or item.get("link", ""),
                    "url": image.get("contextLink") or item.get("sourceUrl") or item.get("link", ""),
                }
            )
    else:
        results = [
            {"title": item.get("title", ""), "snippet": item.get("snippet", ""), "url": item.get("link", "")} for item in items
        ]

    cache = _get_search_cache()
    if cache:
        cache.set(query, results, race_id=race_id, provider="searlo-images" if images else "searlo")
    logger.warning("Serper credits exhausted; completed %s with Searlo fallback", operation.lower())
    return results


async def _serper_search(
    query: str,
    *,
    num_results: int = 8,
    race_id: Optional[str] = None,
    run_budget: RunBudget | None = None,
    max_attempts: int = 2,
) -> List[Dict[str, Any]]:
    """Execute a web search via the Serper API, with caching."""
    normalized_query = re.sub(r"\s+", " ", query or "").strip()
    if not normalized_query:
        logger.warning("_serper_search called with empty query — skipping")
        return []
    if len(normalized_query) > _SERPER_MAX_QUERY_CHARS:
        logger.warning(
            "Truncating oversized Serper query from %s to %s chars: %s",
            len(normalized_query),
            _SERPER_MAX_QUERY_CHARS,
            normalized_query[:120],
        )
        normalized_query = (
            normalized_query[:_SERPER_MAX_QUERY_CHARS].rsplit(" ", 1)[0] or normalized_query[:_SERPER_MAX_QUERY_CHARS]
        )

    cache = _get_search_cache()
    if cache:
        cached = cache.get(normalized_query, race_id)
        if cached:
            logger.debug(f"Search cache HIT: {normalized_query[:60]}")
            return cached["results"]

    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return [{"error": "SERPER_API_KEY not configured"}]

    # Serper already reported exhausted credits this run, so every further call
    # would 400. Skipping it matters for more than latency: the doomed attempt
    # reserved a search slot from the same ceiling the Searlo fallback then
    # reserved again, so each logical search burned two of the run's budget and
    # halved its effective research depth.
    if search_provider_exhausted("serper"):
        return await _searlo_search(
            normalized_query,
            num_results=num_results,
            race_id=race_id,
            run_budget=run_budget,
        )

    client = _get_serper_client()
    last_error = ""
    for attempt in range(max(1, max_attempts)):
        if run_budget:
            run_budget.require_call_time(2.0, operation="Serper search")
        if not reserve_search_call("serper"):
            return [{"error": "Run search budget reached; finish from cached evidence."}]

        request_timeout = (
            run_budget.bounded_timeout(10.0, minimum_seconds=2.0, operation="Serper search") if run_budget else 10.0
        )
        try:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": normalized_query, "num": num_results},
                timeout=request_timeout,
            )
            resp.raise_for_status()
            break
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            response_text = exc.response.text[:300] if exc.response is not None else ""
            last_error = f"HTTP {status or 'unknown'}"
            logger.warning(
                "Serper search failed with HTTP %s for query %r: %s",
                status or "unknown",
                normalized_query[:160],
                response_text,
            )
            try:
                _raise_for_fatal_serper_error(status, response_text)
            except SerperQuotaExhausted:
                mark_search_provider_exhausted("serper")
                return await _searlo_search(
                    normalized_query,
                    num_results=num_results,
                    race_id=race_id,
                    run_budget=run_budget,
                )
            if status not in {429, 500, 502, 503, 504} or attempt >= max_attempts - 1:
                return [{"error": f"Serper search failed: {last_error}"}]
        except httpx.HTTPError as exc:
            last_error = str(exc)
            logger.warning("Serper search request failed for query %r: %s", normalized_query[:160], exc)
            if attempt >= max_attempts - 1:
                return [{"error": f"Serper search failed: {exc}"}]

        wait = min(15.0, (2**attempt) * random.uniform(0.8, 1.2))
        if run_budget:
            wait = run_budget.bounded_sleep(wait, operation="Serper retry")
        await asyncio.sleep(wait)
    else:
        return [{"error": f"Serper search failed: {last_error or 'retry limit reached'}"}]
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
        cache.set(normalized_query, results, race_id=race_id, provider="serper")

    return results


async def _serper_image_search(
    query: str,
    num_results: int = 10,
    race_id: Optional[str] = None,
    run_budget: RunBudget | None = None,
    max_attempts: int = 2,
) -> List[Dict[str, Any]]:
    """Execute a web image search via the Serper Images API, with caching."""
    normalized_query = re.sub(r"\s+", " ", query or "").strip()
    if not normalized_query:
        logger.warning("_serper_image_search called with empty query — skipping")
        return []
    if len(normalized_query) > _SERPER_MAX_QUERY_CHARS:
        logger.warning(
            "Truncating oversized Serper image query from %s to %s chars: %s",
            len(normalized_query),
            _SERPER_MAX_QUERY_CHARS,
            normalized_query[:120],
        )
        normalized_query = (
            normalized_query[:_SERPER_MAX_QUERY_CHARS].rsplit(" ", 1)[0] or normalized_query[:_SERPER_MAX_QUERY_CHARS]
        )

    cache = _get_search_cache()
    if cache:
        cached = cache.get(normalized_query, race_id)
        if cached:
            logger.debug(f"Image search cache HIT: {normalized_query[:60]}")
            return cached["results"]

    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return [{"error": "SERPER_API_KEY not configured"}]

    if search_provider_exhausted("serper"):
        return await _searlo_search(
            normalized_query,
            num_results=num_results,
            race_id=race_id,
            run_budget=run_budget,
            images=True,
        )

    client = _get_serper_client()
    last_error = ""
    for attempt in range(max(1, max_attempts)):
        if run_budget:
            run_budget.require_call_time(2.0, operation="Serper image search")
        if not reserve_search_call("serper"):
            return [{"error": "Run search budget reached; finish from cached evidence."}]

        request_timeout = (
            run_budget.bounded_timeout(10.0, minimum_seconds=2.0, operation="Serper image search") if run_budget else 10.0
        )
        try:
            resp = await client.post(
                "https://google.serper.dev/images",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": normalized_query, "num": num_results},
                timeout=request_timeout,
            )
            resp.raise_for_status()
            break
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            response_text = exc.response.text[:300] if exc.response is not None else ""
            last_error = f"HTTP {status or 'unknown'}"
            logger.warning(
                "Serper image search failed with HTTP %s for query %r: %s",
                status or "unknown",
                normalized_query[:160],
                response_text,
            )
            try:
                _raise_for_fatal_serper_error(status, response_text)
            except SerperQuotaExhausted:
                mark_search_provider_exhausted("serper")
                return await _searlo_search(
                    normalized_query,
                    num_results=num_results,
                    race_id=race_id,
                    run_budget=run_budget,
                    images=True,
                )
            if status not in {429, 500, 502, 503, 504} or attempt >= max_attempts - 1:
                return [{"error": f"Serper image search failed: {last_error}"}]
        except httpx.HTTPError as exc:
            last_error = str(exc)
            logger.warning("Serper image search request failed for query %r: %s", normalized_query[:160], exc)
            if attempt >= max_attempts - 1:
                return [{"error": f"Serper image search failed: {exc}"}]

        wait = min(15.0, (2**attempt) * random.uniform(0.8, 1.2))
        if run_budget:
            wait = run_budget.bounded_sleep(wait, operation="Serper image retry")
        await asyncio.sleep(wait)
    else:
        return [{"error": f"Serper image search failed: {last_error or 'retry limit reached'}"}]
    data = resp.json()

    results: List[Dict[str, Any]] = []
    for item in data.get("images", []):
        results.append(
            {
                "title": item.get("title", ""),
                "imageUrl": item.get("imageUrl", ""),
                "url": item.get("link", ""),
            }
        )

    if cache:
        cache.set(normalized_query, results, race_id=race_id, provider="serper-images")

    return results


def _extract_links_from_html(html: str, base_url: str) -> List[str]:
    """Find all links on a page, resolve relative URLs, and filter to the same domain."""
    parsed_base = urlparse(base_url)
    base_host = parsed_base.netloc.lower()

    # Simple regex to extract href attributes from anchor tags
    raw_hrefs = re.findall(r'<a\s+(?:[^>]*?\s+)?href=["\'](.*?)["\']', html, re.IGNORECASE)

    resolved: List[str] = []
    seen = set()
    for href in raw_hrefs:
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        try:
            absolute_url = urljoin(base_url, href)
            parsed = urlparse(absolute_url)
            # Only keep http/https links on the same host
            if parsed.scheme in ("http", "https") and parsed.netloc.lower() == base_host:
                # Remove fragment and trailing slash
                clean_url = absolute_url.split("#")[0].rstrip("/")
                if clean_url not in seen:
                    resolved.append(clean_url)
                    seen.add(clean_url)
        except Exception:
            continue
    return resolved


async def get_homepage_policy_links(homepage_url: str) -> List[str]:
    """Fetch homepage, extract links, and filter to policy-relevant ones.

    Used to discover real platform/issue paths instead of blindly guessing them.
    """
    try:
        _validate_url(homepage_url)
    except ValueError as exc:
        logger.warning("Blocked homepage links fetch of disallowed URL %s: %s", homepage_url, exc)
        return []

    client = _get_fetch_client()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    html_content = ""
    try:
        # Try direct fetch first
        resp = await _get_validated(client, homepage_url, headers=headers)
        resp.raise_for_status()
        html_content = resp.text
    except Exception:
        # Fallback to Jina Reader proxy
        proxy_url = text_proxy_url(homepage_url)
        try:
            proxy_resp = await _get_validated(client, proxy_url, headers=text_proxy_headers())
            proxy_resp.raise_for_status()
            # If jina returns markdown, extract links using markdown regex [text](url)
            markdown = proxy_resp.text or ""
            raw_links = re.findall(r"\[.*?\]\((https?://[^\s\)]+)\)", markdown)
            parsed_base = urlparse(homepage_url)
            base_host = parsed_base.netloc.lower()
            seen = set()
            resolved = []
            for u in raw_links:
                u = u.strip()
                try:
                    parsed = urlparse(u)
                    if parsed.netloc.lower() == base_host:
                        clean_url = u.split("#")[0].rstrip("/")
                        if clean_url not in seen:
                            resolved.append(clean_url)
                            seen.add(clean_url)
                except Exception:
                    continue
            # Filter to policy links
            policy_links = [u for u in resolved if any(tok in u.lower() for tok in _POLICY_URL_PATH_TOKENS)]
            return policy_links
        except Exception as proxy_exc:
            logger.debug("Homepage links Jina recovery failed: %s", proxy_exc)
            return []

    if not html_content:
        return []

    all_links = _extract_links_from_html(html_content, homepage_url)
    policy_links = [u for u in all_links if any(tok in u.lower() for tok in _POLICY_URL_PATH_TOKENS)]
    return policy_links
