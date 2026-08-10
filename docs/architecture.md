# SmarterVote Architecture

SmarterVote has one production API surface: `services/races-api`. The older `pipeline_client` FastAPI app is retained for local development only. Production race research runs as one-shot Cloud Run Job executions; the same worker remains available as a continuous local Docker mode.

## Ownership

| Area                | Path                                         | Role                                                             |
| ------------------- | -------------------------------------------- | ---------------------------------------------------------------- |
| Web app             | `web/`                                       | SvelteKit admin and public UI                                    |
| Marketing design system | `design-system/`                         | React components and tokens for Claude-generated marketing assets; not deployed with the web app |
| Production API      | `services/races-api/`                        | Public race reads, admin queue/run/draft/publish APIs, analytics |
| Pipeline worker     | `pipeline_client/worker.py`                  | Cloud Run Job and local Docker entry point                       |
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
  -> Cloudflare deploy copies published JSON into the static site build
  -> public read from Cloudflare Pages static assets
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
| GET    | `/runs/{run_id}/diagnostics`                                | Export sanitized run diagnostics                  |
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
| POST   | `/payments/checkout`       | Create an allowlisted Stripe-hosted support checkout      |
| GET    | `/payments/session/{id}`   | Verify a returned Checkout session with Stripe            |
| POST   | `/payments/webhook`        | Receive signature-verified Stripe lifecycle events        |
| GET    | `/health`                  | Liveness                                                  |
| GET    | `/health/ready`            | Readiness                                                 |

The production Cloudflare workflow copies the current published files from GCS into `web/static/` before building.
Public SvelteKit pages therefore load the bundled `/{race_id}.json`, `/summaries.json`, and
`/chamber_forecasts.json` assets from Cloudflare Pages. `VITE_PUBLIC_DATA_URL` remains an optional mode for a future
dedicated public bucket or another public static origin; it is deliberately unset while drafts and published data
share one private bucket. FastAPI public read routes remain available as API fallbacks and operational interfaces.

Public page traffic is therefore measured with the Cloudflare Web Analytics browser beacon, not inferred from
`races-api` reads. The authenticated `/analytics/traffic` endpoint queries Cloudflare's GraphQL API and caches the
result for the admin dashboard. API request analytics remain separate and describe `races-api` health only.

## Public Web Surface

The public SvelteKit site separates product introduction from race discovery:

- `/` is the editorial homepage. It demonstrates the research experience, shows selected national-election content and editorial standards, and links into the ballot lookup and directory; it does not collect an address.
- `/my-ballot/` is the focused address lookup and in-page national-election result flow. It is prerendered for direct navigation but excluded from search indexing and the sitemap.
- `/elections/` is the browse and filtering surface for published election research. Current launch coverage includes supported U.S. House, U.S. Senate, presidential, and gubernatorial races.
- `/races/{slug}/` and its candidate and comparison subroutes remain the detailed research surfaces.
- `/about/` publishes the project's identity and research methodology; `/methodology/` redirects to that section. `/corrections/`, `/privacy/`, `/terms/`, and `/funding-and-editorial-independence/` publish the correction, privacy, legal, and editorial-independence statements.

Public race names are deterministic for the supported U.S. Senate, U.S. House, and governor families. Pipeline outputs
persist canonical titles via `shared/race_titles.py`; the web formatter in `web/src/lib/utils/raceTitle.ts` also
normalizes legacy published records at render time. Race H1s, cards, search results, forecast surfaces, social metadata,
and browser titles must use that formatter instead of displaying the model-supplied `title` field directly. URLs and
canonical links continue to use the stable race ID and do not change when title copy changes.
- `/support/` offers one-time and monthly support through Stripe-hosted Checkout when the server-side Stripe secrets are configured. `/partners/` remains an informational contact page and does not create financial commitments.

The `/my-ballot/` route provides a no-server-storage election lookup. When `VITE_GOOGLE_MAPS_API_KEY` is configured, a visitor can select a U.S. address suggestion supplied directly by Google Places; the optional integration uses debounced requests and one autocomplete session token per search. The completed address is sent directly from the browser to the U.S. Census Geocoder using its documented JSONP interface; the address is never sent to or stored by Smarter.Vote. Without Google configuration or if suggestions fail, visitors can enter the full address normally. The returned state and congressional district plus matched race IDs are retained in tab-scoped `sessionStorage` so results survive a refresh. The non-sensitive state and congressional district are also written as `state` and `district` URL parameters so a result can be bookmarked or shared without exposing the address; the current published catalog is matched again when that URL opens. Both the saved result and URL parameters are cleared when the visitor searches another address. Results transition in place on the focused route rather than returning to the homepage. The lookup is not a complete ballot and does not identify other state, local, judicial, or ballot-measure contests, so results link to VOTE411's personalized ballot guide for broader ballot information. There is no Smarter.Vote address endpoint or durable address persistence. Correction reports use public GitHub issues; other public inquiries currently use mail links rather than a server-side CRM or form-processing service.

Support checkout sends only an amount and one-time/monthly mode to `races-api`; card and billing details go directly to Stripe Checkout and never enter Smarter.Vote's frontend or API. The API derives success and cancellation routes from an exact allowlist of public/local origins, applies checkout rate limits, and keeps Stripe credentials server-side in Secret Manager. The return page verifies the opaque Checkout session ID with Stripe before displaying a confirmed state; the signed webhook endpoint handles lifecycle notifications separately. If Stripe secrets are absent, checkout fails closed with a service-unavailable response.

## Agent Phases

```text
DISCOVERY -> IMAGES -> ISSUES -> FINANCE -> REFINEMENT -> POLLING -> FORECAST -> VOTER_RESOURCES -> REVIEW -> ITERATION
```

Update/rerun mode adds roster and metadata synchronization before re-researching an existing race.

## Storage

| Storage                               | Production Use                                                               |
| ------------------------------------- | ---------------------------------------------------------------------------- |
| GCS `drafts/`                         | Agent output awaiting admin review                                           |
| GCS `races/`                          | Authoritative published race JSON and central `summaries.json` build input  |
| GCS `retired/`                        | Archived previous versions                                                   |
| Firestore `pipeline_queue`            | Durable work routing, leases, dispatch state, and terminal status            |
| Firestore `pipeline_runs`             | Run status, progress, and logs                                               |
| Firestore `races`                     | Race catalog metadata for admin listing/filtering, plus status and history   |
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
- Targeted update runs default to `baseline_source="latest"`, loading a draft before falling back to published data. Use
  `baseline_source="published"` when repairing the public version and an existing draft must be ignored. Continuation
  checkpoint payloads still take precedence, and `force_fresh=true` still disables all baseline loading.
- Prefer shared helpers for validation and summary shaping instead of duplicating logic.
