"""Behavioral tests for the SQLite-backed pipeline_client.agent.search_cache.SearchCache.

The FirestoreSearchCache backend used in deployed workers is already exercised
by tests/test_search_cache.py; this file targets the local SQLite backend
(SearchCache), which previously had no direct test coverage at all.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import pipeline_client.agent.search_cache as search_cache_module
from pipeline_client.agent.search_cache import SearchCache, _should_use_firestore_cache, get_search_cache


@pytest.fixture
def cache(tmp_path):
    return SearchCache(cache_dir=str(tmp_path / "cache"), default_ttl_hours=1)


def test_init_creates_db_file_and_tables(cache, tmp_path):
    assert cache.db_path.exists()
    with sqlite3.connect(cache.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"search_cache", "page_cache"}.issubset(tables)


def test_get_miss_returns_none(cache):
    assert cache.get("nonexistent query") is None


def test_set_then_get_returns_cached_results_and_increments_hits(cache):
    results = [{"title": "Result", "url": "https://example.com"}]

    assert cache.set("candidate name issues", results, race_id="ga-senate-2026", provider="serper") is True

    hit = cache.get("candidate name issues", race_id="ga-senate-2026")
    assert hit is not None
    assert hit["results"] == results
    assert hit["provider"] == "serper"
    assert hit["race_id"] == "ga-senate-2026"
    assert hit["from_cache"] is True


def test_get_is_scoped_by_race_id(cache):
    cache.set("shared query", [{"url": "https://a.example"}], race_id="race-a")
    assert cache.get("shared query", race_id="race-b") is None
    assert cache.get("shared query", race_id="race-a") is not None


def test_set_with_expired_ttl_is_not_returned_by_get(cache):
    cache.set("expiring query", [{"url": "https://a.example"}], ttl_hours=-1)

    assert cache.get("expiring query") is None


def test_set_returns_false_and_logs_on_unserializable_results(cache):
    circular: list = []
    circular.append(circular)

    assert cache.set("bad query", circular) is False


def test_get_and_set_page_round_trip(cache):
    assert cache.get_page("https://example.com/page") is None

    assert cache.set_page("https://example.com/page", "page body text") is True

    assert cache.get_page("https://example.com/page") == "page body text"


def test_set_page_with_expired_ttl_is_not_returned(cache):
    cache.set_page("https://example.com/expired", "content", ttl_hours=-1)

    assert cache.get_page("https://example.com/expired") is None


def test_get_stats_reports_totals_and_provider_breakdown(cache):
    cache.set("q1", [{"url": "https://a"}], provider="serper")
    cache.set("q2", [{"url": "https://b"}, {"url": "https://c"}], provider="serper")
    cache.set("q3", [{"url": "https://d"}], provider="google_cse")
    cache.get("q1")  # bump hit count for q1

    stats = cache.get_stats()

    assert stats["total_entries"] == 3
    assert stats["active_entries"] == 3
    assert stats["expired_entries"] == 0
    assert stats["total_hits"] == 1
    assert stats["by_provider"]["serper"]["count"] == 2
    assert stats["by_provider"]["google_cse"]["count"] == 1
    assert stats["db_size_bytes"] > 0


def test_get_stats_counts_expired_entries_separately(cache):
    cache.set("active", [{"url": "https://a"}])
    cache.set("expired", [{"url": "https://b"}], ttl_hours=-1)

    stats = cache.get_stats()

    assert stats["total_entries"] == 2
    assert stats["active_entries"] == 1
    assert stats["expired_entries"] == 1


def test_cleanup_expired_removes_only_expired_rows(cache):
    cache.set("stays", [{"url": "https://a"}])
    cache.set("goes", [{"url": "https://b"}], ttl_hours=-1)
    cache.set_page("https://page-stays", "content")
    cache.set_page("https://page-goes", "content", ttl_hours=-1)

    removed = cache.cleanup_expired()

    assert removed == 2
    assert cache.get("stays") is not None
    assert cache.get("goes") is None
    assert cache.get_page("https://page-stays") is not None
    assert cache.get_page("https://page-goes") is None


def test_cleanup_expired_returns_zero_when_nothing_expired(cache):
    cache.set("stays", [{"url": "https://a"}])

    assert cache.cleanup_expired() == 0


def test_clear_for_race_only_removes_matching_race(cache):
    cache.set("q1", [{"url": "https://a"}], race_id="race-a")
    cache.set("q2", [{"url": "https://b"}], race_id="race-b")

    removed = cache.clear_for_race("race-a")

    assert removed == 1
    assert cache.get("q1", race_id="race-a") is None
    assert cache.get("q2", race_id="race-b") is not None


def test_list_cached_for_race_returns_searches_and_page_urls(cache):
    cache.set("q1", [{"url": "https://a.example"}], race_id="race-a")
    cache.set_page("https://a.example", "content")
    cache.set_page("https://unrelated.example", "content")

    result = cache.list_cached_for_race("race-a")

    assert result["searches"] == [{"query": "q1", "urls": ["https://a.example"]}]
    assert result["page_urls"] == ["https://a.example"]


def test_list_cached_for_race_tolerates_malformed_json_row(cache):
    with sqlite3.connect(cache.db_path) as conn:
        now = datetime.now(timezone.utc)
        conn.execute(
            """
            INSERT INTO search_cache
            (query_hash, query_text, race_id, provider, results, result_count, searched_at, expires_at, hit_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                "hash1",
                "broken query",
                "race-a",
                "serper",
                "not valid json{{{",
                0,
                now.isoformat(),
                (now + timedelta(hours=1)).isoformat(),
            ),
        )
        conn.commit()

    result = cache.list_cached_for_race("race-a")

    assert result["searches"] == [{"query": "broken query", "urls": []}]


def test_clear_all_removes_everything(cache):
    cache.set("q1", [{"url": "https://a"}])
    cache.set_page("https://a", "content")

    removed = cache.clear_all()

    assert removed == 2
    assert cache.get("q1") is None
    assert cache.get_page("https://a") is None


def test_should_use_firestore_cache_explicit_backend_override(monkeypatch):
    monkeypatch.setenv("SEARCH_CACHE_BACKEND", "firestore")
    assert _should_use_firestore_cache() is True

    monkeypatch.setenv("SEARCH_CACHE_BACKEND", "sqlite")
    assert _should_use_firestore_cache() is False


def test_should_use_firestore_cache_defaults_from_storage_mode(monkeypatch):
    monkeypatch.delenv("SEARCH_CACHE_BACKEND", raising=False)
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CLOUD_RUN_SERVICE", raising=False)
    monkeypatch.setenv("STORAGE_MODE", "gcp")

    assert _should_use_firestore_cache() is True


def test_should_use_firestore_cache_local_mode_is_false(monkeypatch):
    monkeypatch.delenv("SEARCH_CACHE_BACKEND", raising=False)
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CLOUD_RUN_SERVICE", raising=False)

    assert _should_use_firestore_cache() is False


def test_get_search_cache_returns_sqlite_singleton_in_local_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(search_cache_module, "_search_cache_instance", None)
    monkeypatch.delenv("SEARCH_CACHE_BACKEND", raising=False)
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CLOUD_RUN_SERVICE", raising=False)
    monkeypatch.setenv("SEARCH_CACHE_DIR", str(tmp_path / "cache"))

    first = get_search_cache()
    second = get_search_cache()

    assert isinstance(first, SearchCache)
    assert first is second

    monkeypatch.setattr(search_cache_module, "_search_cache_instance", None)


def test_get_search_cache_falls_back_to_sqlite_when_firestore_init_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(search_cache_module, "_search_cache_instance", None)
    monkeypatch.setenv("SEARCH_CACHE_BACKEND", "firestore")
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CLOUD_RUN_SERVICE", raising=False)
    monkeypatch.setenv("SEARCH_CACHE_DIR", str(tmp_path / "cache"))

    class ExplodingFirestoreCache:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("no firestore credentials in this test environment")

    monkeypatch.setattr(search_cache_module, "FirestoreSearchCache", ExplodingFirestoreCache)

    instance = get_search_cache()

    assert isinstance(instance, SearchCache)
    monkeypatch.setattr(search_cache_module, "_search_cache_instance", None)


def test_get_search_cache_raises_when_firestore_required_on_cloud_run(monkeypatch):
    monkeypatch.setattr(search_cache_module, "_search_cache_instance", None)
    monkeypatch.setenv("SEARCH_CACHE_BACKEND", "firestore")
    monkeypatch.setenv("K_SERVICE", "races-api")

    class ExplodingFirestoreCache:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("no firestore credentials in this test environment")

    monkeypatch.setattr(search_cache_module, "FirestoreSearchCache", ExplodingFirestoreCache)

    with pytest.raises(RuntimeError, match="Firestore search cache is required"):
        get_search_cache()

    monkeypatch.setattr(search_cache_module, "_search_cache_instance", None)
    monkeypatch.delenv("K_SERVICE", raising=False)
