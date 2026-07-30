# Pipeline Operations Runbook

This is the canonical operator guide for running, monitoring, reviewing, costing,
and publishing SmarterVote race research. Architecture details live in
`docs/architecture.md`; deployment mechanics live in `docs/deployment-guide.md`.

## Non-Negotiable Rules

- Runs write drafts. They do not publish automatically.
- Review the complete draft and every warning/error before publishing.
- A passing numeric grade is not sufficient by itself. Publication rejects any
  unresolved warning-or-higher review flag, including deterministic link and
  profile-quality flags.
- Use the deployed `races-api` and GCS data as operational truth. Local files are
  fixtures unless a local-only direct run was explicitly requested.
- Preserve unrelated worktree changes. Do not reset a dirty tree to deploy.
- Record model/search cost and cloud compute separately, then report the combined
  total without double counting.

## Execution Paths

### Local Docker worker against the cloud queue

This is the preferred workstation path. It uses the same Firestore queue,
`AgentHandler`, storage, run records, and logs as Cloud Run, but claims only
items queued with `runner=local`.

```powershell
docker compose -f docker-compose.worker.yml up -d --build
docker compose -f docker-compose.worker.yml ps
docker compose -f docker-compose.worker.yml logs -f pipeline-worker
```

The worker reads credentials and configuration from the compose environment.
Confirm `ADMIN_API_KEY`, OpenRouter/search keys, GCP project/storage settings,
and application-default GCP credentials before assuming a pending item is stuck.

### Cloud Run Job

The production-shaped path is:

```text
races-api queue request
  -> Firestore pipeline_queue
  -> pipeline-job-{environment}, with QUEUE_ITEM_ID override
  -> pipeline_client.worker
  -> shared queue processor and AgentHandler
  -> Firestore pipeline_runs and logs
  -> GCS drafts/{race_id}.json
```

Queue with `runner=cloud_run`. The races API service account needs permission to
execute the job with overrides. The job and API must use matching, tested source
revisions. A successful dispatch is not a successful run; monitor the run record
to terminal status.

### Direct local development API

Use only for in-process debugging:

```powershell
python -m uvicorn pipeline_client.backend.main:app --host 0.0.0.0 --port 8001 --reload
```

Production admin behavior belongs in `services/races-api`, not this local API.

## Choosing a Run

The ordered steps are:

```text
discovery -> images -> issues -> finance -> refinement -> polling
  -> forecast -> voter_resources -> review -> iteration
```

Fetch the current step list from `/steps` or the `list_pipeline_steps` MCP tool
instead of hard-coding UI labels or weights.

### Fresh run

Use a fresh run for a new/bad race whose roster and full profile cannot be
trusted:

- `force_fresh=true`
- full ordered steps
- `baseline_source` is irrelevant when no baseline is used
- bound candidate count only when intentionally testing

Fresh runs should establish the roster from authoritative election sources
before researching candidates. Election returns and primary results are roster
evidence, never polling.

### Update run

Use an update when the existing race is generally good:

- default `baseline_source=latest` loads the draft first, then published data
- use `baseline_source=published` when an existing draft must be ignored
- when `enabled_steps` is omitted, the worker defaults to `discovery`,
  `images`, `finance`, `refinement`, `polling`, `forecast`, and
  `voter_resources`
- ordinary updates skip `issues`, `review`, and `iteration`; opt into them only
  when the correction goal justifies their cost
- explicit `enabled_steps` always override the update default
- pass `candidate_names` for candidate-specific repair
- use `review` after material issue or narrative changes and `iteration` only
  when model-assisted correction is appropriate

Update evidence is monotonic: ordinary updates merge source lists and preserve
existing citations. An obsolete URL must be removed explicitly. Confirmed HTTP
404/410 candidate sources are removed deterministically and tombstoned so
baseline restoration cannot reintroduce them.

### Economy versus quality models

`cheap_mode=true` is the default for routine and targeted work. It selects the
economy model profile but does not bypass review or quality gates. Set
`cheap_mode=false` only when intentionally using a non-economy profile. Model
overrides should be exceptional and recorded in the run note.

The largest update cost drivers are issue research across every
candidate/issue pair and repeated whole-profile review. A narrow research step
can still be expensive when the complete review packet is sent to three
reviewers before and after iteration. Prefer one well-specified targeted run
over a sequence of speculative reruns.

### Post-primary decision rule

Verify the general-election roster against official candidate lists or official
primary results before queueing:

- use fresh research when the profile mixes offices, retains primary losers,
  treats running mates as candidates, or otherwise has an untrustworthy roster
- pass a verified `candidate_names` list to constrain the repair
- use an update when the roster and issue record are usable but finance,
  polling, forecast, images, voter resources, or current metadata are aging
- election returns are roster evidence, never opinion polling
- keep both outputs as drafts until the roster and refreshed fields are
  reviewed

The admin Batch Queue dialog opens on the low-cost update preset. **All on**
restores the complete step set, **Update default** restores the maintenance
preset, and **Discovery only** isolates roster/metadata work. `force_fresh`
changes baseline loading but does not silently change an explicit step list.

## Queueing Through MCP

Common tools:

- `scan_catalog`: compact prioritized inventory with research tiers, coverage,
  traffic, freshness, and persisted asset-audit findings
- `plan_repairs`: non-mutating, independently queueable race/candidate repair
  groups with calibrated-or-static cost and search ceilings
- `audit_race_assets`: bounded source/photo URL and image-quality checks;
  `persist=true` stores the evidence on the catalog record
- `queue_races`: one or more races with full options
- `run_race`: one race
- `list_active_runs`, `get_queue`: queue/worker state
- `get_run`, `get_run_logs`: status and cursor-based logs
- `get_race_data(draft=true)`: inspect output
- `publish_race`, `publish_races`: publish only after approval
- `get_run_diagnostics`, `summarize_run_costs`: run health and exact cost
- `get_pipeline_metrics`, `get_pipeline_metrics_summary`: cost reporting

Queue each `repair_groups` item independently. The combined
`recommended_steps` and `candidate_names` fields are summaries, not a safe
queue payload when candidates need different work. Estimates use a 25% margin
over compatible observed per-phase spend, with the static missing-work estimate
as a floor.

Catalog health records strong contest-matched roster evidence, terminal and
sourced issue coverage, field-level freshness, finance/voting coverage,
forecast evidence lineage, and pipeline/validation health. Use
`audit_race_assets(..., persist=true)` when URL reachability, content type, or
thumbnail quality matters; presence alone is not treated as verification.

Logical runs enforce both global and phase search/token ceilings. They also cap
uncached page fetches and fetched characters, and persist per-phase
token/provider/search/page attribution across continuation handoffs. Defaults
are documented in `.env.example`.

Example targeted update:

```json
{
  "race_ids": ["ca-house-03-2026"],
  "runner": "local",
  "cheap_mode": true,
  "baseline_source": "latest",
  "candidate_names": ["Candidate One", "Candidate Two"],
  "enabled_steps": [
    "discovery",
    "images",
    "finance",
    "refinement",
    "polling",
    "forecast",
    "voter_resources"
  ],
  "goal": "Refresh time-sensitive non-issue fields while preserving the verified roster and issue evidence.",
  "note": "Low-cost post-primary maintenance update",
  "save_artifact": true
}
```

Example fresh cloud run:

```json
{
  "race_ids": ["state-house-00-2026"],
  "runner": "cloud_run",
  "cheap_mode": true,
  "force_fresh": true,
  "enabled_steps": [
    "discovery",
    "images",
    "issues",
    "finance",
    "refinement",
    "polling",
    "forecast",
    "voter_resources",
    "review",
    "iteration"
  ],
  "goal": "Build and validate a complete current profile.",
  "save_artifact": true
}
```

Use `debug_mode` for a small diagnostic run when investigating cost, retries,
handoffs, or context behavior. Debug mode increases observability, not quality,
and does not reduce cost.

## Monitoring

Track the returned `run_id`, not only the queue item ID.

1. Confirm the item moves from `pending` to `running`.
2. Inspect `current_step`, overall progress, step progress, and
   `progress_updated_at`.
3. Fetch logs with the opaque `next_cursor`; do not repeatedly download the
   entire log history.
4. Treat a long research/tool call as active when logs and progress timestamps
   continue moving.
5. On terminal status, inspect `completed_at`, error data, draft output, and
   `agent_metrics`.

Do not leave required command sessions or runs unobserved. A queue dispatch can
fail before job start; a worker can lose its lease; a job can complete without a
publishable draft.

For diagnostics, download
`GET /runs/{run_id}/diagnostics` or use **Export diagnostics** in the admin UI.
The sanitized `smartervote.pipeline-diagnostics.v1` bundle includes run, queue,
logs, timeline, catalog data, draft, and computed quality summary. It excludes
raw prompts, model responses, fetched page bodies, and secrets.

## Detailed Quality Review

Review the draft, not only run logs.

### Race and roster

- office, district, election date, and contest stage are correct
- candidate roster matches authoritative current-cycle sources
- incumbent status means the exact office being contested
- withdrawn, defeated, or prior-cycle candidates are absent

### Candidates and evidence

- every candidate has a supported summary
- all 12 canonical issues exist
- every substantive stance has at least one reliable source
- a documented absence uses the canonical no-public-position wording
- finance and voting/public-record narratives have their own sources
- source URLs belong to the correct candidate
- update source counts have not regressed unexpectedly

### Polling and forecast

- pollster is real and named, never `Example`, `Unknown`, or a placeholder
- election/primary results are not stored as polls
- matchup names match the roster exactly
- forecast poll count agrees with accepted polling
- years served are not confused with completed terms
- forecast rationale, winner, probabilities, margin, rating, and cited inputs
  are internally consistent

### Reviews

- all model reviewer verdicts and flags are examined
- automated link validator has no warning/error
- automated profile-quality validator has no warning/error
- `validation_grade.passed` is true
- grade is recomputed after deterministic validators

If any warning/error remains, do not publish. Repair the cause and rerun the
smallest sufficient steps.

## Publication

Publishing copies the approved draft into the published GCS race path, updates
the summaries index/catalog, and removes or supersedes draft state according to
the API implementation.

Before publish:

1. Fetch the final draft again.
2. Confirm candidate/source counts, forecast semantics, polling, reviews, and
   grade.
3. Confirm the run being reviewed is the latest run for that draft.
4. Record its costs.
5. Publish through `races-api`/MCP, never by manually copying JSON.

After publish:

1. Fetch with `draft=false`.
2. Confirm the published payload matches the approved draft.
3. Confirm the race is absent from unpublished-draft listings.
4. Verify the public/static-data path after the web deployment when applicable.

## Cost Accounting

The authoritative per-run model/search fields are under `agent_metrics`:

- `llm_cost_usd`: provider-reported model cost
- `search_cost_usd`: metered search cost
- `cost_usd`: combined provider model plus search cost
- `cost_source`: `provider` or `estimated`
- `estimated_usd`: catalog estimate for comparison/fallback
- prompt, completion, and total tokens
- `serper_calls`, model breakdown, duration, context, retry, and review metrics

Use `cost_usd` as the API total when present. Do not add `llm_cost_usd` and
`search_cost_usd` to it again. If `cost_usd` is absent, report the estimate and
label it estimated.

Cloud compute is separate. Obtain attributable Cloud Run/other GCP spend from
the billing export or `/pipeline/gcp-costs`; local worker compute is not a GCP
charge. Report:

```text
run API cost = agent_metrics.cost_usd
cloud infrastructure cost = attributable billed/estimated GCP compute
run all-in cost = API cost + cloud infrastructure cost
multi-run total = sum of each all-in cost
```

The metrics API reconciles `pipeline_metrics` with `pipeline_runs` by `run_id`
so recent runs are not hidden by a populated but stale cost collection. It
supports both top-level and payload-nested legacy `agent_metrics` layouts.

When comparing update versus fresh cost, include:

- enabled steps and candidate count
- total tokens and search calls
- number and models of review calls
- whether iteration caused a second full review packet
- runner and cloud compute
- failed/diagnostic attempts, reported separately from successful runs

Firestore cost is bounded independently of model/search cost:

- active log polling uses the opaque `next_cursor` and reads only newer logs
- routine progress writes are coalesced; step boundaries and terminal state
  still write immediately
- live and per-run log buffers are capped and long messages are truncated
- diagnostics exports read at most 2,000 log documents and report truncation
- retention defaults expire completed queue records, checkpoints, debug
  artifacts, and run logs instead of retaining them indefinitely

Do not poll from the beginning with numeric `since`, repeatedly stream full
collections, or enable debug capture for broad batches.

## Known Update-Run Optimization Opportunities

The low-cost step default removes the largest avoidable phases, but update
discovery can still spend multiple model iterations proving that a recent
baseline has not changed. Improvements should be implemented in this order:

1. Add deterministic staleness gates per field so a recent image, voter link,
   finance snapshot, or forecast can be skipped without an LLM call.
2. Check official roster/results feeds before invoking open-ended discovery;
   stop roster work early when the verified names and contest stage are
   unchanged.
3. Use source-specific deterministic adapters for FEC/state finance and polling
   catalogs, then ask the model only to interpret changed records.
4. Build a compact baseline delta packet instead of repeatedly sending the
   whole profile to metadata/refinement agents.
5. Persist per-step fingerprints, source access times, and no-change outcomes
   so subsequent runs can make explainable skip decisions.
6. Run review only for changed sections and only when a publication-quality
   decision needs it; retain the deterministic quality gate for all drafts.

Measure each improvement with debug diagnostics: wall time, iterations, model
calls, prompt/completion tokens, search calls, Firestore writes/reads, changed
fields, and quality findings. A cheaper no-op update is successful only if it
preserves roster correctness and evidence.

## Deployment and Runtime Verification

Normal deployment is CI/Terraform; see `docs/deployment-guide.md`. For an
explicit development hotfix, build immutable worker/API tags from the same
source state, push both, update the Cloud Run job/service, and record the
revision. Do not deploy a dirty tree accidentally.

Required verification:

```powershell
pytest -q
docker compose -f docker-compose.worker.yml up -d --build
docker compose -f docker-compose.worker.yml ps
```

Smoke-test the API image before deployment:

```powershell
docker run --rm <races-api-image> python -c "import main; import gcs_helpers"
```

After deployment:

- Cloud Run service routes 100% traffic to the intended revision
- Cloud Run job points at the intended worker image digest
- `/health` and `/health/ready` pass
- metrics endpoints return current runs and costs
- one bounded run succeeds through the intended runner

## Failure Recovery

### Pending local item

- verify the local worker container is running
- verify it was rebuilt from current source
- confirm the item has `runner=local`
- inspect worker logs and GCP credentials

### Cloud dispatch failure

- inspect queue `dispatch_status` and operation/error fields
- verify job name, region, image, and service-account permission to execute with
  overrides
- do not mark the run failed solely from an HTTP client timeout if a Cloud Run
  operation was created

### Stalled or expired run

- check lease and progress timestamps
- inspect cursor-based logs and Cloud Run execution state
- let the queue processor reclaim an expired lease when safe
- cancel only when the active execution is known not to be writing

### Bad draft

- keep it unpublished
- state the concrete blocking findings
- use `baseline_source=latest` for a targeted repair unless the bad draft itself
  must be ignored
- avoid repeating full discovery when only finance, sourcing, polling, forecast,
  or review needs repair

### Cost discrepancy

- compare draft `agent_metrics`, run document, and `pipeline_metrics` record by
  `run_id`
- check both legacy agent-metrics layouts
- verify `cost_usd` includes search before summing components
- distinguish API spend from GCP compute and from failed attempts
