# Pipeline Hardening Plan

Last reviewed: 2026-06-14.

## Objective

Make the research pipeline cheaper, bounded, deadline-aware, and scalable without weakening source attribution or RaceJSON validation.

This plan covers the research agent, Cloud Function orchestration, queue/run persistence, storage paths, logging, and configuration. It does not change the rule that agent output is saved as a draft and publishing remains an explicit admin action.

## Decisions

- Remove automatic post-run LLM analysis completely.
- Use the durable admin agent, MCP tools, and interactive coding agents for occasional diagnostics instead of sending every run's logs and artifact through another model.
- Keep the three-provider profile review available, but make its context and repetition configurable and prevent wasteful duplication.
- Use large context budgets by default so cheap long-context models can consume substantial source material when it improves research quality.
- Replace silent candidate deletion with explicit partitioning or deferred work.
- Treat `services/races-api`, `pipeline_queue`, `pipeline_runs`, and `races` as the production control plane.
- Keep local runner compatibility, but do not let local-only managers define production behavior.

## Delivery Order

1. Remove post-run analysis and close secret/log exposure.
2. Make LLM context large, intentional, measurable, and free of avoidable repetition; bound retries and run time.
3. Make candidate and issue processing scalable.
4. Fix queue correctness and consolidate state ownership.
5. Centralize paths, constants, model configuration, and retention.
6. Add load, cost, and regression tests.

Each phase should be delivered as a separate pull request where practical. Avoid combining queue migrations with prompt or model-loop changes.

## Phase 1: Remove Post-Run Analysis

### Problem

Every local runner completion can send up to 300,000 log characters, 100,000 artifact characters, and copies of the pipeline system prompts to another LLM. This duplicates cost, exposes operational data, and has already allowed provider error URLs containing API keys to enter local artifacts.

### Implementation

Delete:

- `run_post_run_analysis()` and `_MAX_LOG_CHARS` from `pipeline_client/agent/review.py`.
- `POST_RUN_ANALYSIS_SYSTEM` and `POST_RUN_ANALYSIS_USER` from `pipeline_client/agent/prompts.py`.
- `DEFAULT_POST_RUN_ANALYSIS_MODEL` and all `post_run_analysis` model roles from `pipeline_client/agent/model_registry.py`.
- `_run_and_save_post_analysis()` and its invocation from `pipeline_client/backend/pipeline_runner.py`.
- Writing `post_run_analysis` into draft RaceJSON.
- Creation of `post-analysis` artifacts and related log broadcasts.
- Tests, UI fields, documentation, and compatibility aliases that only support this feature.

Search the full repository for:

```text
post_run_analysis
post-analysis
POST_RUN_ANALYSIS
DEFAULT_POST_RUN_ANALYSIS_MODEL
```

Add a log sanitizer before persisting operational messages. At minimum, redact:

- Query parameters named `key`, `api_key`, `token`, `access_token`, or `secret`.
- Bearer tokens and common provider key formats.
- Authorization headers.

Apply sanitization before writing to Firestore, in-memory run history, artifacts, or callback logs. The sanitizer should live in one shared pipeline logging module.

Do not migrate old generated artifacts. They are ignored local runtime files. Rotate any exposed credentials and delete local files containing them.

### Acceptance Criteria

- A completed run makes no post-run LLM request.
- RaceJSON contains no `post_run_analysis` field.
- No post-analysis artifact is produced.
- Persisted exception messages redact credentials embedded in URLs.
- Existing research review and validation grading still work.

### Validation

```bash
rg -n "post_run_analysis|post-analysis|POST_RUN_ANALYSIS|DEFAULT_POST_RUN_ANALYSIS_MODEL" .
PYTHONPATH=. python -m pytest tests/test_run_agent.py tests/test_agent_loop.py tests/test_pipeline_metrics.py -v
```

Add deletion/regression tests if these paths change during implementation.

## Phase 2: Large, Efficient LLM Context

### Problem

`_agent_loop()` appends all assistant messages, search results, fetched pages, and tool responses to one conversation. The complete history is sent again on every iteration. Input-token use therefore grows roughly quadratically with the number and size of tool calls.

The goal is not to force the pipeline into small contexts. The selected models have large context windows and many are inexpensive enough that large research packets are desirable. Optimize duplicated, irrelevant, and stale context first. Truncation should be a final safety mechanism, not the primary cost-control strategy.

### Implementation

Introduce an `AgentContextBudget` configuration object with explicit limits:

```text
target_input_tokens
maximum_input_tokens
reserved_output_tokens
minimum_context_headroom
max_single_tool_result_tokens
max_search_results
max_retained_tool_turns
max_iterations
max_output_tokens
```

Here, "budget" means an intentional allocation of available context capacity, not a mandate to minimize token use. Defaults should be large.

Use per-model and per-phase defaults. Derive ceilings from the configured model's known context window rather than applying one small global cap.

Starting policy:

- Use approximately 60-80% of a model's context window as the normal input target.
- Reserve enough space for tool calls, reasoning, and the configured maximum output.
- Permit discovery, finance, refinement, and review to use very large contexts when the source material is relevant.
- Give image lookup and single-issue tasks smaller targets because their task scope is narrower, not solely to reduce cost.
- Make all limits configurable by model profile and role.
- Record actual context utilization so budgets can be raised when quality benefits.

Change `_agent_loop()` so it retains:

- The system prompt.
- The original user task.
- A compact structured research notebook.
- Relevant raw source excerpts while they fit comfortably within the model-specific context target.
- Recent tool exchanges needed for continuity.

After each tool round:

1. Normalize search results to title, URL, and a bounded snippet.
2. Extract relevant page sections before adding them to model context.
3. Deduplicate URLs and repeated text.
4. Move durable facts and citations into a structured notebook.
5. Remove exact duplicates and superseded responses.
6. Only compact or drop older raw excerpts when the next request would exceed the large model-specific target.

Do not use an extra LLM call solely for compaction. Start with deterministic compaction and structured records.

Replace character-only limits with token estimates where practical. A simple conservative estimator is sufficient initially, provided tests prove the configured ceiling and output reserve are respected.

Prefer these optimizations in order:

1. Remove duplicate tool schemas, repeated URLs, and repeated search results.
2. Remove stale or superseded turns.
3. Use compact structured serialization.
4. Keep the most relevant full source excerpts.
5. Summarize or truncate only when required to stay inside the model's actual context window.

Reduce tool schemas by phase. Do not send editing tools that the current phase cannot use. Keep `read_profile`, but remove or constrain its `full` mode:

- Add candidate-specific and field-specific reads.
- Set a generous model-aware output ceiling.
- Return compact JSON without indentation.
- Allow full-profile reads in broad phases when they fit the configured context target.
- Reject or scope full-profile reads in narrow phases only when they would crowd out the task's source material or exceed the model limit.

Change fetched page handling:

- Keep the cache copy at a reasonable extraction size.
- Return large, relevant phase-specific excerpts to the LLM.
- Prefer paragraphs containing candidate, issue, office, date, and policy terms.
- Include the source URL once instead of repeating it throughout the context.

### Acceptance Criteria

- Every model request has a generous, model-aware target and a hard maximum below the provider context limit.
- A ten-iteration tool loop does not grow input tokens quadratically.
- Full RaceJSON cannot be injected into a narrow issue phase accidentally.
- Search and fetch results remain source-attributed.
- Metrics report context utilization, deduplication, compaction, and truncation counts.
- Normal broad research phases can intentionally use large contexts without warnings or forced early truncation.

### Tests

- Simulate ten large fetch responses and assert request context remains below the model-aware hard maximum.
- Assert relevant excerpts are retained up to the configured large target.
- Assert duplicate and superseded tool turns are compacted or removed first.
- Assert source URLs survive compaction.
- Assert each phase receives only its allowed tools.
- Add a regression test for oversized `read_profile` output.

## Phase 3: OpenRouter Naming and Deadline-Aware Run Budgets

### Problem

The shared LLM helper is named `_call_openai()` even though runtime requests go through OpenRouter. This obscures provider ownership and makes future maintenance confusing. Separately, LLM retry sleeps can outlive the Cloud Function deadline. Deadline handoff checks cannot execute while the provider helper is sleeping or awaiting a long request.

### Implementation

Rename OpenRouter-specific symbols:

- `_call_openai()` to `_call_openrouter()`.
- `_get_openai_client()` to `_get_openrouter_client()`.
- `_openai_client` to `_openrouter_client`.
- `_openai_request_timeout_seconds()` to `_openrouter_request_timeout_seconds()`.

Update imports, tests, mocks, log messages, and compatibility re-exports. Do not retain an `_call_openai` alias unless an external supported integration requires it; repository tests are not a reason to preserve the misleading name.

Keep generic orchestration named around LLMs where provider details do not matter. For example, `_agent_loop()` can remain provider-neutral while its transport dependency is explicitly OpenRouter.

Create a shared `RunBudget` passed from `AgentHandler` through `run_agent()`, phase functions, `_agent_loop()`, and `_call_openrouter()`.

The run-time budget is different from the context budget:

- Context budgets should be large and should exploit available model windows.
- Run budgets prevent requests, retries, and sleeps from crossing the platform deadline.
- Cost budgets should default high or remain advisory for cheap model profiles unless an administrator explicitly sets a hard spending cap.

It should expose:

```text
deadline_at
remaining_seconds()
can_start_call(minimum_seconds)
bounded_timeout(requested_seconds)
bounded_sleep(requested_seconds)
```

Before every model call, search call, page fetch, review call, and retry sleep:

- Stop or hand off if insufficient time remains.
- Bound request timeout to the remaining run time minus a checkpoint buffer.
- Bound total retries by both count and elapsed time.

Replace the twelve-retry default with phase-configurable policies. Suggested starting values:

| Operation | Attempts | Maximum Total Wait |
|---|---:|---:|
| LLM 429 | 3 | 90 seconds |
| LLM 5xx/timeout | 3 | 60 seconds |
| Serper | 2 | 15 seconds |
| Page fetch | 2 direct plus one fallback | 30 seconds |

Use jittered exponential backoff. Respect `Retry-After` only up to the remaining budget.

Checkpoint at safe units:

- After discovery.
- After each candidate image.
- After each candidate/issue result.
- After finance.
- After each candidate refinement.
- Before review and between iteration cycles.

### Acceptance Criteria

- No retry or request timeout can exceed the remaining run budget.
- A run hands off with a valid checkpoint before the platform deadline.
- Continuations do not repeat completed candidate/issue work.
- Retry metrics distinguish rate limits, provider failures, and deadline exits.
- No active OpenRouter transport helper retains an OpenAI-specific name.

## Phase 4: Candidate and Issue Scalability

### Problem

The pipeline silently reduces races to eight candidates and processes candidate/issue work serially. This produces incomplete crowded-primary data and excessive wall-clock time.

### Implementation

Remove `_enforce_candidate_cap()` as a data-deletion step. Keep a configurable workload limit, but represent deferred candidates explicitly.

Preferred data flow:

1. Discovery records the complete authoritative active roster.
2. A work planner creates candidate batches.
3. Each batch researches candidates without removing others from RaceJSON.
4. Continuations process remaining batches.
5. Final review runs only after all required batches complete.

Do not add partial or placeholder candidate profiles to published output. Draft metadata should clearly indicate incomplete work:

```json
{
  "pipeline_state": {
    "complete": false,
    "remaining_candidates": ["..."],
    "remaining_steps": ["issues", "refinement"]
  }
}
```

If schema changes are required, update `shared/models.py` and `web/src/lib/types.ts` together.

Add bounded concurrency for independent issue research:

- Start with a semaphore of two to four concurrent candidate/issue jobs per worker.
- Keep mutation isolated: each job returns a patch rather than mutating shared RaceJSON.
- Merge patches deterministically in the orchestrator.
- Deduplicate searches and source fetches through the shared cache.
- Respect provider rate limits and the run budget.

Consider grouping low-information issues into one candidate call only after measuring quality. The first implementation should preserve one issue per task while gaining bounded concurrency and context limits.

### Acceptance Criteria

- A race with more than eight candidates preserves the complete roster.
- Work limits defer candidates instead of deleting them.
- Concurrent jobs cannot mutate shared dictionaries directly.
- Resume logic skips completed issue units.
- Tests cover at least 20 candidates and interrupted continuation.

## Phase 5: Review Duplication Control and Cost Visibility

### Problem

The full profile is sent independently to three reviewers and resent after each iteration cycle. Worst-case review cost scales with full artifact size, provider count, and cycle count.

### Implementation

Split deterministic validation from LLM review:

- Run schema validation, required-field checks, source counts, duplicate URL checks, stale-date checks, and link checks first.
- Build a compact review packet containing claims, citations, quality metrics, and detected concerns.
- Exclude operational metadata, logs, agent metrics, generator lists, previous reviews, and redundant fields.

Change review behavior:

- Default to one primary reviewer plus deterministic checks.
- Allow multi-provider review as an explicit quality profile.
- Re-review only fields changed during iteration.
- Stop after one iteration by default.
- Permit additional cycles only when error-severity findings remain.
- Do not re-run healthy provider reviews when another provider alone failed.

Store review configuration and cost in `agent_metrics`.

### Acceptance Criteria

- Default review sends one compact packet, not three full RaceJSON copies.
- Multi-provider review remains selectable.
- Iteration re-review is scoped to changed candidates/fields.
- Review stays below the model context limit and any explicitly configured hard dollar cap.
- Default cheap-model profiles use generous review context and advisory cost reporting rather than restrictive low budgets.
- Validation grade behavior remains deterministic when reviewers are unavailable.

## Phase 6: Queue Correctness and Firestore Scalability

### Problem

Queue operations derive state by listing up to 500 unordered race records. This becomes incorrect when the collection grows and is vulnerable to concurrent workers claiming the same work.

### Implementation

Use `pipeline_queue` as the sole production queue.

Claim work transactionally:

1. Query `status == "pending"` ordered by `created_at` or explicit priority.
2. In a Firestore transaction, verify the item is still pending.
3. Set `status = "running"`, `lease_owner`, and `lease_expires_at`.
4. Renew the lease while processing.
5. Permit recovery only after lease expiry.

Add the required composite indexes through Terraform.

Replace collection scans:

- `has_running()` becomes a limited query for `status == "running"`.
- Queue counts use Firestore count aggregation where available.
- Race listing uses cursors and pagination.
- Active run listing queries statuses directly.
- Artifact and cache listing APIs use pagination rather than materializing all objects.

Remove queue position derived from `list_races(500)`. Use creation time, explicit priority, or a transactionally assigned sequence.

### Acceptance Criteria

- Two workers cannot claim the same queue item.
- Queue behavior remains correct with more than 1,000 races and queue documents.
- All list APIs are paginated or explicitly bounded.
- Interrupted workers recover through lease expiry rather than marking every running item failed at process startup.

## Phase 7: Consolidate Ownership and Remove Legacy Paths

### Problem

`QueueManager`, `RaceManager`, `RunManager`, direct Firestore calls, the production API, and the local runner overlap in responsibility. Comments and implementations disagree about which collection is authoritative.

### Target Ownership

| Concern | Production Owner |
|---|---|
| Queue creation/cancel/list | `services/races-api` |
| Queue claim and continuation | `functions/agent` plus shared queue repository |
| Run status/progress/log metadata | shared pipeline run repository |
| Race metadata | shared race repository |
| Draft/published JSON | shared GCS repository |
| Local debug orchestration | `pipeline_client/backend` adapters |

### Implementation

- Introduce repository interfaces for queue, run, race, and object storage.
- Implement Firestore/GCS production repositories and local filesystem/in-memory adapters.
- Make `AgentHandler` depend on these interfaces rather than importing global managers.
- Remove `pipeline_client/backend/queue_manager.py` if it is no longer used by supported local workflows.
- Collapse duplicate run persistence between `RunManager`, `RaceManager` run subcollections, and `FirestoreLogger`.
- Update `docs/architecture.md` when ownership is finalized.

Do this after transactional queue work, not before.

### Acceptance Criteria

- Each production entity has one authoritative store and one repository implementation.
- No production path imports local-only queue state.
- Comments, architecture docs, and code agree about collection ownership.
- Local tests can inject fake repositories without environment-variable patching.

## Phase 8: Centralize Paths and Storage Names

### Problem

Paths are built from the current working directory, different `parents[n]` calculations, and repeated literal prefixes. This makes local behavior dependent on launch location.

### Implementation

Create a shared configuration module with:

```text
repo_root
data_dir
drafts_dir
published_dir
retired_dir
artifacts_dir
cache_dir
metrics_db_path
local_queue_path
```

All defaults must resolve from a single known root, not the current working directory.

Centralize cloud names:

```text
GCS_DRAFTS_PREFIX
GCS_RACES_PREFIX
GCS_RETIRED_PREFIX
GCS_ARTIFACTS_PREFIX
GCS_CHECKPOINTS_PREFIX
FIRESTORE_QUEUE_COLLECTION
FIRESTORE_RUNS_COLLECTION
FIRESTORE_RACES_COLLECTION
FIRESTORE_SEARCH_CACHE_COLLECTION
FIRESTORE_PAGE_CACHE_COLLECTION
```

Use typed settings and validators:

- `storage_mode` as a literal or enum.
- Absolute resolved local paths.
- Required bucket/project values in cloud mode.
- No module-import directory creation except through application startup.

### Acceptance Criteria

- Running from the repository root or `pipeline_client/` uses the same files.
- Tests can override all paths with a temporary directory.
- GCS prefixes and Firestore collection names are not repeated across modules.

## Phase 9: Centralize Magic Values and Validate Options

### Implementation

Create typed configuration for:

- Phase iteration and output limits.
- Context budgets.
- HTTP timeouts and concurrency.
- Cache TTLs.
- Review thresholds and cycle limits.
- Freshness thresholds.
- Log and artifact retention.
- Model roles and pricing.

Derive issue counts from `CanonicalIssue`; remove `/12` and similar literals.

Use shared enums/constants for:

- Pipeline steps.
- Review providers.
- Model profiles.
- Run and race statuses.
- Source types.

Validate:

- `max_candidates >= 1` when provided.
- Model override keys are known roles.
- Enabled steps are dependency-valid.
- Review provider lists are non-empty when review is enabled.
- Concurrency and budget settings have safe upper bounds.
- Model context-window metadata and default utilization targets.

Model prices and availability change frequently. Keep estimates in one configuration source and treat provider-reported cost as authoritative when present.

### Acceptance Criteria

- Invalid zero or negative candidate limits fail validation.
- Adding a canonical issue does not require editing progress log denominators.
- Model/profile/provider names have one canonical definition.
- Threshold changes do not require edits across unrelated modules.

## Phase 10: Logging, Artifact, and Cache Retention

### Problem

Active logs grow without a cap, each line can become a Firestore document, and artifacts duplicate output and logs. Cache collections also rely on manual cleanup.

### Implementation

- Keep a bounded in-memory ring buffer for live logs.
- Batch Firestore log writes or store chunked log documents.
- Define maximum message size and truncate after sanitization.
- Do not embed `agent_logs` inside the main artifact.
- Store artifact references instead of duplicating RaceJSON where possible.
- Configure Firestore TTL policies for logs, queue history, page cache, and search cache.
- Configure GCS lifecycle policies for artifacts and checkpoints.
- Keep published and retired race data under separate retention rules.
- Add structured counters for dropped/truncated logs.

Suggested retention starting point:

| Data | Retention |
|---|---:|
| Live run logs | 30 days |
| Completed queue items | 14 days |
| Debug artifacts | 30 days |
| Continuation checkpoints | 7 days |
| Search cache | 7 days |
| Page cache | 24 hours |
| Published/retired RaceJSON | Product policy, no automatic short TTL |

### Acceptance Criteria

- A noisy run cannot grow process memory without bound.
- A run does not create thousands of synchronous Firestore writes.
- Old operational data expires automatically.
- Secrets are sanitized before all persistence paths.

## Phase 11: Tests and Observability

Add metrics per phase:

```text
llm_calls
input_tokens
output_tokens
tool_calls
search_calls
cache_hits
fetched_chars
context_chars_sent
context_window_tokens
context_utilization_pct
context_compactions
retries_by_reason
deadline_handoffs
candidate_issue_units_completed
review_calls
```

Add budget alerts for:

- Tokens per candidate.
- Cost per race and per candidate.
- Context utilization by phase and model.
- Duration per phase.
- Cache hit rate.
- Retry rate.
- Continuation count.
- Truncated context or logs.

Required test scenarios:

1. Twenty-candidate primary.
2. Ten large tool responses in one agent loop.
3. Provider 429 and 5xx responses near deadline.
4. Worker interruption and continuation.
5. Two workers attempting to claim one queue item.
6. More than 1,000 race and queue records.
7. Review provider unavailable.
8. Malformed or oversized tool output.
9. Credential-bearing exception URL.
10. Execution from multiple working directories.

Run the focused suite after each phase and the full suite before merging:

```bash
PYTHONPATH=. python -m pytest tests/test_run_agent.py tests/test_agent_loop.py tests/test_pipeline_metrics.py -v
PYTHONPATH=. python -m pytest
```

## Completion Checklist

- [ ] Automatic post-run LLM analysis removed.
- [ ] Shared log sanitizer covers every persistence path.
- [ ] LLM requests use generous model-aware context targets and avoid repeated history.
- [ ] OpenRouter transport helpers use OpenRouter-specific names.
- [ ] Retries and timeouts respect a shared run deadline.
- [ ] Candidate rosters are never silently truncated.
- [ ] Candidate/issue work uses bounded concurrency and patch merging.
- [ ] Review uses generous context, avoids duplicate full-profile sends, and reports cost clearly.
- [ ] Queue claims are transactional and lease-based.
- [ ] Firestore and GCS list operations are paginated.
- [ ] Queue/run/race/storage ownership is consolidated.
- [ ] Paths and cloud collection/prefix names are centralized.
- [ ] Magic thresholds and provider names use typed configuration.
- [ ] Logs, artifacts, checkpoints, and caches have retention policies.
- [ ] Load, deadline, security, and cost regression tests pass.

## Non-Goals and Guardrails

These items are explicitly excluded to prevent the hardening work from changing product policy or expanding into unrelated migrations. Exclusion does not imply that they are desirable future work.

- **Do not change the twelve canonical issue names.** They are part of the shared data contract. This plan may remove hard-coded issue counts, but it must preserve the current issue taxonomy.
- **Do not automatically publish agent output.** Draft-first review and explicit admin publishing are required safety and product controls.
- **Do not replace OpenRouter or Serper as part of this work.** Provider replacement would be a separate migration. This plan may improve provider abstractions, naming, retries, and configuration.
- **Do not redesign the public RaceJSON presentation.** Internal pipeline-state fields may be added if needed, but public UI and presentation redesign are separate product work.
- **Do not use an LLM to summarize routine run logs.** Automated post-run analysis is being removed intentionally. Agents and MCP tools can inspect logs on demand when diagnosis is needed.
