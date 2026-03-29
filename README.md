# SmarterVote

AI-powered electoral analysis using a multi-phase research agent with web search.

## Overview

SmarterVote uses an AI agent to research U.S. election races, producing structured candidate profiles with policy stances, sources, and confidence levels. The agent runs in three phases — Discovery, Issue Research, and Refinement — making 8 focused LLM calls per race. Searches are cached to avoid redundant API calls, and re-running a race updates the existing profile.

**Agent Phases**: DISCOVER → RESEARCH (×6 issue groups) → REFINE

**Components**:
- `pipeline_client/agent/`: Multi-phase AI agent (OpenAI + Serper web search)
- `pipeline_client/`: Execution engine (FastAPI backend, run manager, storage)
- `services/races-api/`: API serving published race data
- `web/`: SvelteKit frontend with pipeline dashboard
- `infra/`: Terraform for GCP deployment

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 22+

### Setup

```powershell
# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Copy environment file and add API keys
copy .env.example .env
# Edit .env with: OPENAI_API_KEY, SERPER_API_KEY
```

### Run the Agent

The agent is accessed via the pipeline API:

```powershell
# Start the pipeline backend
cd pipeline_client
uvicorn backend.main:app --port 8001

# In another terminal, trigger a research run
curl -X POST http://localhost:8001/api/run \
  -H "Content-Type: application/json" \
  -d '{"race_id": "mo-senate-2024"}'
```

Or use the web dashboard at `http://localhost:5173/admin/pipeline`.

### Run Web UI

```powershell
# Start races API (serves published data)
cd services/races-api
python main.py

# In another terminal, start web
cd web
npm install
npm run dev
```

## Project Structure

```
pipeline_client/            # Agent + execution engine
  agent/
    agent.py                # Multi-phase research agent with search caching
    prompts.py              # Phase-specific prompt templates
    search_cache.py         # SQLite search result cache
  backend/
    handlers/agent.py       # Agent step handler
    main.py                 # FastAPI endpoints
    pipeline_runner.py      # Step execution + logging
    step_registry.py        # Handler registry
services/races-api/         # REST API for race data
shared/                     # Pydantic models shared across components
web/                        # SvelteKit frontend
infra/                      # Terraform infrastructure (disabled by default)
data/published/             # Output JSON files
data/cache/                 # SQLite search cache
```

## Key Concepts

- **12 Canonical Issues**: Healthcare, Economy, Climate/Energy, Reproductive Rights, Immigration, Guns & Safety, Foreign Policy, Social Justice, Education, Tech & AI, Election Reform, Local Issues
- **Multi-Phase Agent**: Discovery → 6 issue-group research calls → Refinement (8 LLM calls total)
- **Search Caching**: SQLite-based cache for Serper web search results (7-day TTL)
- **Rerun/Update Mode**: Re-running a race updates the existing profile with new developments
- **RaceJSON v0.2**: Output format with candidates, issues, confidence levels, sources

## Configuration

Key environment variables (see `.env.example`):
- `OPENAI_API_KEY` - Required for GPT-5.4/mini
- `SERPER_API_KEY` - Required for web search
- `SMARTERVOTE_CHEAP_MODE=true` - Use gpt-5.4-mini (default) vs gpt-5.4

## Docs

- [Architecture](docs/architecture.md) - Agent design and data flow
- [Local Development](docs/local-development.md) - Setup and testing
- [Deployment](docs/deployment-guide.md) - Cloud deployment (GCP)
- [Infrastructure](infra/README.md) - Terraform modules

## License

CC BY-NC-SA 4.0 (see LICENSE)
