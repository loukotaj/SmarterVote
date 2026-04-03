# Pipeline Modes

The SmarterVote pipeline supports local and cloud operation modes.

## Local Mode (Default)

Best for development and small-scale use.

**How it works**:
- Agent runs via `pipeline_client/backend/main.py` (FastAPI)
- Web search results cached in SQLite (`data/cache/`)
- Published profiles written to `data/published/` as JSON files
- Drafts written to `data/drafts/` before publish
- Queue state persisted to `pipeline_client/queue.json`
- Run history and race records held in-memory (lost on restart)
- Races API reads directly from local files

**Setup**:
```powershell
# Install dependencies
pip install -r requirements.txt
pip install -e shared/

# Set API keys in .env
# OPENAI_API_KEY, SERPER_API_KEY

# Start the pipeline backend (from repo root)
python -m uvicorn pipeline_client.backend.main:app --port 8001 --reload

# Research a race via the dashboard or API
curl -X POST http://localhost:8001/api/run \
  -H "Content-Type: application/json" \
  -d '{"race_id": "ga-senate-2026"}'

# Serve published data
cd services/races-api && python main.py
```

## Cloud Mode

For production scaling. Enable via Terraform.

**How it works**:
- Pipeline runs on Cloud Run (Auth0-protected)
- Agent output saves to GCS `drafts/` prefix first
- Admin publishes draft → GCS `races/` prefix
- Races API reads from GCS with 300s TTL cache
- Run history, race records, and queue persist to Firestore

**Setup**:
```bash
# Enable cloud deployment
cd infra
# Edit terraform.tfvars: enable_pipeline_client = true
terraform apply
```

Environment variables are set by Terraform via Secret Manager:
- `STORAGE_MODE=gcp`
- `GCS_BUCKET_NAME=smartervote-sv-data-{env}`
- `FIRESTORE_PROJECT=smartervote`
- API keys via Secret Manager references

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

Both modes produce identical RaceJSON v0.3 files:
- `{race-id}.json` with candidates, issues, sources
- 12 canonical issues per candidate
- Confidence levels (high/medium/low) per issue stance
- Optional multi-LLM review (Claude, Gemini, Grok) with ValidationGrade (A–F)
- Source attribution with freshness tracking
- Optional multi-LLM review (Claude, Gemini, Grok) with ValidationGrade (A–F)
- Source attribution with freshness tracking
