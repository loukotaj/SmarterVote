# SmarterVote AI Assistant Instructions

Guidelines for generating and editing code in this repository.

## Project Overview

Multi-phase AI agent for electoral analysis:
- **Agent Pipeline**: DISCOVERY → IMAGES → ISSUES (×12 per-candidate) → FINANCE → REFINEMENT → REVIEW (optional) → ITERATION
- **Output**: RaceJSON v0.3 with canonical issues, confidence levels, sources, and optional multi-LLM review
- **Cloud-first**: Pipeline runs on Cloud Run, data in GCS/Firestore; local dev supported

## Canonical Issues

Healthcare, Economy, Climate/Energy, Reproductive Rights, Immigration, Guns & Safety, Foreign Policy, Social Justice, Education, Tech & AI, Election Reform, Local Issues

Defined in `shared/models.py` as `CanonicalIssue` enum and `pipeline_client/agent/prompts.py`.

## Key Files

| Purpose | Location |
|---------|----------|
| Agent loop + orchestration | `pipeline_client/agent/agent.py` |
| Prompt templates | `pipeline_client/agent/prompts.py` |
| Agent tool definitions | `pipeline_client/agent/tools.py` |
| LLM request/response handling | `pipeline_client/agent/handlers.py` |
| Multi-LLM review | `pipeline_client/agent/review.py` |
| Candidate image resolution | `pipeline_client/agent/images.py` |
| Ballotpedia lookup | `pipeline_client/agent/ballotpedia.py` |
| Search cache (SQLite) | `pipeline_client/agent/search_cache.py` |
| Token counting + cost | `pipeline_client/agent/cost.py` |
| Agent step handler | `pipeline_client/backend/handlers/agent.py` |
| API endpoints (40+) | `pipeline_client/backend/main.py` |
| Pipeline step models | `pipeline_client/backend/models.py` |
| Pipeline runner | `pipeline_client/backend/pipeline_runner.py` |
| Run lifecycle manager | `pipeline_client/backend/run_manager.py` |
| Queue manager | `pipeline_client/backend/queue_manager.py` |
| Race manager | `pipeline_client/backend/race_manager.py` |
| Settings (from env) | `pipeline_client/backend/settings.py` |
| Storage routing | `pipeline_client/backend/storage.py` |
| Storage backends | `pipeline_client/backend/storage_backend.py` |
| Schema models (v0.3) | `shared/models.py` |
| TypeScript types | `web/src/lib/types.ts` |
| Frontend pipeline service | `web/src/lib/services/pipelineApiService.ts` |
| Races API | `services/races-api/main.py` |
| Infrastructure | `infra/*.tf` |

## Coding Conventions

**Python**:
- Black (line-length 127, target py310) + isort (profile "black")
- Pydantic v2 models with `model_dump()` and `model_validate()`
- Async where applicable
- Structured logging with module-level loggers

**TypeScript/Svelte**:
- Types in `web/src/lib/types.ts` must mirror `shared/models.py`
- Components in `web/src/lib/components/`
- Prettier + ESLint; TailwindCSS for styling

## Running the Agent

```bash
# Start the pipeline backend (from repo root)
python -m uvicorn pipeline_client.backend.main:app --port 8001 --reload

# Trigger a research run via API
curl -X POST http://localhost:8001/api/run \
  -H "Content-Type: application/json" \
  -d '{"race_id": "ga-senate-2026"}'

# Or use the web dashboard at http://localhost:5173/admin/pipeline
```

## Testing APIs with curl

```bash
# List published races (races-api on port 8080)
curl http://localhost:8080/races

# Get specific race
curl http://localhost:8080/races/ga-senate-2026

# Run agent (pipeline client on port 8001)
curl -X POST http://localhost:8001/api/run \
  -H "Content-Type: application/json" \
  -d '{"race_id": "ga-senate-2026"}'

# Check run status
curl http://localhost:8001/runs
```

## Running Tests

```bash
# Python pipeline tests (from repo root)
PYTHONPATH=. python -m pytest tests/test_pipeline.py -v

# Races-api tests
cd services/races-api && PYTHONPATH=../.. python -m pytest test_races_api.py -v

# Frontend tests
cd web && npm run test:unit -- --run

# TypeScript check
cd web && npm run check
```

## Project Rules

1. **7-Step Pipeline**: Discovery → Images → Issues → Finance → Refinement → Review → Iteration
2. **Canonical Issues**: Keep consistent across all outputs
3. **Source Attribution**: Preserve confidence scoring and sources
4. **Search Caching**: Use SQLite cache for Serper searches (7-day TTL)
5. **Draft → Publish**: Agent always saves to drafts first; publish is an explicit admin action
6. **Type Sync**: Keep `shared/models.py` and `web/src/lib/types.ts` aligned
7. **PYTHONPATH**: Always run `PYTHONPATH=.` when invoking pytest from repo root

## Storage Abstraction

The project supports local and cloud storage via backend abstraction:
- `LocalStorageBackend`: File system (default for local dev)
- `GCPStorageBackend`: Google Cloud Storage + Firestore (cloud)

Cloud persistence:
- **GCS**: Published/draft race JSON files
- **Firestore**: Run history, race metadata, queue state

Configured via `STORAGE_MODE` environment variable in `pipeline_client/backend/settings.py`.

## Infrastructure

Cloud deployment uses Terraform in `infra/`:
- **Cloud Run**: races-api (public), pipeline-client (Auth0-protected)
- **GCS**: Data bucket (races/, drafts/)
- **Firestore**: Run history, race records, queue
- **Secret Manager**: API keys
- Pipeline client disabled by default (`enable_pipeline_client = false`)

Keep responses concise. Point to files instead of duplicating content.
