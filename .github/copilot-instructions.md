# SmarterVote — Copilot Instructions

AI-powered electoral analysis platform. Multi-phase research agent (OpenAI + Serper) produces RaceJSON v0.3 candidate profiles. SvelteKit frontend served by a FastAPI races-api.

## Architecture

```
pipeline_client/           # FastAPI pipeline backend + AI research agent
  agent/                   # Agent loop, prompts, search cache, review, tools
  backend/                 # FastAPI app, handlers/, run_manager, queue_manager
services/races-api/        # Public read-only FastAPI serving published RaceJSON
web/                       # SvelteKit frontend (static adapter → GitHub Pages)
shared/                    # Pydantic models shared across Python services
infra/                     # Terraform for GCP (Cloud Run, GCS, Firestore)
tests/                     # Python integration tests
data/published/            # Published race JSON (GCS races/ in cloud)
data/drafts/               # Draft race JSON (GCS drafts/ in cloud)
```

Agent phases: DISCOVERY → IMAGES → ISSUES (×12 per-candidate) → FINANCE → REFINEMENT → REVIEW (optional) → ITERATION.
See `docs/architecture.md` for full details, endpoints, and cloud topology.

## Build & Test

```bash
# Python tests (from repo root — PYTHONPATH required)
PYTHONPATH=. python -m pytest tests/test_pipeline.py -v
cd services/races-api && PYTHONPATH=../.. python -m pytest test_races_api.py -v

# Python formatting
black --line-length 127 --target-version py310 <file>
isort --profile black --line-length 127 <file>

# Frontend (always npm ci first)
cd web && npm ci && npm run check && npm run build && npm run test:unit -- --run

# Terraform
cd infra && terraform fmt -check -recursive && terraform validate
```

CI (`.github/workflows/ci.yaml`) runs all four on push/PR to `main`/`develop`. CD auto-deploys on `main` via Terraform.

## Python Conventions

- **Black** (line-length 127, py310) + **isort** (profile "black") — config in `pyproject.toml`
- **Pydantic v2 only** — use `model_dump()` / `model_validate()`, never v1 `.dict()` / `.parse_obj()`
- **Absolute imports** — `from pipeline_client.agent.agent import run_agent`, not relative
- **Lazy imports in handlers** to break circular dependencies — import inside functions, not at module top
- **Logging** — all loggers use `logging.getLogger("pipeline")`, not `__name__`
- **Async** with `httpx.AsyncClient` for HTTP; FastAPI endpoints are async where applicable
- **Race ID format** — lowercase only, validated via `^[a-z0-9][a-z0-9_-]{0,99}$` (e.g., `ga-senate-2026`)
- **Auth0 on endpoints** — protected routes use `dependencies=[Depends(verify_token)]`; auth gracefully disabled if `AUTH0_DOMAIN` env var is missing (safe for local dev)

## TypeScript / Svelte Conventions

- Types in `web/src/lib/types.ts` **must mirror** `shared/models.py` — update both simultaneously
- Components in `web/src/lib/components/`; routes use `+page.svelte` / `+page.ts`
- **Prettier + ESLint** for formatting; **TailwindCSS** with semantic design tokens (`--sv-page`, `--sv-text`, etc.)
- Unused variables prefixed with `_` (ESLint `@typescript-eslint/no-unused-vars` pattern `^_`)
- Frontend env vars use `VITE_` prefix: `VITE_API_BASE`, `VITE_RACES_API_URL`
- Static adapter for GitHub Pages (`web/svelte.config.js`)

## Testing Gotchas

- Tests use `autouse=True` fixtures in `tests/conftest.py` that mock external network calls (Wikipedia, etc.) — add similar mocks for any new network-dependent code
- `PYTHONPATH=.` is required from repo root (tests import `pipeline_client.*` and `shared.*`)
- Frontend: `npm run test:unit -- --run` (vitest)

## Key Rules

1. Agent always saves to **drafts** first — publish is an explicit admin action
2. Keep canonical issues consistent: Healthcare, Economy, Climate/Energy, Reproductive Rights, Immigration, Guns & Safety, Foreign Policy, Social Justice, Education, Tech & AI, Election Reform, Local Issues (defined in `shared/models.py` `CanonicalIssue` enum)
3. Preserve confidence scoring and source attribution in data changes
4. Local dev: run history is in-memory only (lost on restart); queue persists to `pipeline_client/queue.json`
5. Storage mode (`STORAGE_MODE` env var): `local` uses filesystem, `gcp` uses GCS + Firestore — see `PIPELINE_MODES.md`

## Detailed Docs (link, don't duplicate)

- **Architecture & endpoints**: `docs/architecture.md`
- **Local development**: `docs/local-development.md`
- **Auth0 setup**: `docs/auth0-configuration.md`
- **Deployment**: `docs/deployment-guide.md`
- **Pipeline modes**: `PIPELINE_MODES.md`
- **Infrastructure**: `infra/README.md`
- **Contributing**: `CONTRIBUTING.md`
