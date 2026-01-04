# SmarterVote AI Assistant Instructions

Guidelines for generating and editing code in this repository.

## Project Overview

Corpus-first AI pipeline for electoral analysis:
- **4-Step Pipeline**: INGEST → CORPUS → SUMMARIZE → PUBLISH
- **Output**: RaceJSON v0.2 with 12 canonical issues, confidence levels, and sources
- **Local-first**: Run pipeline locally, deploy races-api for serving data

## Canonical Issues (12)

Healthcare, Economy, Climate/Energy, Reproductive Rights, Immigration, Guns & Safety, Foreign Policy, Social Justice, Education, Tech & AI, Election Reform, Local Issues

Defined in `shared/models.py` as `CanonicalIssue` enum.

## Key Files

| Purpose | Location |
|---------|----------|
| Schema models | `shared/models.py`, `pipeline/app/schema.py` |
| TypeScript types | `web/src/lib/types.ts` |
| Pipeline handlers | `pipeline_client/backend/handlers/` |
| Provider registry | `pipeline/app/providers/` |
| API services | `services/races-api/`, `services/enqueue-api/` |
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

## Running the Pipeline Locally

```powershell
# Full pipeline run
python pipeline_client/run.py mo-senate-2024

# Individual steps (via CLI)
python pipeline_client/run.py mo-senate-2024 --step step01_metadata
python pipeline_client/run.py mo-senate-2024 --step step02_corpus
python pipeline_client/run.py mo-senate-2024 --step step03_summarise
python pipeline_client/run.py mo-senate-2024 --step step04_publish
```

## Testing APIs with curl

```bash
# List published races
curl http://localhost:8000/races

# Get specific race
curl http://localhost:8000/races/mo-senate-2024

# Pipeline status (if running pipeline_client server)
curl http://localhost:8080/api/runs
```

## Project Rules

1. **Corpus-first**: Always build/query vector DB before summarization
2. **Multi-LLM**: Use triangulation, never single-model summaries
3. **12 Canonical Issues**: Keep consistent across all outputs
4. **Source Attribution**: Preserve confidence scoring and sources
5. **Type Sync**: Keep Python models and TypeScript types aligned

## Storage Abstraction

The project supports local and cloud storage via backend abstraction:
- `LocalStorageBackend`: File system (default)
- `GCPStorageBackend`: Google Cloud Storage

Configured via environment variables.

## Infrastructure

Cloud deployment is disabled by default (`enable_pipeline_client = false` in `infra/variables.tf`). Enable for production scaling.

Keep responses concise. Point to files instead of duplicating content.
