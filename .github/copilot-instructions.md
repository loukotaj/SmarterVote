# SmarterVote — Copilot Instructions

## What This Repository Does

SmarterVote is an AI-powered electoral analysis platform. A multi-phase research agent (OpenAI + Serper web search) produces structured candidate profiles (RaceJSON v0.3) covering 12 canonical issues with confidence scoring and source attribution. A SvelteKit frontend displays the data served by a FastAPI races-api.

## Languages & Runtimes

- **Python 3.10+** — backend, agent pipeline, API services
- **TypeScript / Svelte 4 / SvelteKit** — frontend (Node.js 22+)
- **Terraform 1.5+** — GCP infrastructure

## Project Layout

```
pipeline_v2/          # AI research agent (agent.py, prompts.py, search_cache.py)
pipeline_client/      # FastAPI backend that runs the agent (backend/main.py, handlers/)
services/races-api/   # REST API serving published race JSON
web/                  # SvelteKit frontend (static site, GitHub Pages)
shared/               # Pydantic models shared across Python components (models.py)
infra/                # Terraform for GCP (Cloud Run, Pub/Sub, Secret Manager)
tests/                # Python integration tests for the pipeline
data/published/       # Output RaceJSON files
data/cache/           # SQLite search cache
docs/                 # Architecture, deployment, local-dev guides
```

### Key Files

| Purpose | Path |
|---------|------|
| Agent loop + caching | `pipeline_v2/agent.py` |
| Prompt templates | `pipeline_v2/prompts.py` |
| Search cache (SQLite) | `pipeline_v2/search_cache.py` |
| Agent run handler | `pipeline_client/backend/handlers/v2_agent.py` |
| Pipeline API endpoints | `pipeline_client/backend/main.py` |
| Pydantic models (v0.3) | `shared/models.py` |
| TypeScript types | `web/src/lib/types.ts` |
| CI workflow | `.github/workflows/ci.yaml` |

## Build, Test & Lint Commands

### Python — Pipeline & APIs

```bash
# Install dependencies (from repo root)
pip install -r pipeline_client/backend/requirements.txt
pip install pytest pytest-asyncio httpx

# Run pipeline tests (always set PYTHONPATH)
PYTHONPATH=. python -m pytest tests/test_pipeline_v2.py -v

# Run races-api tests
cd services/races-api
pip install -r requirements.txt -r test-requirements.txt
PYTHONPATH=../.. python -m pytest test_races_api.py -v

# Format (Black + isort, line-length 127)
black --line-length 127 --target-version py310 <file>
isort --profile black --line-length 127 <file>
```

### Web — SvelteKit Frontend

```bash
cd web
npm ci               # install deps (always run before build)
npm run build        # production build (vite build)
npm run test:unit    # vitest
npm run check        # svelte-check + TypeScript
npm run lint         # prettier + eslint
```

### Terraform

```bash
cd infra
terraform fmt -check -recursive
terraform init -backend=false && terraform validate
```

## CI Checks (`.github/workflows/ci.yaml`)

Every PR to `main` runs these jobs — all must pass:

1. **test-pipeline** — `PYTHONPATH=. python -m pytest tests/test_pipeline_v2.py -v`
2. **test-apis** — races-api pytest
3. **test-web** — `npm run build` then `npm run test:unit`
4. **terraform-validate** — `terraform fmt -check` and `terraform validate`

## Coding Conventions

### Python

- **Black** (line-length 127, target py310) + **isort** (profile "black")
- Pydantic v2 — use `model_dump()` / `model_validate()`, not deprecated v1 methods
- Async where applicable; structured logging with module-level loggers
- Pre-commit hooks: trailing-whitespace, end-of-file-fixer, check-yaml, check-toml

### TypeScript / Svelte

- Types in `web/src/lib/types.ts` must mirror Python models in `shared/models.py`
- Components in `web/src/lib/components/`; routes use `+page.svelte`
- Prettier + ESLint for formatting; TailwindCSS for styling

## Architecture Notes

- **Agent phases**: DISCOVER → RESEARCH (×6 issue groups) → REFINE (8 LLM calls total)
- **12 Canonical Issues**: Healthcare, Economy, Climate/Energy, Reproductive Rights, Immigration, Guns & Safety, Foreign Policy, Social Justice, Education, Tech & AI, Election Reform, Local Issues — defined in `shared/models.py` (`CanonicalIssue` enum) and `pipeline_v2/prompts.py`
- **Search caching**: SQLite with 7-day TTL (`pipeline_v2/search_cache.py`)
- **Storage backends**: `LocalStorageBackend` (default) and `GCPStorageBackend`
- **Required API keys**: `OPENAI_API_KEY`, `SERPER_API_KEY` (see `.env.example`)
- **Optional review**: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` for multi-LLM review

## Important Rules

1. Keep the 12 canonical issues consistent across all outputs.
2. Preserve confidence scoring and source attribution in any data changes.
3. Keep Python models (`shared/models.py`) and TypeScript types (`web/src/lib/types.ts`) in sync.
4. Re-running a race updates the existing profile — do not create duplicates.
5. Always run `PYTHONPATH=.` when invoking pytest from the repo root.
6. Always run `npm ci` in `web/` before building or testing the frontend.
