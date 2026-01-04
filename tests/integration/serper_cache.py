"""
Serper API response caching for reproducible integration tests.

This module provides a file-based cache layer for Serper API responses,
allowing tests to run without making real API calls after the initial cache
population. Caches never expire to ensure test reproducibility.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

# Default cache directory for test fixtures
CACHE_DIR = Path(__file__).parent / "fixtures" / "serper_cache"


def get_cache_key(query: str, search_type: str = "search") -> str:
    """
    Generate a deterministic cache key from search parameters.

    Args:
        query: The search query string
        search_type: The type of search (search, news, etc.)

    Returns:
        MD5 hash of the normalized query parameters
    """
    normalized = f"{search_type}:{query.lower().strip()}"
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def get_cache_path(query: str, search_type: str = "search", cache_dir: Path | None = None) -> Path:
    """
    Get the file path for a cached response.

    Args:
        query: The search query string
        search_type: The type of search
        cache_dir: Optional custom cache directory

    Returns:
        Path to the cache file
    """
    directory = cache_dir or CACHE_DIR
    cache_key = get_cache_key(query, search_type)
    return directory / f"{cache_key}.json"


def read_cache(query: str, search_type: str = "search", cache_dir: Path | None = None) -> dict[str, Any] | None:
    """
    Read a cached Serper response if it exists.

    Args:
        query: The search query string
        search_type: The type of search
        cache_dir: Optional custom cache directory

    Returns:
        The cached response dict, or None if not cached
    """
    cache_path = get_cache_path(query, search_type, cache_dir)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def write_cache(query: str, response: dict[str, Any], search_type: str = "search", cache_dir: Path | None = None) -> Path:
    """
    Write a Serper response to the cache.

    Args:
        query: The search query string
        response: The Serper API response to cache
        search_type: The type of search
        cache_dir: Optional custom cache directory

    Returns:
        Path to the written cache file
    """
    directory = cache_dir or CACHE_DIR
    directory.mkdir(parents=True, exist_ok=True)

    cache_path = get_cache_path(query, search_type, cache_dir)

    # Include metadata for debugging
    cache_data = {"query": query, "search_type": search_type, "response": response}

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)

    return cache_path


def has_cache(query: str, search_type: str = "search", cache_dir: Path | None = None) -> bool:
    """
    Check if a cached response exists for the given query.

    Args:
        query: The search query string
        search_type: The type of search
        cache_dir: Optional custom cache directory

    Returns:
        True if cache exists, False otherwise
    """
    return get_cache_path(query, search_type, cache_dir).exists()


def clear_cache(cache_dir: Path | None = None) -> int:
    """
    Clear all cached responses.

    Args:
        cache_dir: Optional custom cache directory

    Returns:
        Number of cache files deleted
    """
    directory = cache_dir or CACHE_DIR

    if not directory.exists():
        return 0

    count = 0
    for cache_file in directory.glob("*.json"):
        cache_file.unlink()
        count += 1

    return count


def list_cached_queries(cache_dir: Path | None = None) -> list[dict[str, str]]:
    """
    List all cached queries with their metadata.

    Args:
        cache_dir: Optional custom cache directory

    Returns:
        List of dicts with query and search_type for each cached item
    """
    directory = cache_dir or CACHE_DIR

    if not directory.exists():
        return []

    queries = []
    for cache_file in directory.glob("*.json"):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                queries.append(
                    {
                        "query": data.get("query", "unknown"),
                        "search_type": data.get("search_type", "search"),
                        "cache_file": cache_file.name,
                    }
                )
        except (json.JSONDecodeError, IOError):
            continue

    return queries
