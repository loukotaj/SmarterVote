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
async def test_search_raises_when_no_provider_is_configured():
    """With neither provider configured, searching must fail loudly.

    Handing the agent a soft error dict here would invite it to answer from
    unsourced model knowledge, which is the one failure this module exists to
    prevent.
    """
    env = os.environ.copy()
    env.pop("SERPER_API_KEY", None)
    env.pop("SEARLO_API_KEY", None)
    with (
        patch.dict(os.environ, env, clear=True),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        pytest.raises(SearchProviderUnavailable, match="SEARLO_API_KEY"),
    ):
        await _serper_search("test query")


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
async def test_serper_search_falls_back_to_searlo_when_credits_are_exhausted():
    request = httpx.Request("POST", "https://google.serper.dev/search")
    response = httpx.Response(400, request=request, text='{"message":"Not enough credits"}')
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.get = AsyncMock(
        return_value=httpx.Response(
            200,
            request=httpx.Request("GET", "https://api.searlo.tech/api/v1/search/web"),
            json={"organic": [{"title": "Fallback", "snippet": "Evidence", "link": "https://example.com"}]},
        )
    )

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key", "SEARLO_API_KEY": "fallback-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
    ):
        results = await _serper_search("important evidence")

    assert results == [{"title": "Fallback", "snippet": "Evidence", "url": "https://example.com"}]
    assert mock_client.get.call_args.kwargs["headers"] == {"x-api-key": "fallback-key"}


@pytest.mark.asyncio
async def test_serper_search_stops_when_credits_exhausted_without_searlo_key():
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://google.serper.dev/search"),
        text='{"message":"Not enough credits"}',
    )
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)
    env = os.environ.copy()
    env["SERPER_API_KEY"] = "test-key"
    env.pop("SEARLO_API_KEY", None)

    with (
        patch.dict(os.environ, env, clear=True),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
        pytest.raises(SearchProviderUnavailable, match="SEARLO_API_KEY is not configured"),
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
async def test_serper_search_request_and_response_contract():
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://google.serper.dev/search"),
        json={
            "organic": [{"title": "Race guide", "snippet": "Candidate evidence", "link": "https://example.com/race"}],
            "knowledgeGraph": {
                "title": "Arizona Senate",
                "description": "2026 election",
                "website": "https://example.com/election",
            },
        },
    )
    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=client),
    ):
        results = await _serper_search(" Arizona   Senate 2026 ", num_results=4)

    request = client.post.call_args
    assert request.args[0] == "https://google.serper.dev/search"
    assert request.kwargs["headers"] == {"X-API-KEY": "test-key", "Content-Type": "application/json"}
    assert request.kwargs["json"] == {"q": "Arizona Senate 2026", "num": 4}
    assert results[0] == {
        "title": "Arizona Senate",
        "snippet": "2026 election",
        "url": "https://example.com/election",
        "type": "knowledge_graph",
    }
    assert results[1]["url"] == "https://example.com/race"


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
async def test_image_search_raises_when_no_provider_is_configured():
    """The image path fails loudly for the same reason the web path does."""
    env = os.environ.copy()
    env.pop("SERPER_API_KEY", None)
    env.pop("SEARLO_API_KEY", None)
    with (
        patch.dict(os.environ, env, clear=True),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        pytest.raises(SearchProviderUnavailable, match="SEARLO_API_KEY"),
    ):
        await _serper_image_search("test query")


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


@pytest.mark.asyncio
async def test_serper_image_search_falls_back_to_searlo_when_credits_are_exhausted():
    mock_client = MagicMock()
    mock_client.post = AsyncMock(
        return_value=httpx.Response(
            400,
            request=httpx.Request("POST", "https://google.serper.dev/images"),
            text='{"message":"Not enough credits"}',
        )
    )
    mock_client.get = AsyncMock(
        return_value=httpx.Response(
            200,
            request=httpx.Request("GET", "https://api.searlo.tech/api/v1/search/images"),
            json={
                "images": [
                    {
                        "title": "Candidate",
                        "imageUrl": "https://example.com/photo.jpg",
                        "sourceUrl": "https://example.com/candidate",
                    }
                ]
            },
        )
    )

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key", "SEARLO_API_KEY": "fallback-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
    ):
        results = await _serper_image_search("candidate headshot")

    assert results == [
        {
            "title": "Candidate",
            "imageUrl": "https://example.com/photo.jpg",
            "url": "https://example.com/candidate",
        }
    ]


@pytest.mark.asyncio
async def test_searlo_fallback_accepts_documented_items_shape():
    """Keep compatibility with Searlo's documented response during API rollout."""
    mock_client = MagicMock()
    mock_client.post = AsyncMock(
        return_value=httpx.Response(
            400,
            request=httpx.Request("POST", "https://google.serper.dev/search"),
            text='{"message":"Not enough credits"}',
        )
    )
    mock_client.get = AsyncMock(
        return_value=httpx.Response(
            200,
            request=httpx.Request("GET", "https://api.searlo.tech/api/v1/search/web"),
            json={"items": [{"title": "Fallback", "snippet": "Evidence", "link": "https://example.com"}]},
        )
    )

    with (
        patch.dict(os.environ, {"SERPER_API_KEY": "test-key", "SEARLO_API_KEY": "fallback-key"}),
        patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
        patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
    ):
        results = await _serper_search("important evidence")

    assert results == [{"title": "Fallback", "snippet": "Evidence", "url": "https://example.com"}]


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


def test_text_proxy_headers_include_api_key_when_configured(monkeypatch):
    """Anonymous r.jina.ai quota exhaustion looks identical to a site block at every call site."""
    from pipeline_client.agent import web_tools

    monkeypatch.delenv("JINA_API_KEY", raising=False)
    assert "Authorization" not in web_tools.text_proxy_headers()

    monkeypatch.setenv("JINA_API_KEY", "test-key")
    assert web_tools.text_proxy_headers()["Authorization"] == "Bearer test-key"


def test_text_proxy_url_is_unchanged():
    from pipeline_client.agent import web_tools

    assert web_tools.text_proxy_url("https://ballotpedia.org/X") == "https://r.jina.ai/https://ballotpedia.org/X"


def test_total_proxy_failure_is_logged_once(monkeypatch, caplog):
    """A run where every proxy fetch fails must say so, not emit N look-alike per-URL errors."""
    import logging

    from pipeline_client.agent import web_tools

    monkeypatch.delenv("JINA_API_KEY", raising=False)
    monkeypatch.setattr(web_tools, "_proxy_attempts", 0)
    monkeypatch.setattr(web_tools, "_proxy_failures", 0)
    monkeypatch.setattr(web_tools, "_proxy_outage_logged", False)

    with caplog.at_level(logging.WARNING, logger=web_tools.logger.name):
        for _ in range(8):
            web_tools.record_proxy_result(ok=False)

    outage_warnings = [record for record in caplog.records if "has failed all" in record.getMessage()]
    assert len(outage_warnings) == 1
    assert "JINA_API_KEY" in outage_warnings[0].getMessage()
    assert web_tools.proxy_health_snapshot() == {"attempts": 8, "failures": 8}


def test_proxy_success_prevents_outage_warning(monkeypatch, caplog):
    import logging

    from pipeline_client.agent import web_tools

    monkeypatch.delenv("JINA_API_KEY", raising=False)
    monkeypatch.setattr(web_tools, "_proxy_attempts", 0)
    monkeypatch.setattr(web_tools, "_proxy_failures", 0)
    monkeypatch.setattr(web_tools, "_proxy_outage_logged", False)

    with caplog.at_level(logging.WARNING, logger=web_tools.logger.name):
        web_tools.record_proxy_result(ok=True)
        for _ in range(8):
            web_tools.record_proxy_result(ok=False)

    assert not [record for record in caplog.records if "has failed all" in record.getMessage()]


def test_spreadsheet_urls_are_detected_as_tabular():
    from pipeline_client.agent.web_tools import is_tabular_document

    assert is_tabular_document("https://sos.nebraska.gov/x/Statewide_Candidate_Filing_List.xlsx")
    assert is_tabular_document("https://example.gov/list.csv")
    assert not is_tabular_document("https://ballotpedia.org/Some_Race,_2026")
    assert not is_tabular_document("https://example.gov/list.pdf")


def test_xlsx_extraction_reads_rows_without_a_spreadsheet_dependency():
    """Several states publish the certified candidate list as .xlsx.

    The text proxy answers 422 for those even though the file downloads fine, so
    the authoritative roster source was unreadable and finalization deadlocked.
    """
    import io
    import zipfile

    from pipeline_client.agent.web_tools import _xlsx_to_text

    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    shared = (
        f'<sst xmlns="{ns}">'
        "<si><t>For Representative in Congress</t></si>"
        "<si><t>District 02</t></si>"
        "<si><t>Denise Powell</t></si>"
        "</sst>"
    )
    sheet = (
        f'<worksheet xmlns="{ns}"><sheetData>'
        '<row><c t="s"><v>0</v></c><c t="s"><v>1</v></c><c t="s"><v>2</v></c></row>'
        "<row><c><v>2026</v></c></row>"
        "</sheetData></worksheet>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)

    text = _xlsx_to_text(buffer.getvalue())

    assert "For Representative in Congress | District 02 | Denise Powell" in text
    assert "2026" in text


@pytest.mark.asyncio
async def test_searlo_serves_every_search_without_probing_serper():
    """Searlo is the primary provider, so the backup is never dialled.

    The budget accounting is the point: each logical search must reserve one
    slot, not two. Probing a backup that is not needed would halve the run's
    effective research depth.
    """
    from pipeline_client.agent import cost as cost_module
    from pipeline_client.agent.web_tools import _serper_search

    quota_response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://google.serper.dev/search"),
        text='{"message":"Not enough credits"}',
    )
    searlo_response = httpx.Response(
        200,
        request=httpx.Request("GET", "https://api.searlo.tech/api/v1/search/web"),
        json={"organic": [{"title": "Fallback", "snippet": "Evidence", "link": "https://example.com"}]},
    )
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=quota_response)
    mock_client.get = AsyncMock(return_value=searlo_response)

    acc = {"prompt_tokens": 0, "completion_tokens": 0, "serper_calls": 0, "searlo_calls": 0}
    token = cost_module._cost_ctx.set(acc)
    env = os.environ.copy()
    env["SERPER_API_KEY"] = "test-key"
    env["SEARLO_API_KEY"] = "fallback-key"
    try:
        with (
            patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
            patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
            patch.dict(os.environ, env, clear=True),
        ):
            first = await _serper_search("first query")
            second = await _serper_search("second query")
            third = await _serper_search("third query")
    finally:
        cost_module._cost_ctx.reset(token)

    assert first and second and third, "every search returns Searlo evidence"
    # Serper is the backup and Searlo never failed, so it is never called.
    assert mock_client.post.await_count == 0
    assert mock_client.get.await_count == 3
    # Three logical searches must cost three budget slots, not six.
    assert acc["serper_calls"] == 0
    assert acc["searlo_calls"] == 3


@pytest.mark.asyncio
async def test_serper_exhaustion_does_not_leak_between_runs():
    """A fresh run re-probes Serper in case the account was topped up."""
    from pipeline_client.agent import cost as cost_module
    from pipeline_client.agent.cost import mark_search_provider_exhausted, search_provider_exhausted

    first_run = {"serper_calls": 0}
    token = cost_module._cost_ctx.set(first_run)
    try:
        mark_search_provider_exhausted("serper")
        assert search_provider_exhausted("serper") is True
    finally:
        cost_module._cost_ctx.reset(token)

    second_run = {"serper_calls": 0}
    token = cost_module._cost_ctx.set(second_run)
    try:
        assert search_provider_exhausted("serper") is False
    finally:
        cost_module._cost_ctx.reset(token)


def _searlo_ok(title="Primary"):
    return httpx.Response(
        200,
        request=httpx.Request("GET", "https://api.searlo.tech/api/v1/search/web"),
        json={"organic": [{"title": title, "snippet": "Evidence", "link": "https://example.com"}]},
    )


def _searlo_status(status):
    return httpx.Response(
        status,
        request=httpx.Request("GET", "https://api.searlo.tech/api/v1/search/web"),
        text="upstream error",
    )


@pytest.mark.asyncio
async def test_searlo_retries_a_transient_503_and_succeeds():
    """A single 503 must not cost the caller its search.

    Searlo answered ~99.4% of requests during the outage that prompted this,
    yet each stray 503 aborted an entire research step, because the failure
    surfaced as a non-retryable provider error.
    """
    from pipeline_client.agent import cost as cost_module

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[_searlo_status(503), _searlo_ok()])
    mock_client.post = AsyncMock()

    acc = {"serper_calls": 0, "searlo_calls": 0}
    token = cost_module._cost_ctx.set(acc)
    env = {"SEARLO_API_KEY": "k", "SERPER_API_KEY": "s"}
    try:
        with (
            patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
            patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
            patch("pipeline_client.agent.web_tools.asyncio.sleep", new_callable=AsyncMock),
            patch.dict(os.environ, env, clear=True),
        ):
            results = await _serper_search("query")
    finally:
        cost_module._cost_ctx.reset(token)

    assert results[0]["title"] == "Primary"
    assert mock_client.get.await_count == 2
    assert mock_client.post.await_count == 0, "the backup is not needed when the retry succeeds"
    # The retry is the same question asked again, so it must not be billed twice.
    assert acc["searlo_calls"] == 1


@pytest.mark.asyncio
async def test_persistent_searlo_outage_falls_back_to_serper():
    """When Searlo is genuinely down, the backup provider carries the run."""
    from pipeline_client.agent import cost as cost_module

    serper_response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://google.serper.dev/search"),
        json={"organic": [{"title": "Backup", "snippet": "Evidence", "link": "https://example.com"}]},
    )
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=_searlo_status(503))
    mock_client.post = AsyncMock(return_value=serper_response)

    acc = {"serper_calls": 0, "searlo_calls": 0}
    token = cost_module._cost_ctx.set(acc)
    env = {"SEARLO_API_KEY": "k", "SERPER_API_KEY": "s"}
    try:
        with (
            patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
            patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
            patch("pipeline_client.agent.web_tools.asyncio.sleep", new_callable=AsyncMock),
            patch.dict(os.environ, env, clear=True),
        ):
            first = await _serper_search("first")
            second = await _serper_search("second")
    finally:
        cost_module._cost_ctx.reset(token)

    assert first[0]["title"] == "Backup"
    assert second[0]["title"] == "Backup"
    # Searlo is retried within one search, then written off for the run rather
    # than re-probed on every later query.
    assert mock_client.get.await_count == 3
    assert acc["searlo_calls"] == 1


@pytest.mark.asyncio
async def test_searlo_auth_failure_is_not_retried():
    """A rejected key will not heal by waiting, so spend nothing on backoff."""
    from pipeline_client.agent import cost as cost_module

    serper_response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://google.serper.dev/search"),
        json={"organic": [{"title": "Backup", "snippet": "Evidence", "link": "https://example.com"}]},
    )
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=_searlo_status(403))
    mock_client.post = AsyncMock(return_value=serper_response)

    acc = {"serper_calls": 0, "searlo_calls": 0}
    token = cost_module._cost_ctx.set(acc)
    env = {"SEARLO_API_KEY": "k", "SERPER_API_KEY": "s"}
    try:
        with (
            patch("pipeline_client.agent.web_tools._get_serper_client", return_value=mock_client),
            patch("pipeline_client.agent.web_tools._get_search_cache", return_value=None),
            patch("pipeline_client.agent.web_tools.asyncio.sleep", new_callable=AsyncMock),
            patch.dict(os.environ, env, clear=True),
        ):
            results = await _serper_search("query")
    finally:
        cost_module._cost_ctx.reset(token)

    assert results[0]["title"] == "Backup"
    assert mock_client.get.await_count == 1, "403 is terminal; no backoff"
