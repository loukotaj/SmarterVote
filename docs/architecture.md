# SmarterVote Architecture

SmarterVote has one production API surface: `services/races-api`. The older `pipeline_client` FastAPI app is retained for local development only. Production agent work runs in a gen2 Cloud Function triggered from Firestore.

## Ownership

| Area | Path | Role |
|------|------|------|
| Web app | `web/` | SvelteKit admin and public UI |
| Production API | `services/races-api/` | Public race reads, admin queue/run/draft/publish APIs, analytics |
| Agent trigger | `functions/agent/` | Firestore Eventarc Cloud Function entry point |
| Admin agent | `functions/admin_agent/` | Durable tool-calling admin tasks and continuations |
| Agent orchestration | `pipeline_client/backend/handlers/agent.py` | `AgentHandler` wrapper used by the Cloud Function |
| Agent research | `pipeline_client/agent/` | Multi-phase AI research implementation |
| Shared schema | `shared/models.py` | RaceJSON/Pydantic models shared by agent and APIs |
| Local dev API | `pipeline_client/backend/main.py` | Local-only FastAPI app for in-process agent debugging |
| Infrastructure | `infra/` | Terraform for GCP services |

## Production Flow

```text
Admin dashboard
  -> Dashboard for traffic, health, queue state, and run drilldowns
  -> Durable Agent conversation/task API for normal administration
  -> admin_agent_tasks Firestore trigger -> functions/admin_agent/main.py
  -> races-api tools with approval gates for destructive operations
  -> races-api POST /api/races/queue or POST /api/races/{race_id}/run
  -> Firestore pipeline_queue document
  -> Eventarc document-create trigger
  -> functions/agent/main.py
  -> AgentHandler.handle()
  -> pipeline_client.agent.run_agent()
  -> GCS drafts/{race_id}.json
  -> races-api publish endpoint
  -> GCS races/{race_id}.json & central races/summaries.json
  -> public read (FastAPI races-api OR direct GCS static hosting)
```

Queue documents should contain:

- `id`
- `race_id`
- `run_id`
- `status`
- `options`
- `is_continuation`
- `created_at`

The Cloud Function updates `pipeline_runs/{run_id}`, writes logs under `pipeline_runs/{run_id}/logs`, and updates `races/{race_id}` metadata.

## Admin API Surface

The admin dashboard should target `services/races-api`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/races` | List Firestore race records |
| GET | `/api/races/{race_id}` | Get one Firestore race record |
| DELETE | `/api/races/{race_id}` | Delete race record and associated GCS JSON |
| POST | `/api/races/queue` | Queue one or more races |
| POST | `/api/races/{race_id}/run` | Queue a single race |
| POST | `/api/races/{race_id}/cancel` | Cancel queued/running race |
| POST | `/api/races/{race_id}/recheck` | Reconcile status from Firestore/GCS |
| GET | `/runs` | List recent pipeline runs |
| GET | `/runs/{run_id}` | Get run details |
| GET | `/runs/{run_id}/logs` | Get run logs |
| DELETE | `/runs/{run_id}` | Cancel or delete a run |
| GET | `/api/queue` | List queue items |
| DELETE | `/api/queue/{item_id}` | Cancel/remove a queue item |
| DELETE | `/api/queue/finished` | Clear completed/failed/cancelled queue items |
| DELETE | `/api/queue/pending` | Cancel pending queue items |
| GET | `/api/races/drafts` | List draft race summaries |
| DELETE | `/api/races/{race_id}/draft` | Delete draft JSON |
| POST | `/api/races/{race_id}/publish` | Publish a race |
| POST | `/api/races/{race_id}/unpublish` | Unpublish a race |
| POST | `/api/races/publish` | Batch publish drafts |
| GET | `/api/races/{race_id}/data?draft=true` | Get draft or published JSON |
| GET | `/api/races/{race_id}/versions` | List retired versions |
| POST | `/api/admin-agent/conversations` | Create a durable admin-agent conversation |
| GET | `/api/admin-agent/conversations/{conversation_id}` | Load messages and recent tasks |
| POST | `/api/admin-agent/conversations/{conversation_id}/messages` | Queue an asynchronous agent task |
| GET | `/api/admin-agent/tasks/{task_id}` | Get agent task status |
| POST | `/api/admin-agent/tasks/{task_id}/approve` | Approve a protected tool call and continue |
| POST | `/api/admin-agent/tasks/{task_id}/cancel` | Cancel queued, running, or approval-blocked work |
| GET | `/analytics/traffic` | Cloudflare static-site traffic summary |

Legacy admin aliases were removed; frontend code should use the routes above.

## Public API Surface

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/races` | List published race IDs |
| GET | `/races/summaries` | List published race summaries |
| GET | `/races/{race_id}` | Get full published race data |
| GET | `/health` | Liveness |
| GET | `/health/ready` | Readiness |

If `VITE_PUBLIC_DATA_URL` is set in the web environment, the public SvelteKit frontend will bypass the FastAPI public read routes (`/races/*`) and load data statically from GCS (`races/{race_id}.json` and `races/summaries.json`).

Public page traffic is therefore measured with the Cloudflare Web Analytics browser beacon, not inferred from
`races-api` reads. The authenticated `/analytics/traffic` endpoint queries Cloudflare's GraphQL API and caches the
result for the admin dashboard. API request analytics remain separate and describe `races-api` health only.

## Agent Phases

```text
DISCOVERY -> IMAGES -> ISSUES -> FINANCE -> REFINEMENT -> REVIEW -> ITERATION
```

Update/rerun mode adds roster and metadata synchronization before re-researching an existing race.

## Storage

| Storage | Production Use |
|---------|----------------|
| GCS `drafts/` | Agent output awaiting admin review |
| GCS `races/` | Published race JSON served publicly, plus the central `summaries.json` index |
| GCS `retired/` | Archived previous versions |
| Firestore `pipeline_queue` | Queue items that trigger Cloud Function runs |
| Firestore `pipeline_runs` | Run status, progress, and logs |
| Firestore `races` | Race metadata, grading data, status, history |
| Firestore `admin_agent_conversations` | Durable deployed-agent conversation metadata |
| Firestore `admin_agent_messages` | User, assistant, and tool-call history |
| Firestore `admin_agent_tasks` | Asynchronous work, approval state, cancellation, and continuations |
| Secret Manager | API keys and admin secrets |

## Local Development

`pipeline_client/backend/main.py` is local-only and exposes only runner/debug routes such as `/api/run`, `/run/{step}`, and `/runs/*`. Production correctness should be tested against `services/races-api` plus the Cloud Function handler path.

## Migration Guardrails

- Treat `services/races-api` as the canonical API contract.
- Do not add new production-only behavior to `pipeline_client/backend/main.py`.
- Keep `web/src/lib/services/pipelineApiService.ts` aligned with `services/races-api` responses.
- Keep queue option models in sync with `pipeline_client.backend.models.RunOptions`.
- Prefer shared helpers for validation and summary shaping instead of duplicating logic.
