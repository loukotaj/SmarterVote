# SmarterVote

AI-powered electoral analysis with corpus-first processing and multi-LLM consensus.

## Overview

SmarterVote processes electoral data through a 4-step pipeline that builds comprehensive content understanding before generating summaries. Multiple AI models validate each other's output for reliability.

**Pipeline**: INGEST → CORPUS → SUMMARIZE → PUBLISH

**Components**:
- `pipeline_client/`: Local execution engine (FastAPI + CLI)
- `services/races-api/`: API serving published race data
- `web/`: SvelteKit static site
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

# Install pipeline dependencies
pip install -r pipeline/requirements.txt

# Copy environment file and add API keys
copy .env.example .env
# Edit .env with: OPENAI_API_KEY, ANTHROPIC_API_KEY, XAI_API_KEY, SERPER_API_KEY
```

### Run Pipeline

```powershell
# Run full pipeline for a race
python pipeline_client/run.py mo-senate-2024

# Or use the start script
cd pipeline_client
.\start.ps1 mo-senate-2024
```

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
pipeline/app/           # Core pipeline modules (schema, providers, steps)
pipeline_client/        # Execution engine (backend/, run.py)
services/races-api/     # REST API for race data
shared/                 # Pydantic models shared across components
web/                    # SvelteKit frontend
infra/                  # Terraform infrastructure (disabled by default)
data/published/         # Output JSON files
data/chroma_db/         # Vector database
```

## Key Concepts

- **12 Canonical Issues**: Healthcare, Economy, Climate/Energy, Reproductive Rights, Immigration, Guns & Safety, Foreign Policy, Social Justice, Education, Tech & AI, Election Reform, Local Issues
- **Multi-LLM Consensus**: GPT-4o, Claude-3.5, grok-3 (or mini variants in cheap mode)
- **RaceJSON v0.2**: Output format with candidates, issues, confidence levels, sources
- **ChromaDB**: Vector corpus for semantic search

## Configuration

Key environment variables (see `.env.example`):
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY` - LLM providers
- `SERPER_API_KEY` - Web search
- `SMARTERVOTE_CHEAP_MODE=true` - Use mini models for cost savings
- `CHROMA_PERSIST_DIR=./data/chroma_db` - Vector DB location

## Docs

- [Architecture](docs/architecture.md) - System design and pipeline details
- [Local Development](docs/local-development.md) - Setup and testing
- [Deployment](docs/deployment-guide.md) - Cloud deployment (GCP)
- [Infrastructure](infra/README.md) - Terraform modules

## License

CC BY-NC-SA 4.0 (see LICENSE)
