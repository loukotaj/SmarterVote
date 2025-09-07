import asyncio
from datetime import datetime
from unittest.mock import patch, AsyncMock

import pytest

from ..schema import CanonicalIssue, FreshSearchQuery, Source, SourceType
from .search_utils import SearchUtils


def test_deduplicate_sources_ignores_query_params():
    utils = SearchUtils({})
    url1 = "https://example.com/path?utm_source=news&id=5&fbclid=123"
    url2 = "https://example.com/path?id=5"
    sources = [
        Source(url=url1, type=SourceType.WEBSITE, last_accessed=datetime.utcnow()),
        Source(url=url2, type=SourceType.WEBSITE, last_accessed=datetime.utcnow()),
    ]
    deduped = utils.deduplicate_sources(sources)
    assert len(deduped) == 1
    # URL is normalized, so tracking params are removed
    assert str(deduped[0].url) == url2


def test_default_serper_mode_returns_mock_when_no_key():
    utils = SearchUtils({})
    query = FreshSearchQuery(race_id="tx-sen-2024", text="test")
    results = asyncio.run(utils.search_google_custom(query, CanonicalIssue.ECONOMY))
    assert len(results) == 1
    assert "serper" in str(results[0].url)


@pytest.mark.asyncio
async def test_serper_date_param_conversion():
    """Test that date parameters are correctly converted for Serper API."""
    utils = SearchUtils({"search_provider": "serper"})
    
    # Mock the httpx response
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "organic": [
            {
                "link": "https://example.com/test",
                "title": "Test Result",
                "snippet": "Test snippet"
            }
        ]
    }
    mock_response.raise_for_status = AsyncMock()
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    
    with patch.dict('os.environ', {'SERPER_API_KEY': 'test-key'}):
        with patch('httpx.AsyncClient', return_value=mock_client):
            # Test d30 format (30 days)
            query = FreshSearchQuery(race_id="test", text="test", date_restrict="d30")
            await utils._search_serper(query, CanonicalIssue.ECONOMY, datetime.utcnow())
            
            # Verify the payload sent to API
            call_args = mock_client.post.call_args
            payload = call_args[1]['json']
            assert payload['dateRestrict'] == 'd30'
            
            # Test y2 format (2 years)
            query = FreshSearchQuery(race_id="test", text="test", date_restrict="y2")
            await utils._search_serper(query, CanonicalIssue.ECONOMY, datetime.utcnow())
            
            call_args = mock_client.post.call_args
            payload = call_args[1]['json']
            assert payload['dateRestrict'] == 'y2'


@pytest.mark.asyncio
async def test_serper_handles_empty_organic_results():
    """Test that Serper search handles empty organic results gracefully."""
    utils = SearchUtils({"search_provider": "serper"})
    
    # Mock response with no organic results
    mock_response = AsyncMock()
    mock_response.json.return_value = {"someOtherField": "value"}
    mock_response.raise_for_status = AsyncMock()
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    
    with patch.dict('os.environ', {'SERPER_API_KEY': 'test-key'}):
        with patch('httpx.AsyncClient', return_value=mock_client):
            query = FreshSearchQuery(race_id="test", text="test")
            results = await utils._search_serper(query, CanonicalIssue.ECONOMY, datetime.utcnow())
            
            assert results == []


@pytest.mark.asyncio  
async def test_serper_request_headers():
    """Test that Serper requests include correct headers."""
    utils = SearchUtils({"search_provider": "serper"})
    
    mock_response = AsyncMock()
    mock_response.json.return_value = {"organic": []}
    mock_response.raise_for_status = AsyncMock()
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    
    with patch.dict('os.environ', {'SERPER_API_KEY': 'test-api-key'}):
        with patch('httpx.AsyncClient', return_value=mock_client):
            query = FreshSearchQuery(race_id="test", text="test")
            await utils._search_serper(query, CanonicalIssue.ECONOMY, datetime.utcnow())
            
            # Verify headers
            call_args = mock_client.post.call_args
            headers = call_args[1]['headers']
            assert headers['X-API-KEY'] == 'test-api-key'
            assert headers['Content-Type'] == 'application/json'
