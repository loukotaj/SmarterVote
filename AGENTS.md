# SmarterVote AI Assistant Instructions

Guidelines for generating and editing code in this repository.

## Project Overview

Multi-phase AI agent for electoral analysis:
- **Agent Pipeline**: DISCOVER → RESEARCH (×6 issue groups) → REFINE
- **Output**: RaceJSON v0.2 with 12 canonical issues, confidence levels, and sources
- **Local-first**: Run agent locally, deploy races-api for serving data

## Canonical Issues (12)

Healthcare, Economy, Climate/Energy, Reproductive Rights, Immigration, Guns & Safety, Foreign Policy, Social Justice, Education, Tech & AI, Election Reform, Local Issues

Defined in `shared/models.py` as `CanonicalIssue` enum and `pipeline_v2/prompts.py`.

## Key Files

| Purpose | Location |
|---------|----------|
| Agent loop + caching | `pipeline_v2/agent.py` |
| Prompt templates | `pipeline_v2/prompts.py` |
| Search cache | `pipeline_v2/search_cache.py` |
| Agent handler | `pipeline_client/backend/handlers/v2_agent.py` |
| API endpoints | `pipeline_client/backend/main.py` |
| Schema models | `shared/models.py` |
| TypeScript types | `web/src/lib/types.ts` |
| API services | `services/races-api/` |
| Infrastructure | `infra/*.tf` |

## Coding Conventions

**Python**:
- Black + isort formatting
- Pydantic v2 models with `model_dump()` and `model_validate()`
- Async where applicable
- Structured logging

**TypeScript/Svelte**:
- Types in `web/src/lib/types.ts`
- Components in `web/src/lib/components/`

## Running the Agent

```bash
# Start the pipeline backend
cd pipeline_client
uvicorn backend.main:app --port 8001

# Trigger a research run via API
curl -X POST http://localhost:8001/api/v2/run \
  -H "Content-Type: application/json" \
  -d '{"race_id": "mo-senate-2024"}'

# Or use the web dashboard at http://localhost:5173/admin/pipeline
```

## Testing APIs with curl

```bash
# List published races
curl http://localhost:8000/races

# Get specific race
curl http://localhost:8000/races/mo-senate-2024

# Run agent
curl -X POST http://localhost:8001/api/v2/run \
  -H "Content-Type: application/json" \
  -d '{"race_id": "mo-senate-2024"}'

# Check run status
curl http://localhost:8001/runs
```

## Running Tests

```bash
# Python tests
python -m pytest tests/test_pipeline_v2.py -v

# Frontend tests
cd web && npx vitest run

# TypeScript check
cd web && npx svelte-check --tsconfig ./tsconfig.json
```

## Project Rules

1. **Multi-Phase Agent**: Discovery → Issue Research (6 groups) → Refinement
2. **12 Canonical Issues**: Keep consistent across all outputs
3. **Source Attribution**: Preserve confidence scoring and sources
4. **Search Caching**: Use SQLite cache for Serper searches (7-day TTL)
5. **Rerun Support**: Re-running a race updates the existing profile
6. **Type Sync**: Keep Python models and TypeScript types aligned

## Storage Abstraction

The project supports local and cloud storage via backend abstraction:
- `LocalStorageBackend`: File system (default)
- `GCPStorageBackend`: Google Cloud Storage

Configured via environment variables.

## Infrastructure

Cloud deployment is disabled by default (`enable_pipeline_client = false` in `infra/variables.tf`). Enable for production scaling.

Keep responses concise. Point to files instead of duplicating content.
