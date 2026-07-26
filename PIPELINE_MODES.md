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

## Cloud Run Job Mode (Production)

The primary cloud architecture. Admin triggers runs through `races-api`; each race runs in a one-shot Cloud Run Job with no idle instance cost or request-timeout handoffs.

**How it works**:

- Admin queues a race via `races-api POST /api/races/queue` (Auth0 authenticated)
- `races-api` creates a document in Firestore `pipeline_queue`
- `races-api` starts `pipeline-job-{env}` with the queue item ID as an execution override
- `pipeline_client.worker` atomically claims that exact item and invokes `AgentHandler`
- Agent runs the configured pipeline steps; progress + logs stream to Firestore `pipeline_runs/`
- The worker renews a Firestore lease and can run for up to the configured job timeout
- Draft saved to GCS `drafts/{race_id}.json`; admin publishes via `races-api` (writing `{race_id}.json` to GCS `races/` and updating the central `races/summaries.json` index)
- Frontend polls `races-api /runs/{run_id}` plus cursor-based `/runs/{run_id}/logs` every 5 seconds while a run is active (or fetches published files statically from GCS if configured)

**Setup** (Terraform):

```bash
cd infra
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
- **Cloud Mode**: Cached in Firestore collections (`search_cache` and `page_cache`) so independent job executions and recovered leases do not repeat expensive searches.

## Local Docker Worker (Permanent)

The long-lived Docker worker is a supported execution mode, not a temporary migration tool. Queue with `runner=local`; the deployed Cloud Run path ignores those items.

```powershell
docker compose -f docker-compose.worker.yml up -d --build
```

It uses the same queue processor and `AgentHandler` as Cloud Run, but polls continuously and supports configurable local concurrency.
- **Activation**: Automatically chooses Firestore if `STORAGE_MODE=gcp`, `FIRESTORE_PROJECT` is set, or running in Cloud Run/Functions. Otherwise falls back to SQLite. You can force-enable the Firestore backend in any environment by setting `SEARCH_CACHE_BACKEND=firestore` (requires `google-cloud-firestore` installed).

## Pipeline Steps

The current ordered step set is:

```text
discovery -> images -> issues -> finance -> refinement -> polling -> forecast -> voter_resources -> review -> iteration
```

The `/steps` endpoint returns the same order with labels and progress weights from `shared/pipeline_config.py`.

## Debug Capture and Diagnostics Export

The observable production path is queue request -> Firestore queue item -> Cloud Run/local worker lease -> `AgentHandler` -> agent phases -> Firestore run/log documents -> races-api -> admin UI. Normal mode keeps human-readable progress and bounded logs. Enable `debug_mode` when diagnosing quality, cost, retry, or handoff behavior; it adds structured step start/progress/complete events, per-step token and estimated-cost deltas, and active-step context to deep agent logs. Progress events are throttled to 10% buckets to limit Firestore writes.

Use it from the admin UI:

1. Queue one or a small number of races through **Batch Queue** and select **Debug capture**. Full research cost rules still apply; debug mode does not make research cheaper.
2. Wait for the run to complete or fail, open it in **Runs**, and select **Export diagnostics**.
3. Provide the downloaded `pipeline-diagnostics-{run_id}.json` for analysis. The export can also be fetched from authenticated `GET /runs/{run_id}/diagnostics`.

The `smartervote.pipeline-diagnostics.v1` bundle contains the sanitized run document, queue/continuation records, chronological logs, structured event timeline, race catalog record, current draft, and a computed draft-quality summary. The summary flags missing or placeholder stances, source coverage, candidate summaries/images/finance fields, pipeline completion, validation grade, token/context/retry metrics, and log truncation. Older runs can also be exported, but the bundle warns when `debug_mode` was not enabled and structured detail is incomplete.

The capture intentionally excludes raw prompts, raw model responses, fetched page bodies, credentials, and API keys. Existing log redaction runs over the complete bundle before it leaves the API. Treat the exported JSON as internal operational data because it can include unpublished draft research.

Firestore reads and writes are bounded for this workflow. Admin log polling uses the opaque `next_cursor` returned by `/runs/{run_id}/logs`, so each poll queries only newer documents; numeric `since` remains a legacy compatibility path and should not be used by new clients. Routine progress updates are coalesced to at most one Firestore write every three seconds while step starts, step completions, and terminal updates remain immediate. Set `PIPELINE_PROGRESS_WRITE_MIN_INTERVAL_SECONDS` to tune that interval (`0` disables coalescing). Diagnostics exports read at most 2,000 log documents and warn when that safety cap is reached.

## Output

All modes produce identical RaceJSON v0.3 files:

- `{race-id}.json` with candidates, issues, sources
- `races/summaries.json` central index (built and served statically in GCS production environment)
- 12 canonical issues per candidate
- Confidence levels (high/medium/low) per issue stance
- Optional OpenRouter-backed multi-model review with ValidationGrade (A–F)
- Source attribution with freshness tracking
