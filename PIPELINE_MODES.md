# Pipeline Modes

The SmarterVote pipeline supports local and cloud operation modes.

## Local Mode (Default)

Best for development and small-scale use.

**How it works**:
- Agent runs via `pipeline_client/backend/main.py` (FastAPI)
- Web search results cached in SQLite (`data/cache/`)
- Published profiles written to `data/published/` as JSON files
- Races API reads directly from local files

**Setup**:
```powershell
# Install dependencies
pip install -r requirements.txt

# Set API keys in .env
# OPENAI_API_KEY, SERPER_API_KEY

# Start the pipeline backend
cd pipeline_client
uvicorn backend.main:app --port 8001

# Research a race via the dashboard or API
curl -X POST http://localhost:8001/api/run \
  -H "Content-Type: application/json" \
  -d '{"race_id": "mo-senate-2024"}'

# Serve data
cd services/races-api && python main.py
```

## Cloud Mode

For production scaling. Enable via Terraform.

**How it works**:
- Pipeline runs on Cloud Run
- Data publishes to Google Cloud Storage (`gs://bucket/races/`)
- Races API reads from GCS with local caching

**Setup**:
```bash
# Enable cloud deployment
cd infra
# Edit terraform.tfvars: enable_pipeline_client = true
terraform apply

# Set environment variables
export GOOGLE_CLOUD_PROJECT=your-project
export GCS_BUCKET_NAME=your-bucket
```

## Mode Detection

The pipeline auto-detects mode based on environment:

| Variable | Indicates |
|----------|-----------|
| `GOOGLE_CLOUD_PROJECT` | Cloud mode |
| `K_SERVICE` | Cloud Run |
| None of above | Local mode |

## Storage Abstraction

Both modes use the same code via storage backends:

```python
# Local mode
storage = LocalStorageBackend(base_path="data/published")

# Cloud mode
storage = GCPStorageBackend(bucket_name="sv-data")
```

Switch by setting `STORAGE_BACKEND=gcp` environment variable.

## Search Caching

Web search results are cached in SQLite to avoid redundant Serper API calls:
- **TTL**: 7 days (configurable via `SEARCH_CACHE_TTL_HOURS`)
- **Location**: `data/cache/search_cache.db`
- **Scope**: Works in both local and cloud modes

## Output

Both modes produce identical RaceJSON v0.2 files:
- `{race-id}.json` with candidates, issues, sources
- canonical issues per candidate
- Confidence levels (high/medium/low) per issue stance
