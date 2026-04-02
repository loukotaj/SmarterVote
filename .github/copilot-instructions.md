# SmarterVote — Copilot Instructions

## What This Repository Does

SmarterVote is an AI-powered electoral analysis platform. A multi-phase research agent (OpenAI + Serper web search) produces structured candidate profiles (RaceJSON v0.3) covering canonical issues with confidence scoring and source attribution. A SvelteKit frontend displays the data served by a FastAPI races-api.

## Languages & Runtimes

- **Python 3.10+** — backend, agent pipeline, API services
- **TypeScript / Svelte 4 / SvelteKit** — frontend (Node.js 22+)
- **Terraform 1.9+** — GCP infrastructure (Cloud Run, GCS, Firestore, Secret Manager)

## Project Layout

```
pipeline_client/            # FastAPI pipeline backend + AI research agent
  agent/                    # Agent loop, prompts, search cache, review, tools
  backend/                  # FastAPI app (main.py), handlers/, run_manager, queue_manager
  artifacts/                # Raw per-run output snapshots (local dev only)
services/races-api/         # Public FastAPI serving published RaceJSON
web/                        # SvelteKit frontend (static, deployed to GitHub Pages)
shared/                     # Pydantic models shared across Python services
infra/                      # Terraform for GCP
scripts/                    # Deployment helper scripts
data/published/             # Published RaceJSON files (GCS races/ prefix in cloud)
data/drafts/                # Draft RaceJSON files (GCS drafts/ prefix in cloud)
data/cache/                 # SQLite search cache (local only)
tests/                      # Python integration tests
.github/workflows/          # CI + deploy workflows
```

### Key Files

| Purpose | Path |
|---------|------|
| Agent loop | `pipeline_client/agent/agent.py` |
| Prompt templates | `pipeline_client/agent/prompts.py` |
| Agent step handler | `pipeline_client/backend/handlers/agent.py` |
| Pipeline API | `pipeline_client/backend/main.py` |
| Run lifecycle manager | `pipeline_client/backend/run_manager.py` |
| Queue manager | `pipeline_client/backend/queue_manager.py` |
| Pipeline step models | `pipeline_client/backend/models.py` |
| Pydantic models (v0.3) | `shared/models.py` |
| TypeScript types | `web/src/lib/types.ts` |
| Frontend pipeline service | `web/src/lib/services/pipelineApiService.ts` |
| Races-api public service | `services/races-api/simple_publish_service.py` |
| CI workflow | `.github/workflows/ci.yaml` |
| CD workflow | `.github/workflows/terraform-deploy.yaml` |

## CI/CD Pipeline

### CI (`.github/workflows/ci.yaml`)

Triggers on push to `main`/`develop` and PRs to `main`. All four jobs must pass:

1. **test-pipeline** — `PYTHONPATH=. python -m pytest tests/test_pipeline.py -v`
2. **test-apis** — races-api pytest suite
3. **test-web** — `npm run check`, `npm run build`, `npm run test:unit`
4. **terraform-validate** — `terraform fmt -check` + `terraform validate`

### CD (`.github/workflows/terraform-deploy.yaml`)

Triggers automatically when CI completes successfully on `main` (via `workflow_run`). Also triggerable manually via `workflow_dispatch`.

Steps:
1. **Build containers** — builds and pushes `pipeline-client` and `races-api` Docker images to Artifact Registry (`us-central1-docker.pkg.dev/smartervote/smartervote-dev/`)
2. **Deploy infrastructure** — `terraform apply` updates Cloud Run services, secrets, GCS, Firestore config

**Every push to `main` that passes CI will automatically redeploy both Cloud Run services.** No manual deploy step needed for normal code changes.

Manual deploy (emergency/bypass):
```powershell
.\scripts\deploy_pipeline_client.ps1   # rebuild + push + deploy pipeline-client
.\scripts\deploy_races_api.ps1         # rebuild + push + deploy races-api
```

## Cloud Architecture (GCP `smartervote` project, `dev` environment)

| Service | Description |
|---------|-------------|
| `pipeline-client-dev` | Cloud Run — FastAPI pipeline backend, Auth0-protected |
| `races-api-dev` | Cloud Run — public read-only races API |
| `smartervote-sv-data-dev` | GCS bucket — `races/` (published), `drafts/` (agent output) |
| Firestore | Run history (pipeline run metadata, status, steps) |
| Secret Manager | API keys (openai, serper, anthropic, gemini, xai, admin key) |

### Draft → Publish Lifecycle

```
POST /api/run  →  agent runs  →  saves to GCS drafts/{race_id}.json
                                  (draft, not live)
                    ↓  admin reviews via ?draft=true preview
POST /drafts/{race_id}/publish  →  copies drafts/ → races/ in GCS
                                    (races-api now serves it)
```

The races-api reads exclusively from `GCS races/` in cloud mode (with 300s TTL cache). Drafts are never served publicly.

## Pipeline API Endpoints (all Auth0-protected except `/health`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/run` | POST | Run the research agent for a race_id |
| `/queue` | GET/POST/DELETE | Manage the processing queue |
| `/drafts` | GET | List all drafts |
| `/drafts/{race_id}` | GET/DELETE | Get or delete a draft |
| `/drafts/{race_id}/publish` | POST | Promote draft → published |
| `/races` | GET | List published races |
| `/races/{race_id}` | GET/DELETE | Get or delete a published race |
| `/races/{race_id}/unpublish` | POST | Remove from published (keeps draft) |
| `/runs` | GET | List recent runs (from Firestore) |
| `/runs/{run_id}` | GET/DELETE | Get or delete a run record |
| `/run/{step}` | POST | Run a named pipeline step directly |
| `/artifact/{artifact_id}` | GET | Retrieve a stored artifact |
| `/health` | GET | Health check (unauthenticated) |

### RunOptions (passed in `POST /api/run`)

```json
{
  "race_id": "ga-senate-2026",
  "options": {
    "cheap_mode": true,          // cheaper/faster models (default: true)
    "enable_review": false,      // multi-LLM review via Claude/Gemini/Grok
    "max_candidates": null,      // limit candidates researched (null = all)
    "target_no_info": false,     // prioritize candidates with least data
    "enabled_steps": null        // list of step names to run (null = all)
  }
}
```

## Run Management

- **Active runs** — held in-memory on the Cloud Run instance; progress broadcast via WebSocket (`/ws`)
- **Completed/failed runs** — persisted to Firestore (`pipeline_runs` collection) in background
- **Local dev** — no Firestore → in-memory only, lost on restart (acceptable)
- Run status flow: `pending → running → completed | failed | cancelled`

## Agent Phases

DISCOVER → RESEARCH (×6 issue groups) → REFINE → REVIEW (optional, multi-LLM)

Post-run: Gemini Flash analysis saved to `pipeline_client/post_run_analyses/`

## Canonical Issues

Healthcare, Economy, Climate/Energy, Reproductive Rights, Immigration, Guns & Safety, Foreign Policy, Social Justice, Education, Tech & AI, Election Reform, Local Issues

Defined in `shared/models.py` (`CanonicalIssue` enum) and `pipeline_client/agent/prompts.py`. Keep these consistent everywhere.

## Coding Conventions

### Python

- **Black** (line-length 127, target py310) + **isort** (profile "black")
- Pydantic v2 — use `model_dump()` / `model_validate()`, not deprecated v1 methods
- Async where applicable; structured logging with module-level loggers

### TypeScript / Svelte

- Types in `web/src/lib/types.ts` must mirror Python models in `shared/models.py`
- Components in `web/src/lib/components/`; routes use `+page.svelte`
- Prettier + ESLint for formatting; TailwindCSS for styling

## Build & Test Commands

```bash
# Python tests (from repo root)
PYTHONPATH=. python -m pytest tests/test_pipeline.py -v
cd services/races-api && PYTHONPATH=../.. python -m pytest test_races_api.py -v

# Python formatting
black --line-length 127 --target-version py310 <file>
isort --profile black --line-length 127 <file>

# Frontend
cd web && npm ci && npm run build
cd web && npm run test:unit
cd web && npm run check

# Terraform
cd infra && terraform fmt -check -recursive
cd infra && terraform init -backend=false && terraform validate
```

## Local Development (brief)

For quick local iteration only — cloud is the primary environment.

```bash
# Pipeline backend
cd pipeline_client && uvicorn backend.main:app --port 8001 --reload

# Races API
cd services/races-api && python main.py   # reads data/published/ locally

# Frontend
cd web && npm run dev
```

Requires `.env` at repo root with `OPENAI_API_KEY`, `SERPER_API_KEY`. Without GCS configured, runs save drafts to `data/drafts/` and run history is in-memory only.

## Important Rules

1. Keep canonical issues consistent across all outputs.
2. Preserve confidence scoring and source attribution in any data changes.
3. Keep `shared/models.py` and `web/src/lib/types.ts` in sync.
4. Agent runs always save to **drafts** first — never directly to published. Publish is an explicit admin action.
5. Always run `PYTHONPATH=.` when invoking pytest from the repo root.
6. Always run `npm ci` in `web/` before building or testing the frontend.
7. GCS bucket env var is `GCS_BUCKET_NAME` (also aliased as `GCS_BUCKET` / `BUCKET_NAME`).
8. Firestore project env var is `FIRESTORE_PROJECT`. Without it, run history is ephemeral.
