# SmarterVote

AI-powered electoral analysis with a corpus-first pipeline and multi-LLM consensus.

## What it is
- Pipeline (Python): 4-step processing engine producing RaceJSON v0.2
- Services (FastAPI): enqueue-api (jobs), races-api (serve published data)
- Web (SvelteKit + TypeScript): static site consuming races-api
- Infra (Terraform + GCP): Cloud Run, Pub/Sub, Secret Manager, Cloud Storage

See docs for details: `docs/architecture.md` and `docs/issues-list.md`.

## Quick start

Prereqs
- Python 3.10+
- Node.js 22+
- Terraform 1.5+ (for infra)
- Docker (for images)

Setup
- Copy env file: `.env.example` → `.env` and fill keys (OpenAI/Anthropic/xAI, Google Search)
- Create venv and install:
  - Windows PowerShell
    - `python -m venv .venv`
    - `.venv\Scripts\Activate.ps1`
    - `pip install -r pipeline/requirements.txt`
  - Web: `cd web && npm install`

Dev commands
- Test vector DB: `python test_vector_db.py`
- Run all tests: `python -m pytest -v`
- Start web: `cd web && npm run dev`
- Start races API: `cd services/races-api && python main.py`
- Local pipeline run: `python scripts/run_local.py <race-id>`

## Pipeline workflow
INGEST → CORPUS → SUMMARIZE → PUBLISH

- Vector DB: ChromaDB (corpus-first)
- Multi-LLM: GPT-4o, Claude-3.5, grok-3 with 2-of-3 consensus
- Cheap Mode: GPT-4o-mini, Claude-3-Haiku, Grok-3-mini for cost-effective processing
- Output: RaceJSON v0.2, with confidence and sources

## Running the Pipeline

### Cheap Mode (Mini Models - Default)
```bash
python scripts/run_local.py mo-senate-2024
```

### Standard Mode (Premium Models)
```bash
python scripts/run_local.py mo-senate-2024 --full-models
# or set environment variable
export SMARTERVOTE_CHEAP_MODE=false
python scripts/run_local.py mo-senate-2024
```

## Docs
- Architecture: `docs/architecture.md`
- Local dev: `docs/local-development.md`
- Testing: `docs/testing-guide.md`
- Infra: `infra/README.md`
- Web: `web/README.md`

## Contributing
- Run linters/tests before PRs
- Keep types/models in sync (Python Pydantic ↔ web `src/lib/types.ts`)

## License
CC BY-NC-SA 4.0 (see `LICENSE`).
