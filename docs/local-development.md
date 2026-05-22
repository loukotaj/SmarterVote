# Local Development

This guide runs the web app, the production-shaped `races-api`, and the local-only pipeline development API.

## Prerequisites

- Python 3.10+
- Node.js 22+
- Git
- `OPENROUTER_API_KEY` and `SERPER_API_KEY` for real agent runs

## Environment Setup

From the project root, the directory that contains `pyproject.toml`:

```powershell
copy .env.example .env
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e shared/

cd web
npm ci
cd ..
```

Edit `.env` and set at minimum:

```env
OPENROUTER_API_KEY=sk-or-your-key-here
SERPER_API_KEY=your-serper-key-here
```

## One-command Start

```powershell
.\dev-start.ps1
```

Expected services:

| Service | Port | Notes |
|---------|------|-------|
| Web | 5173 | SvelteKit app |
| Races API | 8080 | Production-shaped API used by the frontend |
| Pipeline dev API | 8001 | Local-only in-process agent runner |
| MCP server | stdio | Optional local assistant/tool integration backed by Races API |

## Manual Start

Terminal 1, pipeline dev API:

```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn pipeline_client.backend.main:app --host 0.0.0.0 --port 8001 --reload
```

Terminal 2, races API:

```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn main:app --app-dir services/races-api --host 0.0.0.0 --port 8080 --reload
```

The `services/races-api` directory is not currently an importable Python package because of the hyphen in its name, so use `--app-dir` for local uvicorn runs.

Terminal 3, web:

```powershell
cd web
npm run dev -- --host 0.0.0.0 --port 5173
```

Optional MCP server, backed by the Races API:

```powershell
python -m venv .venv-mcp
.venv-mcp\Scripts\Activate.ps1
pip install -r requirements-mcp.txt
$env:SMARTERVOTE_RACES_API_URL = "http://127.0.0.1:8080"
python -m smartervote_mcp.server
```

The separate `.venv-mcp` keeps MCP SDK dependency updates from changing the pinned FastAPI/races-api environment.

For local admin tools, start `races-api` with `SKIP_AUTH=true`, or set `SMARTERVOTE_RACES_API_TOKEN`
to a valid Auth0 bearer token for a deployed API. `SMARTERVOTE_RACES_API_ADMIN_KEY` is also forwarded
as `X-Admin-Key` for legacy admin-key endpoints such as analytics/cache operations.

For a long-running local HTTP MCP endpoint instead of stdio, set:

```powershell
$env:SMARTERVOTE_MCP_TRANSPORT = "streamable-http"
python -m smartervote_mcp.server
```

The default endpoint is `http://127.0.0.1:8000/mcp`.

Example MCP client config:

```json
{
  "mcpServers": {
    "smartervote-races": {
      "command": ".venv-mcp/Scripts/python.exe",
      "args": ["-m", "smartervote_mcp.server"],
      "env": {
        "SMARTERVOTE_RACES_API_URL": "http://127.0.0.1:8080"
      }
    }
  }
}
```

Use absolute paths for `command` or set the client working directory if your MCP client does not launch
servers from the repository root.

For Codex against the deployed dev races API, use the GCP launcher so the admin key is fetched from
Secret Manager at startup instead of being stored in Codex config:

```powershell
codex mcp add smartervote-races `
  --env SMARTERVOTE_RACES_API_URL=https://races-api-dev-ddsvfazica-uc.a.run.app `
  --env SMARTERVOTE_GCP_PROJECT=smartervote `
  --env SMARTERVOTE_GCP_ENVIRONMENT=dev `
  -- .venv-mcp\Scripts\python.exe -m smartervote_mcp.gcp_launcher
```

The launcher requires local `gcloud` auth with access to `races-api-admin-key-dev`.

## Using the App

- Homepage: `http://localhost:5173`
- Admin dashboard: `http://localhost:5173/admin/pipeline`
- Races API health: `http://localhost:8080/health`
- Pipeline dev API health: `http://localhost:8001/health`

The admin UI should target `races-api` for production-shaped admin behavior. The pipeline dev API is retained only for local direct runs and debugging.

## Race IDs

Race IDs should match:

```text
{state}-{office}-{year}
```

Examples:

- `az-senate-2026`
- `ga-governor-2026`
- `ny-04-house-2026`

## Checks

```powershell
$env:PYTHONPATH = "."
python -m pytest

cd web
npm ci
npm run check
npm run build
npm run test:unit -- --run
```

## Troubleshooting

### `OPENROUTER_API_KEY is not set`

Make sure `.env` exists in the project root and that the server was started from the project root or with the documented `--app-dir` command.

### OpenRouter `429` or insufficient quota

The key is valid but the account lacks credits or quota. Add credits or adjust limits in OpenRouter.

### Port Conflicts

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### Import Errors

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e shared/
```

### Force Fresh Search Results

```powershell
Remove-Item -Recurse -Force data\cache
```

## Production Notes

In production, the admin dashboard queues races through `services/races-api`. A Firestore `pipeline_queue` document triggers the Cloud Function in `functions/agent`, which calls `AgentHandler` and writes draft output to GCS. The local pipeline API does not run in production.
