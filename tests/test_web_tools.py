"""Tests for web tools: Serper search, page fetching, and content analysis."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from pipeline_client.agent.agent import (
    _fetch_page,
    _is_unusable_page_text,
    _page_fetch_log_hint,
    _serper_image_search,
    _serper_search,
)
from pipeline_client.agent.web_tools import SearchProviderUnavailable

# ---------------------------------------------------------------------------
# Serper search tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serper_search_no_api_key():
    """_serper_search returns error when SERPER_API_KEY is not set."""
    env = os.environ.copy()
    env.pop("SERPER_API_KEY", None)
    with (
        patch.dict(os.environ, env, clear=True),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
    ):
        results = await _serper_search("test query")
    assert len(results) == 1
    assert "error" in results[0]


@pytest.mark.asyncio
async def test_serper_search_uses_cache():
    """_serper_search returns cached results when available."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = {"results": [{"title": "Cached", "snippet": "...", "url": "https://cached.com"}]}

    with patch("pipeline_client.agent.web_tools._get_search_cache", return_value=mock_cache):
        results = await _serper_search("test query", race_id="my-race")

    assert results == [{"title": "Cached", "snippet": "...", "url": "https://cached.com"}]
    mock_cache.get.assert_called_once_with("test query", "my-race")


@pytest.mark.asyncio
async def test_serper_search_returns_tool_error_on_http_400():
    """Bad model-generated search queries should not fail the whole pipeline."""
    request = httpx.Request("POST", "https://google.serper.dev/search")
    response = httpx.Response(400, request=request, text="bad request")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
    ):
        results = await _serper_search("bad query")

    assert results == [{"error": "Serper search failed: HTTP 400"}]


@pytest.mark.asyncio
async def test_serper_search_stops_run_when_credits_are_exhausted():
    request = httpx.Request("POST", "https://google.serper.dev/search")
    response = httpx.Response(400, request=request, text='{"message":"Not enough credits"}')
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
        pytest.raises(SearchProviderUnavailable, match="quota exhausted"),
    ):
        await _serper_search("important evidence")


@pytest.mark.asyncio
async def test_serper_search_retries_transient_failure_once():
    request = httpx.Request("POST", "https://google.serper.dev/search")
    unavailable = httpx.Response(503, request=request, text="unavailable")
    success = httpx.Response(
        200,
        request=request,
        json={"organic": [{"title": "Result", "snippet": "Evidence", "link": "https://example.com"}]},
    )
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=[unavailable, success])

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
        patch("pipeline_client.agent.web_tools.random.uniform", return_value=1.0),
        patch("pipeline_client.agent.web_tools.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        results = await _serper_search("retry query")

    assert results == [{"title": "Result", "snippet": "Evidence", "url": "https://example.com"}]
    assert mock_client.post.call_count == 2
    mock_sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_serper_search_truncates_oversized_queries():
    """Oversized queries are trimmed before calling Serper."""
    response = httpx.Response(200, json={"organic": []}, request=httpx.Request("POST", "https://google.serper.dev/search"))
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)
    long_query = " ".join(["georgia governor"] * 80)

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
    ):
        results = await _serper_search(long_query)

    sent_query = mock_client.post.call_args.kwargs["json"]["q"]
    assert results == []
    assert len(sent_query) <= 500


@pytest.mark.asyncio
async def test_serper_image_search_no_api_key():
    """_serper_image_search returns error when SERPER_API_KEY is not set."""
    env = os.environ.copy()
    env.pop("SERPER_API_KEY", None)
    with (
        patch.dict(os.environ, env, clear=True),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
    ):
        results = await _serper_image_search("test query")
    assert len(results) == 1
    assert "error" in results[0]


@pytest.mark.asyncio
async def test_serper_image_search_success():
    """_serper_image_search returns image URLs correctly."""
    response = httpx.Response(
        200,
        json={"images": [{"title": "Image Title", "imageUrl": "https://example.com/img.jpg", "link": "https://example.com"}]},
        request=httpx.Request("POST", "https://google.serper.dev/images"),
    )
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
    ):
        results = await _serper_image_search("candidate headshot")

    assert results == [{"title": "Image Title", "imageUrl": "https://example.com/img.jpg", "url": "https://example.com"}]


# ---------------------------------------------------------------------------
# Page content analysis tests
# ---------------------------------------------------------------------------


def test_is_unusable_page_text_detects_block_pages():
    """Blocked placeholder content is treated as unusable."""
    blocked = "Please enable JavaScript to continue. Attention required by security check."
    assert _is_unusable_page_text(blocked) is True


def test_page_fetch_log_hint_reports_failed_fetch_strings():
    url = "https://www.jeffwadlin.com/issues"
    page_text = "[Failed to fetch https://www.jeffwadlin.com/issues: 403 forbidden]"

    hint = _page_fetch_log_hint(url, page_text)

    assert hint is not None
    assert "fetch failed" in hint
    assert "jeffwadlin.com/issues" in hint


def test_page_fetch_log_hint_flags_short_policy_pages():
    url = "https://www.jeffwadlin.com/issues"
    page_text = "Wadlin for Senate This request returned 403 Forbidden."

    hint = _page_fetch_log_hint(url, page_text)

    assert hint is not None
    assert "short policy-page content" in hint or "blocked/unusable" in hint


# ---------------------------------------------------------------------------
# Page fetching tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_page_uses_proxy_fallback_when_primary_unusable():
    """_fetch_page falls back to proxy when direct fetch is too short/useless."""

    class _Resp:
        def __init__(self, text: str, content_type: str = "text/html; charset=utf-8"):
            self.text = text
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(
        side_effect=[
            _Resp("<html><body>Please enable JavaScript</body></html>"),
            _Resp("<html><body>Please enable JavaScript</body></html>"),
            _Resp("Proxy recovered page text " + ("x" * 500), "text/plain"),
        ]
    )

    with (
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page("https://www.example.com/issues")

    assert "Proxy recovered page text" in result
    assert "[Failed to fetch" not in result


@pytest.mark.asyncio
async def test_fetch_page_attempts_jeff_wadlin_issues_url():
    """_fetch_page issues a direct request to the exact Wadlin issues URL."""

    class _Resp:
        def __init__(self, text: str, content_type: str = "text/html; charset=utf-8"):
            self.text = text
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    target_url = "https://www.jeffwadlin.com/issues"
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=_Resp("Valid issue content " + ("x" * 500)))

    with (
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page(target_url)

    requested_urls = [call.args[0] for call in mock_client.get.call_args_list if call.args]
    assert requested_urls[0] == target_url, "First HTTP call must be directly to the Wadlin issues URL"
    assert "Valid issue content" in result


@pytest.mark.asyncio
async def test_fetch_page_jeff_wadlin_blocked_falls_back_to_proxy_with_correct_url():
    """When jeffwadlin.com returns a JS stub (~214 chars), _fetch_page retries via jina proxy
    using the original https:// URL (not a downgraded http:// version)."""

    class _Resp:
        def __init__(self, text: str, content_type: str = "text/html; charset=utf-8"):
            self.text = text
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    target_url = "https://www.jeffwadlin.com/issues"
    expected_proxy_url = f"https://r.jina.ai/{target_url}"
    proxy_content = "Healthcare: I support a universal 80/20 Medicare-for-all option. " + ("x" * 400)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(
        side_effect=[
            # Both direct header profiles return a tiny JS shell (~214 chars after stripping)
            _Resp("<html><body>Please enable JavaScript</body></html>"),
            _Resp("<html><body>Please enable JavaScript</body></html>"),
            # Jina proxy returns real content
            _Resp(proxy_content, "text/plain"),
        ]
    )

    with (
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page(target_url)

    requested_urls = [call.args[0] for call in mock_client.get.call_args_list if call.args]
    assert requested_urls[0] == target_url, "First call must be the direct Wadlin issues URL"
    assert expected_proxy_url in requested_urls, f"Proxy call must use the original https:// URL \u2014 got: {requested_urls}"
    assert "Medicare-for-all" in result
    assert "[Failed to fetch" not in result


@pytest.mark.asyncio
async def test_fetch_page_short_low_signal_content_prefers_proxy_text():
    """Short low-signal content should trigger proxy probe and prefer richer proxy text."""

    class _Resp:
        def __init__(self, text: str, content_type: str = "text/html; charset=utf-8"):
            self.text = text
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    target_url = "https://www.example.com/issues"
    expected_proxy_url = f"https://r.jina.ai/{target_url}"
    short_primary = "Issue overview page with minimal content and no detailed policy text." + ("x" * 340)
    rich_proxy = "Healthcare section: supports public option and PBM reform. " + ("y" * 2200)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(
        side_effect=[
            _Resp(short_primary),
            _Resp(rich_proxy, "text/plain"),
        ]
    )

    with (
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page(target_url)

    requested_urls = [call.args[0] for call in mock_client.get.call_args_list if call.args]
    assert requested_urls[0] == target_url
    assert expected_proxy_url in requested_urls
    assert "public option" in result


@pytest.mark.asyncio
async def test_fetch_page_policy_url_uses_sitemap_fallback_when_direct_and_proxy_fail():
    """When a policy URL is blocked and the proxy fails too, the fallback crawls the
    site's sitemap to recover policy-relevant content. Works for any candidate site."""

    HOST = "www.example-candidate.org"

    class _Resp:
        def __init__(self, text: str, status_code: int = 200, content_type: str = "text/html; charset=utf-8"):
            self.text = text
            self.status_code = status_code
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"Client error '{self.status_code}'",
                    request=httpx.Request("GET", f"https://{HOST}/issues"),
                    response=httpx.Response(self.status_code),
                )

    target_url = f"https://{HOST}/issues"
    proxy_url = f"https://r.jina.ai/{target_url}"
    sitemap_xml = f"""
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://{HOST}/blog</loc></url>
          <url><loc>https://{HOST}/about</loc></url>
        </urlset>
    """
    blog_html = """
        <html><body>
          <p>On healthcare, I support transparent pricing and stronger rural care access.</p>
          <p>On the economy, I support reducing inflation by limiting federal overspending.</p>
          <p>This platform focuses on practical policy changes for working families, including affordability, opportunity, and accountable government.</p>
          <p>These priorities are repeated across campaign materials to provide clarity for voters and avoid vague slogans.</p>
        </body></html>
    """
    about_html = "<html><body><p>Lorem ipsum dolor sit amet.</p></body></html>"

    async def _mock_get(url, headers=None):
        if url == target_url:
            return _Resp("<html><body>404 Not Found</body></html>", status_code=404)
        if url == proxy_url:
            return _Resp(
                "Title: Just a moment... Warning: Target URL returned error 403: Forbidden", content_type="text/plain"
            )
        if url == f"https://{HOST}/sitemap.xml":
            return _Resp(sitemap_xml, content_type="application/xml")
        if url == f"https://{HOST}/sitemap_index.xml":
            return _Resp("<sitemapindex></sitemapindex>", content_type="application/xml")
        if url == f"https://{HOST}/blog":
            return _Resp(blog_html)
        if url == f"https://{HOST}/about":
            return _Resp(about_html)
        return _Resp("<html><body>Not Found</body></html>", status_code=404)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=_mock_get)

    with (
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page(target_url)

    assert "Recovered issue-related content" in result
    assert "healthcare" in result.lower()
    assert "economy" in result.lower()
    assert "lorem ipsum" not in result.lower()


def test_extract_links_from_html():
    """_extract_links_from_html extracts same-domain http/https links and strips trailing slashes/fragments."""
    from pipeline_client.agent.web_tools import _extract_links_from_html

    html = """
        <html><body>
            <a href="/issues">Issues</a>
            <a href="https://www.example.com/about/">About</a>
            <a href="https://otherdomain.com/issues">Other</a>
            <a href="#fragment">Anchor</a>
            <a href="javascript:void(0)">JS</a>
            <a href="/platform#environment">Relative Fragment</a>
        </body></html>
    """
    links = _extract_links_from_html(html, "https://www.example.com")
    assert links == [
        "https://www.example.com/issues",
        "https://www.example.com/about",
        "https://www.example.com/platform",
    ]


@pytest.mark.asyncio
async def test_get_homepage_policy_links():
    """get_homepage_policy_links filters extracted links for policy keywords."""
    from pipeline_client.agent.web_tools import get_homepage_policy_links

    homepage_html = """
        <html><body>
            <a href="/issues">Issues Platform</a>
            <a href="/about-me">About candidate</a>
            <a href="/priorities">My Priorities</a>
            <a href="/donate">Donate here</a>
        </body></html>
    """

    class _Resp:
        def __init__(self, text: str):
            self.text = text
            self.status_code = 200

        def raise_for_status(self):
            return None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=_Resp(homepage_html))

    with patch("pipeline_client.agent.web_tools._get_fetch_client", return_value=mock_client):
        links = await get_homepage_policy_links("https://www.example.com")

    # Should only return policy-related links, matching /issues and /priorities
    assert "https://www.example.com/issues" in links
    assert "https://www.example.com/priorities" in links
    assert "https://www.example.com/about-me" not in links
    assert "https://www.example.com/donate" not in links


@pytest.mark.asyncio
async def test_fetch_page_sitemap_blocked_falls_back_to_homepage_crawl():
    """When sitemaps return 404, fallback falls back to crawling the homepage for policy links."""
    HOST = "www.no-sitemap.com"

    class _Resp:
        def __init__(self, text: str, status_code: int = 200):
            self.text = text
            self.status_code = status_code
            self.headers = {"content-type": "text/html"}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("Err", request=None, response=None)

    homepage_html = f"""
        <html><body>
            <a href="https://{HOST}/priorities">Priorities</a>
        </body></html>
    """
    # Make Priorities HTML longer to pass the 300-char content check
    priorities_html = """
        <html><body>
          <p>On healthcare, I support public option policies to ensure that every citizen has access to affordable care.</p>
          <p>On economy, I support reducing regulatory overhead, which will help small businesses thrive and create new jobs.</p>
          <p>On education, we must increase funding for public schools and support teachers by raising their salaries across the state.</p>
          <p>On the environment, I advocate for investing in clean energy and reducing carbon emissions to protect our future generations.</p>
        </body></html>
    """

    async def _mock_get(url, headers=None):
        if url == f"https://{HOST}/issues":
            return _Resp("404", 404)
        if url == f"https://r.jina.ai/https://{HOST}/issues":
            return _Resp("Forbidden", 403)
        if url in (f"https://{HOST}/sitemap.xml", f"https://{HOST}/sitemap_index.xml"):
            return _Resp("Not Found", 404)
        if url == f"https://{HOST}/":
            return _Resp(homepage_html)
        if url == f"https://{HOST}/priorities":
            return _Resp(priorities_html)
        return _Resp("404", 404)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=_mock_get)

    with (
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page(f"https://{HOST}/issues")

    assert "Recovered issue-related content" in result
    assert "healthcare" in result.lower()
    assert "economy" in result.lower()
