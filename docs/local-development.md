# Local Development

Complete setup guide for running SmarterVote locally — pipeline client, races API, and web frontend.

## Prerequisites

- **Python 3.10+** (tested with 3.10.6)
- **Node.js 22+** (tested with 22.18.0)
- **Git**

## 1. API Keys (Required)

You need **two** API keys to run the pipeline. Get them from:

| Key | Service | Get it at | Cost |
|-----|---------|-----------|------|
| `OPENAI_API_KEY` | GPT-4o-mini/GPT-4o for candidate research | https://platform.openai.com/api-keys | Pay-as-you-go (check billing!) |
| `SERPER_API_KEY` | Web search via Google | https://serper.dev | Free tier: 2,500 searches |

**Optional keys** (only needed if you enable the review phase):

| Key | Service | Purpose |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | Claude Sonnet 4 | Independent fact-check review |
| `GEMINI_API_KEY` | Google Gemini | Independent fact-check review |
| `XAI_API_KEY` | xAI Grok | Independent fact-check review |

> **Important**: Your OpenAI account must have billing credits. A `429 insufficient_quota` error means you need to add funds at https://platform.openai.com/settings/organization/billing.

## 2. Environment Setup

```powershell
cd SmarterVote      # project root (contains pyproject.toml)

# Create/verify .env file
copy .env.example .env    # if starting fresh
```

Edit `.env` and set at minimum:
```env
OPENAI_API_KEY=sk-proj-your-key-here
SERPER_API_KEY=your-serper-key-here
```

### Python Virtual Environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e shared/
```

### Web Frontend

```powershell
cd web
npm install
cd ..
```

## 3. Running All Services

### Option A: One-command start (recommended)

```powershell
.\dev-start.ps1
```

This starts all three services as background jobs. Use `Get-Job` to monitor and `Receive-Job -Name <name>` to see logs.

### Option B: Manual start (three terminals)

**Terminal 1 — Pipeline Client** (port 8001):
```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn pipeline_client.backend.main:app --host 0.0.0.0 --port 8001 --reload
```

**Terminal 2 — Races API** (port 8080):
```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn services.races-api.main:app --host 0.0.0.0 --port 8080 --reload
```

**Terminal 3 — Web Frontend** (port 5173):
```powershell
cd web
npx vite dev --port 5173 --host
```

## 4. Using the Application

### Web Frontend
- **Homepage**: http://localhost:5173 — browse published races
- **Race detail**: http://localhost:5173/race/tx-governor-2024 — view candidate comparison
- **About page**: http://localhost:5173/about
- **Admin dashboard**: http://localhost:5173/admin/pipeline — trigger pipeline runs

### Running a Pipeline Job

**Via the admin dashboard** (recommended):
1. Go to http://localhost:5173/admin/pipeline
2. Enter a race ID (e.g. `az-senate-2024` or a new slug like `pa-senate-2024`)
3. Click "Research Race"
4. Watch live logs via WebSocket — the pipeline will:
   - **Phase 1 (Discovery)**: Identify candidates, career history, images
   - **Phase 2 (Issue Research)**: 6 LLM calls, one per issue group (economy, healthcare, etc.)
   - **Phase 3 (Refinement)**: Merge and clean the full profile
   - **Phase 4 (Review)**: Optional fact-check via Claude, Gemini, and Grok (if "AI Review" is checked)

   Toggle **Cheap Mode** for faster/cheaper runs, or expand **Advanced Model Settings** to override specific models.
5. Results are automatically published to `data/published/{race_id}.json`
6. The races API serves the new data immediately — refresh the homepage

**Via curl/API**:
```powershell
$body = '{"race_id": "pa-senate-2024", "options": {"save_artifact": true}}'
Invoke-WebRequest -Uri "http://localhost:8001/api/run" `
    -Method POST `
    -Headers @{"Content-Type"="application/json"} `
    -Body $body
```

### Understanding Race IDs

Race IDs follow the format `{state}-{office}-{year}`, e.g.:
- `az-senate-2024` — Arizona Senate 2024
- `tx-governor-2024` — Texas Governor 2024
- `ny-house-03-2024` — New York House District 3, 2024

You can use any race ID — if no published data exists, the pipeline runs a full fresh research. If data already exists, it enters **update mode**, improving the existing profile.

## 5. Configuration Reference

### Key Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | GPT models (required) | — |
| `SERPER_API_KEY` | Web search (required) | — |
| `ANTHROPIC_API_KEY` | Claude review (optional) | — |
| `GEMINI_API_KEY` | Gemini review (optional) | — |
| `XAI_API_KEY` | Grok review (optional) | — |
| `SEARCH_CACHE_TTL_HOURS` | Search cache TTL | `168` (7 days) |

### Pipeline Options

When triggering a run, the `options` object supports:

| Option | Type | Default | Purpose |
|--------|------|---------|---------|
| `cheap_mode` | bool | `true` | Use cheaper/faster model variants |
| `save_artifact` | bool | `true` | Save full run artifact for later inspection |
| `enable_review` | bool | `false` | Send output to Claude, Gemini, and Grok |
| `research_model` | string | `null` | Override OpenAI research model |
| `claude_model` | string | `null` | Override Claude review model |
| `gemini_model` | string | `null` | Override Gemini review model |
| `grok_model` | string | `null` | Override Grok review model |

### Model Defaults

| Phase | Cheap Mode (default) | Full Mode |
|-------|---------------------|----------|
| Research (OpenAI) | gpt-5-mini | gpt-5.4 |
| Review: Claude | claude-haiku-4-20250514 | claude-sonnet-4-6 |
| Review: Gemini | gemini-3.0-flash-lite | gemini-3.0-flash |
| Review: Grok | grok-3-mini | grok-3 |

You can override any model from the admin dashboard's "Advanced Model Settings" panel, or by passing the option in the API request body.

### Ports

| Service | Port | Health Check |
|---------|------|-------------|
| Pipeline Client | 8001 | `GET /health` |
| Races API | 8080 | `GET /races` |
| Web Frontend | 5173 | — |

### Frontend Environment (`web/.env`)

| Variable | Purpose | Default |
|----------|---------|---------|
| `VITE_RACES_API_URL` | Races API URL | `http://localhost:8080` |
| `VITE_API_BASE` | Pipeline Client URL | `http://localhost:8001` |
| `VITE_SKIP_AUTH` | Bypass Auth0 login locally | `true` |

## 6. Project Structure

```
data/
├── cache/          # SQLite search cache (auto-created)
└── published/      # Output JSON files (served by races API)

pipeline_client/
├── agent/          # AI research agent
│   ├── agent.py    # Multi-phase agent loop with web search
│   ├── prompts.py  # Prompt templates for each phase
│   └── search_cache.py # SQLite-backed search result cache
├── backend/        # FastAPI app, WebSocket logging, run management
│   ├── main.py     # API endpoints
│   ├── handlers/   # Pipeline step handlers (agent.py)
│   └── ...
└── run.py          # CLI entry point

services/
└── races-api/      # FastAPI REST API serving published race data

shared/
└── models.py       # Pydantic v2 models (RaceJSON v0.3 schema)

web/                # SvelteKit + Tailwind frontend
├── src/routes/     # Pages (home, race detail, admin)
├── src/lib/        # Components, stores, services
└── .env            # Frontend env vars
```

## 7. Troubleshooting

### "insufficient_quota" / 429 from OpenAI
Your OpenAI API key has no billing credits. Add funds at https://platform.openai.com/settings/organization/billing.

### "OPENAI_API_KEY is not set"
The `.env` file is not being loaded. Make sure:
1. `.env` exists in the project root (same directory as `pyproject.toml`)
2. You're starting the pipeline client from the project root

### Port conflicts
Kill existing processes on a port:
```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### Import errors
Ensure the virtual environment is active and `shared` package is installed:
```powershell
.venv\Scripts\Activate.ps1
pip install -e shared/
```

### Search cache
Cached search results are stored in `data/cache/`. Delete the cache to force fresh web searches:
```powershell
Remove-Item -Recurse -Force data\cache
```

### Auth0 in production
For production deployment with Auth0 authentication, see [auth0-configuration.md](auth0-configuration.md). Local development bypasses auth via `VITE_SKIP_AUTH=true`.

## 8. Terraform / Infrastructure (Not Required Locally)

The `infra/` directory contains Terraform configs for GCP deployment (Cloud Run, Pub/Sub, Cloud Storage). You do **not** need Terraform for local development. See [deployment-guide.md](deployment-guide.md) for production setup.
