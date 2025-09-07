# Race Metadata Caching Implementation

This document describes the caching implementation for the RaceMetadataService to reduce redundant API calls and improve response times.

## Overview

The race metadata caching system provides persistent storage of race metadata extraction results in Google Cloud Firestore with configurable TTL (time-to-live) expiry, cache invalidation, and comprehensive observability.

## Architecture

### Components

1. **RaceMetadataCache** (`pipeline/app/utils/race_metadata_cache.py`)
   - Specialized cache for race metadata with TTL support
   - Built on top of existing FirestoreCache infrastructure
   - Handles serialization/deserialization of RaceJSON objects

2. **RaceMetadataService Integration** (`pipeline/app/step01_ingest/MetaDataService/race_metadata_service.py`)
   - Enhanced to support caching with cache-first strategy
   - Added cache management utility methods
   - Includes force refresh capability

3. **Cache Management CLI** (`scripts/manage_race_metadata_cache.py`)
   - Command-line utility for cache administration
   - View, clear, export, and cleanup operations

## Features

### ✅ Persistent Results in GCP Firestore
- Stores complete RaceJSON results from `extract_race_metadata()` 
- Uses race_id as primary document ID to prevent collisions
- Includes metadata for efficient querying (year, state, office_type, candidates_count)

### ✅ Data Freshness & Expiry
- Configurable TTL (default: 12 hours)
- `last_updated` timestamp field in each document
- Automatic expiry checking on retrieval
- Configurable per-request TTL override

### ✅ Cache Invalidation
- `invalidate_cache(race_id)` - Single race invalidation
- `bulk_invalidate_cache(race_ids)` - Bulk invalidation
- `cleanup_expired_entries()` - Remove expired entries
- Force refresh option bypasses cache

### ✅ Reusable Firestore Helper
- Built on existing `FirestoreCache` class
- Specialized `RaceMetadataCache` for metadata-specific operations
- Separate from content extraction cache

### ✅ Observability
- Structured JSON logging for cache hits/misses
- Performance metrics (extraction duration)
- Cache statistics (fresh/expired counts, by state/year)
- Error handling and logging

## Usage

### Basic Usage

```python
from pipeline.app.step01_ingest.MetaDataService.race_metadata_service import RaceMetadataService

# Initialize with caching enabled
service = RaceMetadataService(
    enable_caching=True,
    cache_ttl_hours=12,  # 12-hour TTL
    cache_project_id="your-gcp-project"  # Optional
)

# Extract metadata (checks cache first)
race_json = await service.extract_race_metadata("mo-senate-2024")

# Force refresh (bypasses cache)
race_json = await service.extract_race_metadata("mo-senate-2024", force_refresh=True)

# Cache management
await service.invalidate_cache("mo-senate-2024")
stats = await service.get_cache_stats()
await service.cleanup_expired_cache()
```

### Cache Management CLI

```bash
# View cache statistics
python scripts/manage_race_metadata_cache.py view

# View specific race
python scripts/manage_race_metadata_cache.py view --race-id mo-senate-2024

# Clear specific race cache
python scripts/manage_race_metadata_cache.py clear --race-id mo-senate-2024

# Test connection
python scripts/manage_race_metadata_cache.py test

# Cleanup expired entries
python scripts/manage_race_metadata_cache.py cleanup

# Export race data
python scripts/manage_race_metadata_cache.py export mo-senate-2024 output.json
```

### Configuration Options

```python
RaceMetadataService(
    enable_caching=True,           # Enable/disable caching
    cache_ttl_hours=12,           # Default TTL in hours
    cache_project_id=None,        # GCP project ID (None = default)
)

RaceMetadataCache(
    project_id=None,              # GCP project ID
    collection_name="race_metadata_cache",  # Firestore collection
    default_ttl_hours=12,         # Default TTL
)
```

## Data Schema

### Firestore Document Structure

```json
{
  "race_id": "mo-senate-2024",
  "cached_at": "2024-01-15T10:30:00Z",
  "race_json": { /* Complete RaceJSON object */ },
  "candidates_count": 2,
  "confidence": "medium",
  "year": 2024,
  "state": "MO", 
  "office_type": "senate"
}
```

### Cache Statistics

```json
{
  "total_items": 150,
  "fresh_items": 120,
  "expired_items": 30,
  "ttl_hours": 12,
  "stats_by_year": {"2024": 150},
  "stats_by_state": {"MO": 5, "CA": 10, ...},
  "oldest_cache": "2024-01-10T08:00:00Z",
  "newest_cache": "2024-01-15T12:00:00Z"
}
```

## Logging Examples

### Cache Hit
```json
{
  "ts": "2024-01-15T10:30:00.123Z",
  "level": "info",
  "event": "race_metadata.cache.hit",
  "trace_id": "abc123",
  "race_id": "mo-senate-2024",
  "candidates": 2,
  "confidence": "medium",
  "total_duration_ms": 45
}
```

### Cache Miss
```json
{
  "ts": "2024-01-15T10:30:00.123Z", 
  "level": "info",
  "event": "race_metadata.cache.miss",
  "trace_id": "abc123",
  "race_id": "mo-senate-2024"
}
```

### Cache Store
```json
{
  "ts": "2024-01-15T10:35:00.456Z",
  "level": "info", 
  "event": "race_metadata.cache.store",
  "trace_id": "abc123",
  "race_id": "mo-senate-2024",
  "success": true,
  "candidates": 2,
  "confidence": "medium"
}
```

## Performance Benefits

- **Reduced API Calls**: Eliminates repeated external searches for same race
- **Faster Response Times**: Cache hits typically 50-100x faster than full extraction
- **Lower Costs**: Reduced usage of external APIs (Wikipedia, Ballotpedia, FEC, search)
- **Improved Reliability**: Cached results available even when external services are down

## TTL Strategy

- **Default TTL**: 12 hours balances freshness with performance
- **Election Periods**: Consider shorter TTL (6 hours) during active campaign periods
- **Off-Season**: Longer TTL (24+ hours) acceptable for historical races
- **Custom TTL**: Per-request override for specific needs

## Error Handling

- Cache failures gracefully fall back to normal extraction
- Malformed cache entries are logged and ignored
- Connection errors don't block metadata extraction
- Automatic retry logic for transient Firestore errors

## Testing

### Unit Tests
- `pipeline/app/utils/test_race_metadata_cache.py` - Cache implementation tests
- `tests/test_race_metadata_caching_integration.py` - Service integration tests

### Manual Testing
- `demo_race_metadata_caching.py` - Interactive demonstration
- Firestore emulator support for local testing

### Test with Firestore Emulator

```bash
# Start emulator
gcloud emulators firestore start --host-port=localhost:8080

# Set environment
export FIRESTORE_EMULATOR_HOST=localhost:8080
export GOOGLE_CLOUD_PROJECT=test-project

# Run tests
python -m pytest pipeline/app/utils/test_race_metadata_cache.py
```

## Deployment Considerations

### GCP Setup
- Firestore database must be created
- Service account with Firestore read/write permissions
- Consider regional placement for latency

### Monitoring
- Set up Firestore monitoring for read/write operations
- Monitor cache hit rates in application logs
- Alert on cache error rates

### Maintenance
- Periodic cleanup of expired entries
- Monitor storage costs and retention policies
- Performance tuning based on usage patterns

## Future Enhancements

- **Automatic Background Refresh**: Proactively refresh soon-to-expire entries
- **Multi-Level Caching**: Add memory cache for frequently accessed races
- **Cache Warming**: Pre-populate cache for upcoming elections
- **Compression**: Compress large race data for storage efficiency
- **Metrics Dashboard**: Visual cache performance monitoring