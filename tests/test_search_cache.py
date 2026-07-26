import sys
import types

from pipeline_client.agent.search_cache import FirestoreSearchCache


class _FakeDocSnapshot:
    def __init__(self, ref, data):
        self.reference = ref
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return dict(self._data or {})


class _FakeDocRef:
    def __init__(self, collection, doc_id):
        self.collection = collection
        self.doc_id = doc_id

    def set(self, data):
        self.collection.docs[self.doc_id] = dict(data)

    def get(self):
        return _FakeDocSnapshot(self, self.collection.docs.get(self.doc_id))

    def update(self, data):
        self.collection.docs.setdefault(self.doc_id, {}).update(data)

    def delete(self):
        self.collection.docs.pop(self.doc_id, None)


class _FakeQuery:
    def __init__(self, collection, field, value):
        self.collection = collection
        self.field = field
        self.value = value

    def stream(self):
        # Snapshot before iterating: callers may delete docs while streaming
        # (e.g. cleanup_expired), which would otherwise raise a "dictionary
        # changed size during iteration" RuntimeError against a live dict.
        for doc_id, data in list(self.collection.docs.items()):
            if data.get(self.field) == self.value:
                yield _FakeDocSnapshot(_FakeDocRef(self.collection, doc_id), data)


class _FakeCollection:
    def __init__(self):
        self.docs = {}

    def document(self, doc_id):
        return _FakeDocRef(self, doc_id)

    def where(self, field, _op, value):
        return _FakeQuery(self, field, value)

    def stream(self):
        for doc_id, data in list(self.docs.items()):
            yield _FakeDocSnapshot(_FakeDocRef(self, doc_id), data)


class _FakeFirestoreClient:
    def __init__(self, *args, **kwargs):
        self.collections = {}

    def collection(self, name):
        self.collections.setdefault(name, _FakeCollection())
        return self.collections[name]


def _make_cache(monkeypatch, project="test-project"):
    fake_firestore = types.SimpleNamespace(Client=_FakeFirestoreClient)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(cloud=types.SimpleNamespace(firestore=fake_firestore)))
    monkeypatch.setitem(sys.modules, "google.cloud", types.SimpleNamespace(firestore=fake_firestore))
    return FirestoreSearchCache(project=project)


def test_firestore_search_cache_round_trips_search_and_page(monkeypatch):
    cache = _make_cache(monkeypatch)
    assert cache.set("roy cooper image", [{"title": "Roy", "url": "https://ballotpedia.org/Roy_Cooper"}], race_id="nc")
    assert cache.set_page("https://ballotpedia.org/Roy_Cooper", "Roy Cooper page text")

    search_doc = cache._db.collection(cache._search_collection).docs[cache._query_hash("roy cooper image", "nc")]
    page_doc = cache._db.collection(cache._page_collection).docs[cache._page_hash("https://ballotpedia.org/Roy_Cooper")]
    assert "ttl_at" in search_doc
    assert "ttl_at" in page_doc

    cached = cache.get("roy cooper image", "nc")
    assert cached is not None
    assert cached["results"][0]["url"] == "https://ballotpedia.org/Roy_Cooper"

    race_cache = cache.list_cached_for_race("nc")
    assert race_cache["searches"][0]["query"] == "roy cooper image"
    assert race_cache["page_urls"] == ["https://ballotpedia.org/Roy_Cooper"]
    assert cache.get_page("https://ballotpedia.org/Roy_Cooper") == "Roy Cooper page text"


def test_firestore_search_cache_get_returns_none_for_missing_doc(monkeypatch):
    cache = _make_cache(monkeypatch)

    assert cache.get("never cached") is None
    assert cache.get_page("https://never-cached.example") is None


def test_firestore_search_cache_get_returns_none_for_expired_doc(monkeypatch):
    cache = _make_cache(monkeypatch)
    cache.set("stale query", [{"url": "https://a"}], ttl_hours=-1)
    cache.set_page("https://stale-page", "content", ttl_hours=-1)

    assert cache.get("stale query") is None
    assert cache.get_page("https://stale-page") is None


def test_firestore_search_cache_decode_results_handles_string_and_garbage(monkeypatch):
    cache = _make_cache(monkeypatch)

    assert cache._decode_results('[{"url": "https://a"}]') == [{"url": "https://a"}]
    assert cache._decode_results("not json") == []
    assert cache._decode_results({"not": "a list"}) == []
    assert cache._decode_results([{"url": "https://a"}, "skip-me", 5]) == [{"url": "https://a"}]


def test_firestore_search_cache_get_stats_reports_provider_breakdown(monkeypatch):
    cache = _make_cache(monkeypatch)
    cache.set("q1", [{"url": "https://a"}], provider="serper")
    cache.set("q2", [{"url": "https://b"}], provider="serper")
    cache.set("q3", [{"url": "https://c"}], provider="google_cse", ttl_hours=-1)
    cache.get("q1")

    stats = cache.get_stats()

    assert stats["total_entries"] == 3
    assert stats["active_entries"] == 2
    assert stats["expired_entries"] == 1
    assert stats["total_hits"] == 1
    assert stats["by_provider"]["serper"] == {"count": 2, "hits": 1}
    assert stats["by_provider"]["google_cse"] == {"count": 1, "hits": 0}
    assert stats["backend"] == "firestore"


def test_firestore_search_cache_cleanup_expired_removes_stale_docs(monkeypatch):
    cache = _make_cache(monkeypatch)
    cache.set("fresh", [{"url": "https://a"}])
    cache.set("stale", [{"url": "https://b"}], ttl_hours=-1)
    cache.set_page("https://fresh-page", "content")
    cache.set_page("https://stale-page", "content", ttl_hours=-1)

    removed = cache.cleanup_expired()

    assert removed == 2
    assert cache.get("fresh") is not None
    assert cache.get("stale") is None


def test_firestore_search_cache_clear_for_race_removes_only_matching_docs(monkeypatch):
    cache = _make_cache(monkeypatch)
    cache.set("q1", [{"url": "https://a"}], race_id="race-a")
    cache.set("q2", [{"url": "https://b"}], race_id="race-b")

    removed = cache.clear_for_race("race-a")

    assert removed == 1
    assert cache.get("q1", race_id="race-a") is None
    assert cache.get("q2", race_id="race-b") is not None


def test_firestore_search_cache_clear_all_removes_search_and_page_docs(monkeypatch):
    cache = _make_cache(monkeypatch)
    cache.set("q1", [{"url": "https://a"}])
    cache.set_page("https://a", "content")

    removed = cache.clear_all()

    assert removed == 2
    assert cache.get("q1") is None
    assert cache.get_page("https://a") is None


def test_firestore_search_cache_get_swallows_backend_errors(monkeypatch):
    cache = _make_cache(monkeypatch)

    class ExplodingCollection:
        def document(self, doc_id):
            raise RuntimeError("firestore unavailable")

    cache._db.collection = lambda name: ExplodingCollection()

    assert cache.get("anything") is None
    assert cache.set("anything", [{"url": "https://a"}]) is False
    assert cache.get_page("https://a") is None
    assert cache.set_page("https://a", "content") is False
    assert cache.list_cached_for_race("race-a") == {"searches": [], "page_urls": []}
    assert cache.get_stats()["total_entries"] == 0
    assert cache.cleanup_expired() == 0
    assert cache.clear_for_race("race-a") == 0
    assert cache.clear_all() == 0
