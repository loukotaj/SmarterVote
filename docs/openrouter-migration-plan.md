# OpenRouter Migration Plan

## Summary

Move SmarterVote's LLM calls toward OpenRouter as the default single provider while preserving a temporary direct OpenAI path so existing OpenAI credits can be used up. The migration should keep the current model families available, improve model selection beyond the current `cheap_mode` toggle, and update every run kickoff path so options behave consistently.

Admin redesign work is intentionally out of scope for this plan. UI changes here are limited to the model/provider controls needed for the migration.

## Goals

- Use OpenRouter as the default provider for GPT, Claude, Gemini, and Grok-style model choices.
- Keep direct OpenAI available for research/generation while OpenAI credits remain.
- Replace the current binary cheap/full mental model with clearer model profiles.
- Keep existing queued runs, old option payloads, tests, and stored metrics backward compatible.
- Centralize model IDs, aliases, pricing metadata, and defaults so the frontend and backend stop drifting.

## Current State

- Research and tool-calling phases use `pipeline_client/agent/llm.py`, hardwired to OpenAI Chat Completions and `OPENAI_API_KEY`.
- Reviews use provider-specific clients in `pipeline_client/agent/review.py`:
  - Anthropic via `ANTHROPIC_API_KEY`
  - Gemini via `GEMINI_API_KEY`
  - Grok via `XAI_API_KEY`
- Model constants and pricing live in `pipeline_client/agent/cost.py`.
- Run options are duplicated across:
  - `pipeline_client/backend/models.py`
  - `services/races-api/request_models.py`
  - `web/src/lib/types.ts`
- Run kickoff paths include:
  - `POST /api/races/{race_id}/run`
  - `POST /api/races/queue`
  - Admin chat `queue_run` actions
  - Cloud Function queue execution
  - Local pipeline runner/debug APIs
  - CLI entrypoint `pipeline_client/agent/__main__.py`

## Provider Strategy

Add `llm_provider` to run options:

```ts
type LlmProvider = "openrouter" | "openai-direct";
```

Default provider:

- `openrouter`

Provider behavior:

- `openrouter`
  - Uses `OPENROUTER_API_KEY`.
  - Uses OpenRouter model slugs for all research, review, iteration, and post-run analysis calls.
  - Replaces native Anthropic/Gemini/xAI clients for review calls.
- `openai-direct`
  - Uses `OPENAI_API_KEY`.
  - Supports OpenAI-compatible research, issue subagents, refinement, iteration, and post-run analysis.
  - Cannot directly call Claude/Gemini/Grok reviewers.
  - If reviewers are enabled, non-OpenAI reviewers should still route through OpenRouter when `OPENROUTER_API_KEY` is set.
  - If OpenRouter is not configured and non-OpenAI reviewers are requested, skip those reviewers with a clear log message.

Environment variables:

- Add `OPENROUTER_API_KEY`.
- Keep `OPENAI_API_KEY` for `openai-direct`.
- Deprecate `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, and `XAI_API_KEY` for this pipeline once OpenRouter review routing is live.

## Model Profiles

Add `model_profile` to run options:

```ts
type ModelProfile = "economy" | "balanced" | "quality" | "custom";
```

Recommended defaults:

| Profile | Primary research | Small/subagent | Review defaults |
| --- | --- | --- | --- |
| `economy` | `openai/gpt-5.4-mini` | `openai/gpt-5.4-mini` | Claude Haiku, Gemini Flash Lite, Grok Fast |
| `balanced` | `openai/gpt-5.4` | `openai/gpt-5.4-mini` | Claude Haiku, Gemini Flash Lite, Grok Fast |
| `quality` | `openai/gpt-5.4` | `openai/gpt-5.4` | Claude Sonnet, Gemini Pro, Grok reasoning |
| `custom` | Explicit override | Explicit override | Explicit overrides |

Important cheap-mode fix:

- Do not default issue subagents to nano in economy mode.
- Keep nano available as an advanced override only.

OpenRouter model slug mapping:

| Existing model | OpenRouter model |
| --- | --- |
| `gpt-5.4` | `openai/gpt-5.4` |
| `gpt-5.4-mini` | `openai/gpt-5.4-mini` |
| `gpt-5-nano` | `openai/gpt-5-nano` |
| `claude-sonnet-4-6` | `anthropic/claude-sonnet-4.6` |
| `claude-haiku-4-5-20251001` | `anthropic/claude-haiku-4.5` |
| `gemini-3.1-pro-preview` | `google/gemini-3.1-pro-preview` |
| `gemini-3.1-flash-lite-preview` | `google/gemini-3.1-flash-lite-preview` |
| `grok-4.20-0309-reasoning` | `x-ai/grok-4.20` |
| `grok-4-1-fast-non-reasoning` | `x-ai/grok-4.1-fast` |
| `grok-3-mini` | `x-ai/grok-3-mini` |

## Run Options Contract

Add new fields:

```ts
interface RunOptions {
  llm_provider?: "openrouter" | "openai-direct";
  model_profile?: "economy" | "balanced" | "quality" | "custom";
  model_overrides?: {
    primary?: string;
    small?: string;
    review_claude?: string;
    review_gemini?: string;
    review_grok?: string;
    post_run_analysis?: string;
  };
}
```

Keep legacy fields:

- `cheap_mode`
- `research_model`
- `claude_model`
- `gemini_model`
- `grok_model`

Compatibility rules:

- If `model_profile` is present, it wins over `cheap_mode`.
- If `model_profile` is absent:
  - `cheap_mode=true` maps to `economy`.
  - `cheap_mode=false` maps to `quality`.
  - Missing `cheap_mode` maps to `balanced` for new UI-created runs after migration.
- Legacy per-model fields map into `model_overrides`.
- Explicit model overrides always win over profile defaults.
- Store both normalized resolved models and original options in run metadata where possible.

## Backend Implementation

1. Add a model registry module.
   - Suggested path: `pipeline_client/agent/model_registry.py`.
   - Owns model aliases, profile defaults, provider compatibility, labels, and pricing metadata.
   - Exposes helpers such as `resolve_run_models(options)` and `normalize_model_id(model)`.

2. Add a provider-neutral chat wrapper.
   - Suggested path: `pipeline_client/agent/llm_client.py`.
   - Supports:
     - OpenRouter via `AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")`.
     - Direct OpenAI via normal `AsyncOpenAI(api_key=OPENAI_API_KEY)`.
   - Preserves existing retry behavior, usage accumulation, max token handling, tool calls, and policy/bad request logging.

3. Update research calls.
   - Replace `_call_openai` usage with provider-neutral `call_chat`.
   - Keep `_call_openai` as a compatibility alias only if tests or imports require it.
   - Ensure tool-calling models resolve only to models marked as tool-capable.

4. Update review calls.
   - Replace `_call_anthropic`, `_call_gemini`, and `_call_grok` native SDK calls with provider-neutral calls.
   - Keep reviewer identity labels (`claude`, `gemini`, `grok`) as roles, not API providers.
   - Review availability should depend on resolved model + configured provider keys, not old provider-specific env vars.

5. Update post-run analysis.
   - Route through the same provider-neutral wrapper.
   - Default to a profile-appropriate Gemini/OpenRouter model for OpenRouter runs.
   - Use direct OpenAI when `llm_provider="openai-direct"` unless overridden.

6. Update metrics and cost.
   - Move pricing to the model registry or keep `cost.py` but key it by canonical model IDs.
   - Preserve existing cost estimates for old published model IDs via alias lookup.
   - Add `llm_provider` and `model_profile` to recorded metrics.
   - Keep old cheap/full summaries readable until old metrics age out.

7. Update queue/run option models.
   - Keep `pipeline_client/backend/models.py` and `services/races-api/request_models.py` in sync.
   - Add validators for new enum-like fields.
   - Do not reject legacy model IDs; normalize them during execution.

## Frontend Implementation

Keep this targeted. Do not redesign the admin IA in this migration.

1. Update `web/src/lib/config/pipelineOptions.ts`.
   - Replace static `RESEARCH_MODELS` / `REVIEWER_DEFS` as the primary UX with:
     - provider options
     - profile options
     - advanced override options
   - Keep model dropdown data for advanced/custom mode.

2. Add a shared run options builder.
   - Suggested path: `web/src/lib/config/runOptions.ts`.
   - Used by every run kickoff surface.
   - Converts UI state into the new `RunOptions` shape.
   - Includes legacy fields only if needed for backward compatibility.

3. Update every run kickoff surface.
   - `RacePanel.svelte`
   - `BatchQueueModal.svelte`
   - `AdminChatTab.svelte`
   - Any local/debug pipeline controls that still create runs
   - `PipelineApiService.queueRaces`
   - `PipelineApiService.runRace`

4. UI behavior.
   - Primary controls:
     - Provider: OpenRouter / Direct OpenAI
     - Profile: Economy / Balanced / Quality / Custom
   - Advanced controls:
     - Primary model
     - Small/subagent model
     - Reviewer models
     - Post-run analysis model
   - Show a warning when `openai-direct` is selected:
     - Claude/Gemini/Grok reviewers require OpenRouter and will be skipped if OpenRouter is not configured.

5. Display updates.
   - Run history should show profile and provider instead of `mini` / `full`.
   - Run detail should show resolved models and token/cost breakdown by canonical model ID.
   - Dashboard metrics should read both old cheap/full and new profile/provider metrics.

## Rollout Plan

1. Add registry, option types, and tests without changing runtime behavior.
2. Add OpenRouter wrapper and migrate review calls first.
3. Migrate research/tool calls to provider-neutral wrapper with `openai-direct` as the default internally.
4. Flip default provider for new runs to OpenRouter once tests pass.
5. Update frontend controls and all run kickoff surfaces.
6. Remove native Anthropic/Gemini/xAI dependencies after OpenRouter review path is stable.
7. Keep direct OpenAI support until credits are exhausted, then optionally remove it or hide it behind advanced settings.

## Test Plan

Backend tests:

- Profile resolution:
  - no options -> `balanced`
  - `cheap_mode=true` -> `economy`
  - `cheap_mode=false` -> `quality`
  - explicit `model_profile` wins over `cheap_mode`
  - explicit overrides win over profile defaults
- Model alias normalization for all current model IDs.
- OpenRouter chat wrapper sends OpenRouter slugs and records token usage.
- Direct OpenAI wrapper sends OpenAI slugs and records token usage.
- Review execution skips unavailable provider paths cleanly.
- Queue and run endpoints accept new options and preserve them in Firestore queue documents.
- Cloud Function queue execution resolves options correctly.

Frontend tests:

- Shared run options builder emits correct payloads for provider/profile/custom combinations.
- Race single-run, batch queue, and admin chat confirmation all use the same payload shape.
- Existing cheap/full payloads still display correctly in run history.
- Provider/profile labels render in run rows and details.

Manual verification:

- Run one race with OpenRouter economy.
- Run one race with OpenRouter quality and reviewers enabled.
- Run one race with direct OpenAI and reviewers disabled.
- Run one race with direct OpenAI and reviewers enabled while OpenRouter is configured.
- Confirm `generator`, `reviews[].model`, and `agent_metrics.model_breakdown` use expected canonical IDs.

## Open Questions

- Whether `balanced` or `economy` should be the default for new UI-created runs. This plan recommends `balanced` for quality and keeps `economy` available for bulk/low-priority work.
- Whether to expose OpenRouter provider routing preferences in v1. This plan leaves routing preferences in OpenRouter account settings.
- Whether to fetch OpenRouter model metadata dynamically. This plan starts with a static registry and can add metadata refresh later.
