# SmarterVote Architecture

SmarterVote has one production API surface: `services/races-api`. The older `pipeline_client` FastAPI app is retained for local development only. Production race research runs as one-shot Cloud Run Job executions; the same worker remains available as a continuous local Docker mode.

## Ownership

| Area                | Path                                         | Role                                                             |
| ------------------- | -------------------------------------------- | ---------------------------------------------------------------- |
| Web app             | `web/`                                       | SvelteKit admin and public UI                                    |
| Production API      | `services/races-api/`                        | Public race reads, admin queue/run/draft/publish APIs, analytics |
| Pipeline worker     | `pipeline_client/worker.py`                  | Cloud Run Job and local Docker entry point                       |
| Admin agent         | `functions/admin_agent/`                     | Durable tool-calling admin tasks and continuations               |
| Queue execution     | `pipeline_client/backend/queue_processor.py` | Shared leases, execution, and terminal state for both runners    |
| Agent orchestration | `pipeline_client/backend/handlers/agent.py`  | Shared `AgentHandler` wrapper                                    |
| Agent research      | `pipeline_client/agent/`                     | Multi-phase AI research implementation                           |
| Shared schema       | `shared/models.py`                           | RaceJSON/Pydantic models shared by agent and APIs                |
| Local dev API       | `pipeline_client/backend/main.py`            | Local-only FastAPI app for in-process agent debugging            |
| Infrastructure      | `infra/`                                     | Terraform for GCP services                                       |

## Production Flow

```text
Admin dashboard
  -> Dashboard for traffic, health, queue state, and run drilldowns
  -> Durable Agent conversation/task API for normal administration
  -> admin_agent_tasks Firestore trigger -> functions/admin_agent/main.py
  -> races-api tools with approval gates for destructive operations
  -> races-api POST /api/races/queue or POST /api/races/{race_id}/run
  -> Firestore pipeline_queue document (`runner=cloud_run`)
  -> races-api starts pipeline-job with QUEUE_ITEM_ID override
  -> pipeline_client.worker one-shot execution
  -> atomic queue lease + heartbeat
  -> AgentHandler.handle()
  -> pipeline_client.agent.run_agent()
  -> GCS drafts/{race_id}.json
  -> Firestore races/{race_id} catalog metadata refresh
  -> races-api publish endpoint
  -> GCS races/{race_id}.json & central races/summaries.json
  -> Firestore races/{race_id} published catalog refresh
  -> public read from direct GCS static hosting
```

Queue documents should contain:

- `id`
- `race_id`
- `run_id`
- `status`
- `options`
- `is_continuation`
- `runner` (`cloud_run` or `local`)
- `created_at`

Each production queue item maps to one Cloud Run Job execution and one logical
`pipeline_runs/{run_id}` record. The worker renews a Firestore lease while active;
expired leases can be reclaimed safely. Logs live under `pipeline_runs/{run_id}/logs`.
Local Docker uses the identical processor with `runner=local` and continuous polling.

## Admin API Surface

The admin dashboard should target `services/races-api`.

| Method | Path                                                        | Purpose                                          |
| ------ | ----------------------------------------------------------- | ------------------------------------------------ |
| GET    | `/steps`                                                    | List configured pipeline steps and weights       |
| GET    | `/api/races`                                                | List Firestore race records                      |
| GET    | `/api/races/{race_id}`                                      | Get one Firestore race record                    |
| DELETE | `/api/races/{race_id}`                                      | Delete race record and associated GCS JSON       |
| POST   | `/api/races/queue`                                          | Queue one or more races                          |
| POST   | `/api/races/recheck`                                        | Reconcile all race records from Firestore/GCS    |
| POST   | `/api/races/{race_id}/run`                                  | Queue a single race                              |
| POST   | `/api/races/{race_id}/cancel`                               | Cancel queued/running race                       |
| POST   | `/api/races/{race_id}/recheck`                              | Reconcile status from Firestore/GCS              |
| GET    | `/runs`                                                     | List recent pipeline runs                        |
| GET    | `/runs/active`                                              | List currently pending/running runs              |
| GET    | `/runs/{run_id}`                                            | Get run details                                  |
| GET    | `/runs/{run_id}/logs`                                       | Get run logs                                     |
| DELETE | `/runs`                                                     | Prune terminal pipeline runs                     |
| DELETE | `/runs/{run_id}`                                            | Cancel or delete a run                           |
| GET    | `/api/queue`                                                | List queue items                                 |
| DELETE | `/api/queue/{item_id}`                                      | Cancel/remove a queue item                       |
| DELETE | `/api/queue/finished`                                       | Clear completed/failed/cancelled queue items     |
| DELETE | `/api/queue/pending`                                        | Cancel pending queue items                       |
| GET    | `/api/races/drafts`                                         | List draft race summaries                        |
| DELETE | `/api/races/{race_id}/draft`                                | Delete draft JSON                                |
| POST   | `/api/races/{race_id}/publish`                              | Publish a race                                   |
| POST   | `/api/races/{race_id}/unpublish`                            | Unpublish a race                                 |
| POST   | `/api/races/publish`                                        | Batch publish drafts                             |
| GET    | `/api/races/{race_id}/data?draft=true`                      | Get draft or published JSON                      |
| GET    | `/api/races/{race_id}/versions`                             | List retired versions                            |
| GET    | `/api/races/{race_id}/versions/{filename}`                  | Read a retired version JSON file                 |
| POST   | `/api/races/{race_id}/versions/{filename}/restore`          | Restore a retired version as the active draft    |
| GET    | `/api/races/{race_id}/runs`                                 | List run history for one race                    |
| GET    | `/api/races/{race_id}/runs/{run_id}`                        | Get one race run                                 |
| DELETE | `/api/races/{race_id}/runs/{run_id}`                        | Cancel or delete one race run                    |
| GET    | `/api/races/chamber_forecasts/draft`                        | Get chamber forecast draft JSON                  |
| POST   | `/api/races/chamber_forecasts/generate`                     | Generate chamber forecast draft from race data   |
| POST   | `/api/races/chamber_forecasts/publish`                      | Publish chamber forecast draft                   |
| GET    | `/pipeline/metrics`                                         | Get pipeline metrics                             |
| GET    | `/pipeline/metrics/summary`                                 | Get summarized pipeline metrics                  |
| GET    | `/alerts`                                                   | List operational alerts                          |
| POST   | `/alerts/{alert_id}/acknowledge`                            | Acknowledge one alert                            |
| POST   | `/alerts/acknowledge-all`                                   | Acknowledge all active alerts                    |
| POST   | `/api/admin-chat`                                           | Legacy synchronous admin chat endpoint           |
| POST   | `/api/admin-agent/conversations`                            | Create a durable admin-agent conversation        |
| GET    | `/api/admin-agent/conversations`                            | List durable admin-agent conversations           |
| GET    | `/api/admin-agent/conversations/{conversation_id}`          | Load messages and recent tasks                   |
| DELETE | `/api/admin-agent/conversations/{conversation_id}`          | Delete one conversation and its messages/tasks   |
| POST   | `/api/admin-agent/conversations/{conversation_id}/messages` | Queue an asynchronous agent task                 |
| GET    | `/api/admin-agent/tasks/{task_id}`                          | Get agent task status                            |
| POST   | `/api/admin-agent/tasks/{task_id}/approve`                  | Approve a protected tool call and continue       |
| POST   | `/api/admin-agent/tasks/{task_id}/cancel`                   | Cancel queued, running, or approval-blocked work |
| POST   | `/cache/clear`                                              | Clear the races API in-memory public data cache  |
| GET    | `/analytics/overview`                                       | Races API request analytics summary              |
| GET    | `/analytics/traffic`                                        | Cloudflare static-site traffic summary           |
| GET    | `/analytics/races`                                          | Races API request counts by race                 |
| GET    | `/analytics/timeseries`                                     | Races API request counts over time               |

Legacy admin aliases were removed; frontend code should use the routes above.

The admin race list is intentionally Firestore-catalog-first. It should not enumerate GCS blobs or fetch per-race
JSON on the hot path; draft/published filter state, candidate counts, grades, and freshness all come from the
`races/{race_id}` catalog document.

Initial population is handled by the existing admin recheck flow. After deploy, `POST /api/races/recheck` sweeps the
existing Firestore race docs plus known GCS draft/published race IDs, hydrates catalog metadata from storage, and
creates missing `races/{race_id}` documents when a race already exists in GCS.

## Public API Surface

| Method | Path                       | Purpose                                                   |
| ------ | -------------------------- | --------------------------------------------------------- |
| GET    | `/races`                   | List published race IDs from `races/summaries.json`       |
| GET    | `/races/summaries`         | List published race summaries from `races/summaries.json` |
| GET    | `/races/chamber_forecasts` | Get published chamber forecast narratives                 |
| GET    | `/races/{race_id}`         | Get full published race data                              |
| GET    | `/health`                  | Liveness                                                  |
| GET    | `/health/ready`            | Readiness                                                 |

If `VITE_PUBLIC_DATA_URL` is set in the web environment, the public SvelteKit frontend bypasses the FastAPI public
read routes entirely and loads published data statically from GCS (`races/{race_id}.json` and `races/summaries.json`).
That is the intended production path for public traffic.

Public page traffic is therefore measured with the Cloudflare Web Analytics browser beacon, not inferred from
`races-api` reads. The authenticated `/analytics/traffic` endpoint queries Cloudflare's GraphQL API and caches the
result for the admin dashboard. API request analytics remain separate and describe `races-api` health only.

## Public Web Surface

The public SvelteKit site separates product introduction from race discovery:

- `/` is the homepage. It explains the product, shows selected national-election content and trust principles, and links into the directory; it is not the full election directory.
- `/elections/` is the browse and filtering surface for published election research. At launch it intentionally includes only national and federal races supported by the existing published data.
- `/races/{slug}/` and its candidate and comparison subroutes remain the detailed research surfaces.
- `/about/`, `/methodology/`, `/corrections/`, `/privacy/`, `/terms/`, and `/funding-and-editorial-independence/` publish the project's current identity, research, correction, privacy, legal, and editorial-independence statements.
- `/support/` and `/partners/` are informational contact pages. They do not accept payments or create financial commitments.

The homepage provides a no-storage national-election lookup. A visitor-entered address is sent directly from the browser to the U.S. Census Geocoder using its documented JSONP interface; Smarter.Vote retains only the returned state and congressional district in page memory long enough to match published U.S. House and Senate summaries. The lookup is not a complete ballot and does not identify state, local, judicial, or ballot-measure contests. There is no autocomplete provider, Smarter.Vote address endpoint, or address persistence. The launch also has no Stripe Checkout, subscriptions, donation processing, or partner payment portal. Public inquiries currently use mail links rather than a server-side CRM or form-processing service.

## Agent Phases

```text
DISCOVERY -> IMAGES -> ISSUES -> FINANCE -> REFINEMENT -> POLLING -> FORECAST -> VOTER_RESOURCES -> REVIEW -> ITERATION
```

Update/rerun mode adds roster and metadata synchronization before re-researching an existing race.

## Storage

| Storage                               | Production Use                                                               |
| ------------------------------------- | ---------------------------------------------------------------------------- |
| GCS `drafts/`                         | Agent output awaiting admin review                                           |
| GCS `races/`                          | Published race JSON served publicly, plus the central `summaries.json` index |
| GCS `retired/`                        | Archived previous versions                                                   |
| Firestore `pipeline_queue`            | Durable work routing, leases, dispatch state, and terminal status            |
| Firestore `pipeline_runs`             | Run status, progress, and logs                                               |
| Firestore `races`                     | Race catalog metadata for admin listing/filtering, plus status and history   |
| Firestore `admin_agent_conversations` | Durable deployed-agent conversation metadata                                 |
| Firestore `admin_agent_messages`      | User, assistant, and tool-call history                                       |
| Firestore `admin_agent_tasks`         | Asynchronous work, approval state, cancellation, and continuations           |
| Secret Manager                        | API keys and admin secrets                                                   |

## Local Development

`pipeline_client/backend/main.py` is local-only and exposes runner/debug routes. The permanent Docker worker is started with `docker-compose.worker.yml` and claims only `runner=local` items. Production correctness should be tested against `services/races-api` plus the shared queue processor and one-shot worker path.

## Migration Guardrails

- Treat `services/races-api` as the canonical API contract.
- Treat `pipeline_runs` as the only run-history store. Do not recreate
  `races/{race_id}/runs` subcollections.
- Do not add new production-only behavior to `pipeline_client/backend/main.py`.
- Keep `web/src/lib/services/pipelineApiService.ts` aligned with `services/races-api` responses.
- Keep queue option models in sync with `pipeline_client.backend.models.RunOptions`.
- Prefer shared helpers for validation and summary shaping instead of duplicating logic.
