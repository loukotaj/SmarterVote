# Local Development

Quick setup guide for SmarterVote development.

## Prerequisites

- Python 3.10+
- Node.js 22+
- Git

## Setup

### 1. Clone and Configure

```powershell
git clone https://github.com/loukotaj/SmarterVote.git
cd SmarterVote

# Copy environment template
copy .env.example .env
```

Edit `.env` with your API keys:
```env
OPENAI_API_KEY=your_key
SERPER_API_KEY=your_key

# Optional
SMARTERVOTE_CHEAP_MODE=true
```

### 2. Python Environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r pipeline/requirements.txt
```

### 3. Web Frontend

```powershell
cd web
npm install
```

## Running the Agent

### Via API

```powershell
# Start the pipeline backend
cd pipeline_client
uvicorn backend.main:app --port 8001

# Trigger a research run
curl -X POST http://localhost:8001/api/v2/run \
  -H "Content-Type: application/json" \
  -d '{"race_id": "mo-senate-2024"}'
```

### Via Web Dashboard

Start the backend and web frontend, then navigate to `http://localhost:5173/admin/pipeline`. Enter a race ID and click "Research Race".

Re-running the same race automatically enters update mode, improving the existing profile with new information.

## Running Services

### Races API (serves published data)

```powershell
cd services/races-api
python main.py
# Runs on http://localhost:8000
```

### Web Frontend

```powershell
cd web
npm run dev
# Runs on http://localhost:5173
```

## Running Tests

```bash
# Python unit tests
python -m pytest tests/test_pipeline_v2.py -v

# Frontend tests
cd web && npx vitest run

# TypeScript check
cd web && npx svelte-check --tsconfig ./tsconfig.json
```

## Project Structure

```
data/
├── cache/          # SQLite search cache
└── published/      # Output JSON files

pipeline_v2/
├── agent.py        # Multi-phase agent loop
└── prompts.py      # Prompt templates

pipeline_client/
├── backend/        # API + step handler
└── run.py          # CLI entry point

services/
└── races-api/      # REST API

web/                # SvelteKit frontend
```

## Configuration

Key environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | GPT models | Required |
| `SERPER_API_KEY` | Web search | Required |
| `SMARTERVOTE_CHEAP_MODE` | Use gpt-5-mini | `true` |
| `SEARCH_CACHE_TTL_HOURS` | Search cache TTL | `168` (7 days) |

## Troubleshooting

**API key errors**: Check `.env` file exists and keys are valid.

**Port conflicts**: Default ports are 8000 (races API), 8001 (pipeline API), and 5173 (web).

**Import errors**: Ensure you're in the virtual environment (`.venv\Scripts\Activate.ps1`).

**Search cache**: Cached search results are stored in `data/cache/`. Delete the cache directory to force fresh searches.
