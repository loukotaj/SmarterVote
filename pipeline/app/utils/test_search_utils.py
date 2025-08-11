from datetime import datetime

import pytest

from ..schema import Source, SourceType
from .search_utils import SearchUtils


@pytest.mark.asyncio
async def test_deduplicate_sources_normalizes_tracking_params():
    utils = SearchUtils({})
    url1 = "https://example.com/path?utm_source=news&id=5&fbclid=123"
    url2 = "https://example.com/path?id=5"
    sources = [
        Source(url=url1, type=SourceType.WEBSITE, last_accessed=datetime.utcnow()),
        Source(url=url2, type=SourceType.WEBSITE, last_accessed=datetime.utcnow()),
    ]
    deduped = utils.deduplicate_sources(sources)
    assert len(deduped) == 1
