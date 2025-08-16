from datetime import datetime

from ..schema import Source, SourceType
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
