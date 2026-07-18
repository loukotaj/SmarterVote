# SmarterVote — Copilot Instructions

AI-powered electoral analysis platform. A multi-phase research agent (OpenRouter + Serper) produces RaceJSON v0.3 candidate profiles. The static SvelteKit frontend is deployed to Cloudflare Pages and uses `races-api` for production API operations.

## Architecture

```
pipeline_client/           # Local runner + AI research agent
  agent/                   # Agent loop, prompts, search cache, review, tools
  backend/                 # Local FastAPI runner, Cloud Function handler, run managers
services/races-api/        # Production public/admin FastAPI API
web/                       # SvelteKit frontend (static adapter → Cloudflare Pages)
shared/                    # Pydantic models shared across Python services
infra/                     # Terraform for GCP (Cloud Run, GCS, Firestore)
tests/                     # Python integration tests
data/published/            # Published race JSON (GCS races/ in cloud)
data/drafts/               # Draft race JSON (GCS drafts/ in cloud)
```

Agent phases: DISCOVERY → IMAGES → ISSUES (×12 per-candidate) → FINANCE → REFINEMENT → POLLING → FORECAST → VOTER_RESOURCES → REVIEW (optional) → ITERATION.
See `docs/architecture.md` for full details, endpoints, and cloud topology.

## Build & Test

```bash
# Python pipeline tests (API admin and Cloud Function suites run separately in CI)
PYTHONPATH=. python -m pytest tests -v --ignore=tests/test_races_api_admin.py

# Python formatting checks
python -m black --check shared smartervote_mcp services/races-api tests pipeline_client functions scripts
python -m isort --check-only shared smartervote_mcp services/races-api tests pipeline_client functions scripts

# Frontend (always npm ci first)
cd web && npm ci && npm run check && npm run lint && npm run build && npm run test:unit -- --run

# Terraform
cd infra && terraform fmt -check -recursive && terraform init -backend=false && terraform validate
```

CI (`.github/workflows/ci.yaml`) runs on push/PR. Infrastructure CD deploys through `.github/workflows/terraform-deploy.yaml`; the static web frontend deploys through `.github/workflows/cloudflare-deploy.yaml`.

## Python Conventions

- **Black** (line-length 127, py310) + **isort** (profile "black") — config in `pyproject.toml`
- **Pydantic v2 only** — use `model_dump()` / `model_validate()`, never v1 `.dict()` / `.parse_obj()`
- **Imports** — use established package-relative imports inside a package; use absolute imports across package boundaries (for example, `from shared.models import RaceJSON`)
- **Lazy imports in handlers** to break circular dependencies — import inside functions, not at module top
- **Logging** — pipeline runner/agent code uses `logging.getLogger("pipeline")`; service modules may use module loggers where already established
- **Async** with `httpx.AsyncClient` for HTTP; FastAPI endpoints are async where applicable
- **Race ID format** — lowercase only, validated via `^[a-z0-9][a-z0-9_-]{0,99}$` (e.g., `ga-senate-2026`)
- **Auth0 on endpoints** — protected routes use `dependencies=[Depends(verify_token)]`; local dev can set `SKIP_AUTH=true`

## TypeScript / Svelte Conventions

- Types in `web/src/lib/types.ts` **must mirror** `shared/models.py` — update both simultaneously
- Components in `web/src/lib/components/`; routes use `+page.svelte` / `+page.ts`
- **Prettier + ESLint** for formatting; **TailwindCSS** with semantic design tokens (`--sv-page`, `--sv-text`, etc.)
- Unused variables prefixed with `_` (ESLint `@typescript-eslint/no-unused-vars` pattern `^_`)
- Frontend env vars use `VITE_` prefix: `VITE_RACES_API_URL`, `VITE_PUBLIC_DATA_URL`, `VITE_AUTH0_AUDIENCE`
- Static-site traffic uses Cloudflare Web Analytics; do not infer public traffic from `races-api` request counts
- Static adapter for Cloudflare Pages (`web/svelte.config.js`)

## Testing Gotchas

- Tests use `autouse=True` fixtures in `tests/conftest.py` that mock external network calls (Wikipedia, etc.) — add similar mocks for any new network-dependent code
- `PYTHONPATH=.` is required from repo root (tests import `pipeline_client.*` and `shared.*`)
- Frontend: `npm run test:unit -- --run` (vitest)

## Key Rules

1. Agent always saves to **drafts** first — publish is an explicit admin action
2. Keep canonical issues consistent: Healthcare, Economy, Climate/Energy, Abortion & Reproductive Health, Immigration, Firearms & Second Amendment, Foreign Policy, Civil Rights & Equality, Education, Tech & AI, Election Policy, Local Issues (defined in `shared/models.py` `CanonicalIssue` enum)
3. Preserve confidence scoring and source attribution in data changes
4. Local dev: `services/races-api` is the production-shaped admin API; `pipeline_client/backend/main.py` is only for direct local runner/debug endpoints
5. Storage mode (`STORAGE_MODE` env var): `local` uses filesystem, `gcp` uses GCS + Firestore — see `PIPELINE_MODES.md`
6. Static published data: GCS is authoritative and publish/unpublish keeps `races/summaries.json` current. The Cloudflare workflow copies published JSON into the static site build. Use `VITE_PUBLIC_DATA_URL` only for a separately public static origin.
7. While temporary scratch scripts are acceptable for quick, one-off prototyping or diagnostics, prefer enhancing the MCP server tools (`smartervote-races`) for operations of longer-term utility.

## Detailed Docs (link, don't duplicate)

- **Architecture & endpoints**: `docs/architecture.md`
- **Local development**: `docs/local-development.md`
- **Auth0 setup**: `docs/auth0-configuration.md`
- **Deployment**: `docs/deployment-guide.md`
- **Pipeline modes**: `PIPELINE_MODES.md`
- **Infrastructure**: `infra/README.md`
- **Contributing**: `CONTRIBUTING.md`
- **Documentation map and status**: `docs/README.md`
