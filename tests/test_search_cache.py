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
        for doc_id, data in self.collection.docs.items():
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
        for doc_id, data in self.docs.items():
            yield _FakeDocSnapshot(_FakeDocRef(self, doc_id), data)


class _FakeFirestoreClient:
    def __init__(self, *args, **kwargs):
        self.collections = {}

    def collection(self, name):
        self.collections.setdefault(name, _FakeCollection())
        return self.collections[name]


def test_firestore_search_cache_round_trips_search_and_page(monkeypatch):
    fake_firestore = types.SimpleNamespace(Client=_FakeFirestoreClient)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(cloud=types.SimpleNamespace(firestore=fake_firestore)))
    monkeypatch.setitem(sys.modules, "google.cloud", types.SimpleNamespace(firestore=fake_firestore))

    cache = FirestoreSearchCache(project="test-project")
    assert cache.set("roy cooper image", [{"title": "Roy", "url": "https://ballotpedia.org/Roy_Cooper"}], race_id="nc")
    assert cache.set_page("https://ballotpedia.org/Roy_Cooper", "Roy Cooper page text")

    cached = cache.get("roy cooper image", "nc")
    assert cached is not None
    assert cached["results"][0]["url"] == "https://ballotpedia.org/Roy_Cooper"

    race_cache = cache.list_cached_for_race("nc")
    assert race_cache["searches"][0]["query"] == "roy cooper image"
    assert race_cache["page_urls"] == ["https://ballotpedia.org/Roy_Cooper"]
    assert cache.get_page("https://ballotpedia.org/Roy_Cooper") == "Roy Cooper page text"
