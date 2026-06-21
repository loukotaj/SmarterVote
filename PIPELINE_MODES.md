# Pipeline Modes

The SmarterVote pipeline supports local development and cloud production modes.

## Local Mode (Default)

Best for development and small-scale use.

**How it works**:

- Agent runs via `pipeline_client/backend/main.py` (FastAPI, port 8001)
- Web search results cached in SQLite (`data/cache/`)
- Published profiles written to `data/published/` as JSON files
- Drafts written to `data/drafts/` before publish
- Races API reads directly from local files
- Frontend targets `services/races-api` for admin/public behavior; direct runner debugging can use the local pipeline API.

**Setup**:

```powershell
# Install dependencies
pip install -r requirements.txt
pip install -e shared/

# Set API keys in .env
# OPENROUTER_API_KEY, SERPER_API_KEY

# Start all services at once (recommended)
.\dev-start.ps1

# Or start individually:
# Pipeline backend
python -m uvicorn pipeline_client.backend.main:app --port 8001 --reload
# Races API
python -m uvicorn main:app --app-dir services/races-api --host 0.0.0.0 --port 8080 --reload
```

## Cloud Function Mode (Production)

The primary cloud architecture. Admin triggers runs via `races-api`; the pipeline runs inside a gen2 Cloud Function invoked by Firestore Eventarc.

**How it works**:

- Admin queues a race via `races-api POST /api/races/queue` (Auth0 authenticated)
- `races-api` creates a document in Firestore `pipeline_queue`
- Firestore Eventarc trigger invokes the gen2 Cloud Function (`functions/agent/main.py`)
- CF imports `AgentHandler` from `pipeline_client.backend.handlers.agent`
- Agent runs the configured pipeline steps; progress + logs stream to Firestore `pipeline_runs/`
- If CF nears the 60-min wall-clock limit, it saves a checkpoint to GCS and enqueues a continuation item (`HandoffTriggered`)
- Draft saved to GCS `drafts/{race_id}.json`; admin publishes via `races-api` (writing `{race_id}.json` to GCS `races/` and updating the central `races/summaries.json` index)
- Frontend polls `races-api /runs/{run_id}` + `/runs/{run_id}/logs?since=N` every 2-3 seconds (or fetches published files statically from GCS if configured)

**Setup** (Terraform):

```bash
cd infra
# enable_agent_function is true by default in variables.tf
terraform apply
```

Environment variables set automatically by Terraform:

- `STORAGE_MODE=gcp`
- `GCS_BUCKET_NAME=smartervote-sv-data-{env}`
- `FIRESTORE_PROJECT=smartervote`
- API keys via Secret Manager

## Mode Detection

The pipeline auto-detects storage mode based on environment:

| Variable               | Indicates  |
| ---------------------- | ---------- |
| `GOOGLE_CLOUD_PROJECT` | Cloud mode |
| `K_SERVICE`            | Cloud Run  |
| None of above          | Local mode |

## Storage Abstraction

Both modes use the same code via storage backends:

```python
# Local mode
storage = LocalStorageBackend(base_path="data/published")

# Cloud mode
storage = GCPStorageBackend(bucket_name="sv-data")
```

Switch by setting `STORAGE_MODE=gcp` and configuring `GCS_BUCKET_NAME`/`FIRESTORE_PROJECT`.

## Search Caching

To avoid redundant Serper API calls and reduce costs, web search results and fetched page contents are cached:

- **TTL**: 7 days for search queries, 24 hours for fetched page text content.
- **Local Mode**: Cached in a local SQLite database (`data/cache/search_cache.db`).
- **Cloud Mode**: Cached in Firestore collections (`search_cache` and `page_cache`). This is critical because Cloud Function instances are ephemeral and trigger continuation handoffs; the shared Firestore cache ensures subsequent invocations don't re-run expensive Serper searches.
- **Activation**: Automatically chooses Firestore if `STORAGE_MODE=gcp`, `FIRESTORE_PROJECT` is set, or running in Cloud Run/Functions. Otherwise falls back to SQLite. You can force-enable the Firestore backend in any environment by setting `SEARCH_CACHE_BACKEND=firestore` (requires `google-cloud-firestore` installed).

## Pipeline Steps

The current ordered step set is:

```text
discovery -> images -> issues -> finance -> refinement -> polling -> forecast -> voter_resources -> review -> iteration
```

The `/steps` endpoint returns the same order with labels and progress weights from `shared/pipeline_config.py`.

## Output

All modes produce identical RaceJSON v0.3 files:

- `{race-id}.json` with candidates, issues, sources
- `races/summaries.json` central index (built and served statically in GCS production environment)
- 12 canonical issues per candidate
- Confidence levels (high/medium/low) per issue stance
- Optional OpenRouter-backed multi-model review with ValidationGrade (A–F)
- Source attribution with freshness tracking
