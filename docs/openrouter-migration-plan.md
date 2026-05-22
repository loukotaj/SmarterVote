# OpenRouter Migration

SmarterVote now uses OpenRouter as the single runtime LLM provider for research, review, admin chat, and post-run analysis.

The migration keeps the model families the admin UI already exposed, but all runtime calls use OpenRouter model slugs and a single secret: `OPENROUTER_API_KEY`.

## Runtime Contract

- Required agent secret: `OPENROUTER_API_KEY`
- Required search secret: `SERPER_API_KEY`
- OpenRouter endpoint: `https://openrouter.ai/api/v1`
- Python client: OpenAI SDK `AsyncOpenAI` with OpenRouter `base_url`
- Deployment secret name: `openrouter-api-key-{env}`
- GitHub Actions secret: `OPENROUTER_API_KEY`

Direct provider API keys are no longer used by the agent pipeline.

## Model Registry

The model catalog, pricing estimates, legacy aliases, and profile defaults live in:

```text
pipeline_client/agent/model_registry.py
```

Current defaults:

| Profile | Primary research | Small/subagent | Review defaults |
| --- | --- | --- | --- |
| `economy` | `openai/gpt-5.4-mini` | `openai/gpt-5.4-mini` | Claude Haiku, Gemini Flash Lite, Grok 4.3 |
| `balanced` | `openai/gpt-5.4` | `openai/gpt-5.4-mini` | Claude Haiku, Gemini Flash Lite, Grok 4.3 |
| `quality` | `openai/gpt-5.4` | `openai/gpt-5.4` | Claude Sonnet, Gemini Pro, Grok 4.20 |
| `custom` | Balanced default unless overridden | Balanced default unless overridden | Balanced default unless overridden |

Nano remains available as an explicit advanced override, but economy mode no longer defaults issue subagents to nano.

## Run Options

Run kickoff surfaces may send:

```ts
interface RunOptions {
  cheap_mode?: boolean;
  model_profile?: "economy" | "balanced" | "quality" | "custom";
  model_overrides?: {
    primary?: string;
    small?: string;
    review_claude?: string;
    review_gemini?: string;
    review_grok?: string;
    post_run_analysis?: string;
  };
  research_model?: string;
  claude_model?: string;
  gemini_model?: string;
  grok_model?: string;
  review_providers?: ("claude" | "gemini" | "grok")[];
}
```

Compatibility rules:

- `model_profile` wins over `cheap_mode`.
- Without `model_profile`, `cheap_mode=true` maps to `economy`.
- Without `model_profile`, `cheap_mode=false` maps to `quality`.
- Without either field, backend defaults map to `balanced` in the model registry.
- Legacy per-model fields are normalized to OpenRouter slugs at execution time.
- Explicit overrides win over profile defaults.
- `review_providers` controls which review roles run when the review step is enabled.

## Legacy Alias Mapping

| Legacy model | OpenRouter model |
| --- | --- |
| `gpt-5.4` | `openai/gpt-5.4` |
| `gpt-5.4-mini` | `openai/gpt-5.4-mini` |
| `gpt-5-nano` | `openai/gpt-5-nano` |
| `claude-sonnet-4-6` | `anthropic/claude-sonnet-4.6` |
| `claude-haiku-4-5-20251001` | `anthropic/claude-haiku-4.5` |
| `claude-3-5-sonnet-20241022` | `anthropic/claude-sonnet-4.6` |
| `claude-3-haiku-20240307` | `anthropic/claude-haiku-4.5` |
| `gemini-3.1-pro-preview` | `google/gemini-3.1-pro-preview` |
| `gemini-3.1-flash-lite-preview` | `google/gemini-3.1-flash-lite-preview` |
| `gemini-3-flash-preview` | `google/gemini-3-flash-preview` |
| `grok-4.20-0309-reasoning` | `x-ai/grok-4.20` |
| `grok-4-1-fast-non-reasoning` | `x-ai/grok-4.3` |
| `grok-3-mini` | `x-ai/grok-4.3` |

## Updated Run Kickoff Paths

The OpenRouter option contract is accepted and preserved through:

- `POST /api/races/{race_id}/run`
- `POST /api/races/queue`
- Admin chat `queue_run` actions
- Firestore queue documents
- Cloud Function queue execution
- Local pipeline dev API
- Direct agent entrypoint

Frontend kickoff surfaces use the same option shape:

- `RacePanel.svelte`
- `BatchQueueModal.svelte`
- `AdminChatTab.svelte`
- `PipelineApiService.runRace`
- `PipelineApiService.queueRaces`

## Deployment

Terraform creates and grants access to:

```text
openrouter-api-key-{env}
```

The GitHub deploy workflow requires `OPENROUTER_API_KEY` and syncs it into Secret Manager before Terraform deploys Cloud Run or the agent Cloud Function.

For local Terraform:

```hcl
openrouter_api_key = "sk-or-your-openrouter-key"
serper_api_key     = "your-serper-key"
```

## Verification

Use these checks after changes to model wiring or deployment config:

```powershell
python -m pytest -q

cd web
npm run check
npm run test:unit -- --run

cd ..\infra
terraform validate
```

The configured model IDs should also be checked against OpenRouter's model list:

```powershell
@'
import json, urllib.request
from pipeline_client.agent.model_registry import MODEL_CATALOG
with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=20) as resp:
    data = json.load(resp)["data"]
available = {m["id"] for m in data} | {m.get("canonical_slug") for m in data if m.get("canonical_slug")}
print(sorted(set(MODEL_CATALOG) - available))
'@ | python -
```

Expected output:

```text
[]
```
