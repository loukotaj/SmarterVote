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
SEARLO_API_KEY=your-searlo-key-here
SKIP_AUTH=true
```

Frontend environment variables (configured under `web/` in `.env` or `.env.production`):

- `VITE_RACES_API_URL`: FastAPI Races API base URL (defaults to `http://localhost:8080` in local dev).
- `VITE_PUBLIC_DATA_URL`: Optional public static GCS data folder path (e.g., `https://storage.googleapis.com/smartervote-sv-data-dev/races`). When configured, SvelteKit fetches published races and the central summaries index directly from GCS and does not fall back to `races-api` for public reads. Leave this unset in local development when you want to exercise the FastAPI public read routes.
- `VITE_CLOUDFLARE_WEB_ANALYTICS_TOKEN`: Optional public Cloudflare Web Analytics site token. The beacon is loaded only when this is set and the initial route is not `/admin`. Public/admin navigation links force a full reload so the SPA beacon does not remain active inside the admin console.

For deployed dashboard traffic reporting, configure the races API with:

- `CLOUDFLARE_ANALYTICS_API_TOKEN`: read-only Cloudflare GraphQL token
- `CLOUDFLARE_ANALYTICS_ACCOUNT_TAG`: Cloudflare account ID
- `CLOUDFLARE_ANALYTICS_SITE_TAG`: Web Analytics site/beacon token

Without all three values, `/analytics/traffic` returns `configured: false` so the dashboard does not mistake missing
configuration for zero traffic.

The deployed Agent tab uses durable Firestore records rather than browser session history:

- `admin_agent_conversations` stores conversation metadata.
- `admin_agent_messages` stores user, assistant, and tool messages.
- `admin_agent_tasks` triggers `functions/admin_agent/main.py`.

The worker calls the canonical races API with `ADMIN_API_KEY`, pauses protected operations for browser approval, and
creates continuation tasks before its Cloud Function deadline. Local API-only testing can exercise the conversation
endpoints, but asynchronous execution requires the Eventarc function or a locally invoked worker.

## One-command Start

```powershell
.\dev-start.ps1
```

Expected services:

| Service          | Port  | Notes                                                         |
| ---------------- | ----- | ------------------------------------------------------------- |
| Web              | 5173  | SvelteKit app                                                 |
| Races API        | 8080  | Production-shaped API used by the frontend                    |
| Pipeline dev API | 8001  | Local-only in-process agent runner                            |
| MCP server       | stdio | Optional local assistant/tool integration backed by Races API |

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

The `smartervote-races` MCP intentionally stays small: public race reads, admin race operations, queue/run
monitoring, pipeline metrics, cache/deploy operations, analytics, and broad chamber forecast operations. Prefer
adding reusable operations to the Races API and exposing them through MCP instead of committing ad hoc scripts.
One-off diagnostics should stay untracked locally; if they become useful enough to keep, promote the behavior into
API/MCP code with focused tests.

For local admin tools, start `races-api` with `SKIP_AUTH=true`, or set `SMARTERVOTE_RACES_API_TOKEN`
to a valid Auth0 bearer token for a deployed API. `SMARTERVOTE_RACES_API_ADMIN_KEY` is also forwarded
as `X-Admin-Key`; the races API accepts either a valid Auth0 bearer token or the configured admin key.

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

The launcher requires local `gcloud` auth with access to `races-api-admin-key-dev`. The deployed `races-api` service is publicly invokable at the Cloud Run layer and protected by FastAPI/Auth0/admin-key checks inside the app. If a future environment disables public invocation, set `SMARTERVOTE_RACES_API_USE_CLOUD_RUN_ID_TOKEN=true`; the active `gcloud` account will also need `roles/iam.serviceAccountTokenCreator` on `races-api-dev@smartervote.iam.gserviceaccount.com`, or set `SMARTERVOTE_RACES_API_IMPERSONATE_SERVICE_ACCOUNT` to another invoker service account with that grant.

## Using the App

- Homepage: `http://localhost:5173`
- Admin dashboard: `http://localhost:5173/admin/pipeline`
- Races API health: `http://localhost:8080/health`
- Pipeline dev API health: `http://localhost:8001/health`

The admin UI should target `races-api` for production-shaped admin behavior. The pipeline dev API is retained only for local direct runs and debugging.

Admin race list behavior:

- `/api/races` and `/api/races/drafts` read Firestore race catalog metadata.
- Public `/races` and `/races/summaries` read the published `summaries.json` index.
- Full public race pages read `races/{race_id}.json`.
- For existing data, run `POST /api/races/recheck` once after deploy or local startup to backfill Firestore catalog records from GCS draft/published JSON.

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

To run the same broad local gate sequence used by maintainers:

```powershell
.\scripts\run-ci-gates.ps1
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

In production, the admin dashboard queues races through `services/races-api`, which starts a one-shot Cloud Run Job using the shared worker and `AgentHandler`. For workstation-backed GCP runs, queue with `runner=local` and run `docker compose -f docker-compose.worker.yml up -d`. The local pipeline API does not run in production.
