# SmarterVote AI Assistant Instructions

Use these guardrails when generating or editing code in this repository.

## Context
- Corpus-first AI pipeline: Python pipeline, FastAPI services, SvelteKit web, Terraform infra
- 7-step pipeline: DISCOVER → FETCH → EXTRACT → CORPUS → SUMMARIZE → ARBITRATE → PUBLISH
- Output: RaceJSON v0.2 with 11 canonical issues, confidence levels, and sources

## Coding conventions
- Python: Black + isort; Pydantic models; structured logging; async where applicable
- TypeScript/Svelte: types in `web/src/lib/types.ts`; components in `lib/components/`
- Tests: pytest for Python (adjacent unit tests), FastAPI TestClient, Vitest/Playwright for web

## Development workflow
- Pipeline quick run: `python scripts/run_local.py <race-id>`
- Tests: `python -m pytest -v`; web `npm run test`
- Web dev: `cd web && npm run dev`
- Infra: `cd infra && terraform plan`

## Key references
- Architecture: `docs/architecture.md`
- Issues & status: `docs/issues-list.md`
- Testing guide: `docs/testing.md`
- Schemas: `pipeline/app/schema.py`, web `src/lib/types.ts`

## Project-specific rules
- Always build/query the vector DB before summarization (ChromaDB)
- Use multi-LLM triangulation (no single-model summaries)
- Keep the 11 canonical issues consistent across outputs
- Preserve source attribution and confidence scoring

Keep responses concise. Point to files instead of duplicating content.
