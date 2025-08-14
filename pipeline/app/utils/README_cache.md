# Firestore Content Caching

This module provides Firestore-based caching for extracted content that has passed the AI relevance filter in the SmarterVote pipeline.

## Overview

The caching system stores filtered `ExtractedContent` objects in Google Cloud Firestore after they pass the AI relevance check. This allows for:

- **Data persistence**: Relevant content is preserved beyond the pipeline run
- **Analytics**: Historical analysis of content extraction and relevance patterns
- **Debugging**: Review what content was cached for specific races
- **Backup**: Additional storage layer for processed content

## Architecture

```
Pipeline Flow:
Extract → Relevance Filter → [CACHE TO FIRESTORE] → Corpus → ...
```

The caching happens in `__main__.py` right after the relevance filtering step:

```python
# Step 3: EXTRACT - HTML/PDF → plain text
filtered_content = await self.relevance.filter_content(extracted_content)

# Cache the filtered content to Firestore
cache_success = await self.cache.cache_content(race_id, filtered_content)
```

## Configuration

### Environment Setup

1. **Google Cloud Project**: Ensure you have a GCP project with Firestore enabled
2. **Authentication**: Use one of:
   - Service account key file (`GOOGLE_APPLICATION_CREDENTIALS` environment variable)
   - Application Default Credentials (if running on GCP)
   - For local development: `gcloud auth application-default login`

### Pipeline Integration

The cache is automatically initialized in the `CorpusFirstPipeline` class:

```python
self.cache = FirestoreCache()  # Uses default settings
```

Or with custom configuration:

```python
self.cache = FirestoreCache(
    project_id="your-project-id",
    collection_name="custom_cache_collection"
)
```

## Data Structure

Each cached document contains:

```python
{
    "race_id": "mo-senate-2024",
    "source_url": "https://example.com/article",
    "source_type": "website",
    "text": "Full extracted text content...",
    "metadata": {
        "content_checksum": "abc123...",
        "word_count": 1500,
        "usefulness_score": 0.85,
        "extraction_method": "html_readability",
        # ... other metadata
    },
    "extraction_timestamp": "2025-01-15T10:30:00Z",
    "word_count": 1500,
    "language": "en",
    "cached_at": "2025-01-15T10:35:00Z",
}
```

## Usage Examples

### Programmatic Access

```python
from utils.firestore_cache import FirestoreCache

# Initialize cache
cache = FirestoreCache()

# Retrieve cached content for a race
cached_items = await cache.get_cached_content("mo-senate-2024")

# Get cache statistics
stats = await cache.get_cache_stats("mo-senate-2024")
print(f"Cached {stats['total_items']} items")

# Clear cache for a race (use carefully!)
await cache.clear_cache("mo-senate-2024")

# Always close when done
await cache.close()
```

### Command Line Management

Use the cache manager utility:

```bash
# View cached content for a race
python -m app.utils.cache_manager view --race-id mo-senate-2024

# View overall cache statistics
python -m app.utils.cache_manager view

# Export cache to JSON
python -m app.utils.cache_manager export mo-senate-2024 cache_export.json

# Clear cache for a race
python -m app.utils.cache_manager clear --race-id mo-senate-2024

# Test connection
python -m app.utils.cache_manager test
```

## Deduplication

The cache automatically handles duplicates using:

- **Content checksum**: Prevents exact duplicates from being cached multiple times
- **Document ID**: Uses `{race_id}_{checksum[:16]}` format for unique identification

## Error Handling

The caching system is designed to be resilient:

- **Non-blocking**: Cache failures don't stop the pipeline
- **Graceful degradation**: Pipeline continues even if caching fails
- **Logging**: All cache operations are logged for debugging

## Local Development

For local testing, you can use the Firestore emulator:

```bash
# Install and start emulator
firebase emulators:start --only=firestore

# Set environment variable
export FIRESTORE_EMULATOR_HOST=localhost:8080

# Run tests
python test_cache_standalone.py
```

## Monitoring

Key metrics to monitor:

- **Cache success rate**: Percentage of successful cache operations
- **Storage usage**: Firestore storage consumption
- **Performance**: Cache operation latency

Check logs for:
- Cache operation results
- Serialization warnings
- Connection issues

## Best Practices

1. **Resource cleanup**: Always call `await cache.close()` when done
2. **Error handling**: Don't let cache failures break your application
3. **Monitoring**: Watch for serialization errors in complex metadata
4. **Security**: Use least-privilege service accounts for Firestore access

## Limitations

- **Metadata serialization**: Complex objects are converted to strings
- **Size limits**: Firestore document size limit is 1MB
- **Cost**: Firestore operations incur charges based on reads/writes
- **Consistency**: Eventual consistency model (usually fast, but not immediate)

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure `google-cloud-firestore` is installed
2. **Authentication**: Check GCP credentials and project access
3. **Permissions**: Ensure service account has Firestore read/write access
4. **Unicode issues**: Windows console may have encoding problems with emojis

### Debug Steps

1. Test connection: `python -m app.utils.cache_manager test`
2. Check logs for detailed error messages
3. Verify GCP project and Firestore setup
4. Test with Firestore emulator locally
