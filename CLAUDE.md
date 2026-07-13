# SmarterVote — Claude Code Guide

## Priority Model

**GCP/deployed is always the source of truth. CI (GitHub Actions) is the validation gate.**

- Local runs are useful for quick iteration, but CI green is what matters for correctness.
- Do not treat local test results as definitive — they mock more than CI does.
- Do not run `terraform apply` or publish race data unless explicitly asked.
- The production system runs on GCP; local services exist only for debugging.

## Deployed Architecture

```
pipeline_client/worker.py        → Cloud Run Job or long-lived local Docker worker
functions/admin_agent/main.py    → Cloud Function gen2 (durable admin agent)
services/races-api/              → Cloud Run (admin + public FastAPI API)
GCS bucket                       → race data: drafts/, races/, summaries.json, retired/
Firestore                        → pipeline_queue, pipeline_runs, races catalog,
                                   admin_agent_conversations/messages/tasks,
                                   search_cache, page_cache
Secret Manager                   → API keys (openrouter, serper, admin, cloudflare)
Cloudflare Pages                 → static SvelteKit frontend (web/)
Artifact Registry                → container images for Cloud Run
```

**Deployment path** — every push to `main`:
1. `.github/workflows/ci.yaml` — all gates must pass (security, tests, lint, terraform)
2. `.github/workflows/terraform-deploy.yaml` — builds containers, pushes to Artifact Registry, runs `terraform apply`
3. `.github/workflows/cloudflare-deploy.yaml` — builds and deploys SvelteKit frontend

## Quick File Map

| Area | Path | Notes |
| ---- | ---- | ----- |
| Production API | `services/races-api/main.py` | All admin + public endpoints |
| Pipeline worker | `pipeline_client/worker.py` | One-shot Cloud Run Job and continuous Docker entry point |
| Admin agent CF | `functions/admin_agent/main.py` | Durable admin tasks |
| Agent orchestration | `pipeline_client/backend/handlers/agent.py` | `AgentHandler` used by CFs |
| AI research agent | `pipeline_client/agent/` | Multi-phase research engine |
| Shared schema | `shared/models.py` | RaceJSON v0.3 — Pydantic v2 |
| Frontend | `web/src/` | SvelteKit; types mirror `shared/models.py` |
| Infrastructure | `infra/` | Terraform for all GCP services |
| Local-only dev API | `pipeline_client/backend/main.py` | Not production; debug only |

## Validation

Run the narrowest useful check for what you touched. The commands below mirror the substantive CI gates; CI also runs a tracked-artifact check and Gitleaks secret scan.

```bash
# Python pipeline + agent tests (excludes cloud-function-specific and API admin tests)
PYTHONPATH=. python -m pytest tests -v \
  --ignore=tests/test_races_api_admin.py

# CI additionally enforces the ratcheted branch-coverage floor configured in
# .github/workflows/ci.yaml; local coverage behavior is in .coveragerc.

# Races API tests
cd services/races-api && PYTHONPATH=../.. python -m pytest test_races_api.py -v

# Races API admin tests (run from repo root)
cd services/races-api && PYTHONPATH=../.. python -m pytest ../../tests/test_races_api_admin.py -v

# Python formatting check
python -m black --check shared smartervote_mcp services/races-api tests pipeline_client functions scripts
python -m isort --check-only shared smartervote_mcp services/races-api tests pipeline_client functions scripts

# Frontend (always npm ci first; CI creates minimal static JSON fixtures before build)
cd web && npm ci && npm run check && npm run lint && npm run build && npm run test:unit -- --run

# Terraform
cd infra && terraform fmt -check -recursive && terraform init -backend=false && terraform validate
```

For the full local gate sequence: `.\scripts\run-ci-gates.ps1`

## Python Conventions

- **Black** (line-length 127, py310) + **isort** (profile "black") — config in `pyproject.toml`
- **Pydantic v2 only** — `model_dump()` / `model_validate()`, never `.dict()` / `.parse_obj()`
- **Imports** — package-relative inside a package; absolute across boundaries (`from shared.models import RaceJSON`)
- **Lazy imports in handlers** to break circular dependencies — import inside functions, not at module top
- **Logging** — use `logging.getLogger("pipeline")` in pipeline/agent code
- **Async HTTP** — `httpx.AsyncClient`, never `requests`
- **Race ID format** — `^[a-z0-9][a-z0-9_-]{0,99}$` (e.g., `ga-senate-2026`)
- **Auth0** — protected routes use `dependencies=[Depends(verify_token)]`; local dev can set `SKIP_AUTH=true`

## TypeScript / Svelte Conventions

- `web/src/lib/types.ts` **must mirror** `shared/models.py` — update both simultaneously
- Pipeline option validation is canonical in `shared/pipeline_options.py`; API and worker models subclass it for wire versus resolved defaults
- Components in `web/src/lib/components/`; routes use `+page.svelte` / `+page.ts`
- **Prettier + ESLint** for formatting; **TailwindCSS** with semantic design tokens
- Frontend env vars use `VITE_` prefix; static adapter for Cloudflare Pages

## Key Rules

1. **Drafts before publish** — agent always saves to GCS `drafts/`; publish is an explicit admin action
2. **Canonical issues are frozen** — 12 issues defined in `shared/models.py` `CanonicalIssue`; never add/remove/rename without explicit instruction
3. **Production API is `services/races-api`** — new admin behavior goes there first; `pipeline_client/backend/main.py` is local debug only
4. **Storage mode** — `local` uses filesystem, `gcp` uses GCS + Firestore (see `PIPELINE_MODES.md`)
5. **Static GCS hosting** — if `VITE_PUBLIC_DATA_URL` is set, public reads go directly to GCS; publish keeps `races/summaries.json` index up to date
6. **Pipeline mode** — prefer cheap/economy for queued race work; only use expensive models when explicitly asked
7. **Pipeline run cost** — **full research runs are expensive** (LLM + web search API costs per candidate per race). Only queue full runs when the user explicitly asks or there is a clear data quality problem requiring it. Targeted lightweight runs are fine: `steps=["discovery"]` to fix candidate lists, `steps=["forecast"]` to regenerate forecasts, or image-only refreshes. Never batch-queue full runs autonomously without user sign-off.
8. **MCP over scratch** — for reusable operations prefer enhancing `smartervote_mcp/server.py` over one-off scripts in `scratch/`
9. **Tests mock network** — `tests/conftest.py` has `autouse=True` fixtures mocking external calls; add similar mocks for any new network-dependent code

## Prompt Shortcuts

- Full CI check: follow `.github/prompts/ci-check.prompt.md`
- Project improvement review: follow `.github/prompts/project-improvements-review-and-implement.prompt.md`
- Pipeline agent work: follow `.github/agents/pipeline-researcher.agent.md`
- Frontend type sync: follow `.github/instructions/frontend-types.instructions.md`
- Terraform work: follow `.github/instructions/terraform.instructions.md`

## Detailed Docs (link, don't duplicate)

- **Architecture & all endpoints**: `docs/architecture.md`
- **Pipeline modes (local vs GCP)**: `PIPELINE_MODES.md`
- **Infrastructure conventions**: `infra/README.md`
- **Deployment**: `docs/deployment-guide.md`
- **Auth0 setup**: `docs/auth0-configuration.md`
- **Local development**: `docs/local-development.md`
- **Documentation map and status**: `docs/README.md`
- **AI conventions (Copilot-style)**: `.github/copilot-instructions.md`
