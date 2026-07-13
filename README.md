# SmarterVote

AI-powered candidate research for U.S. elections.

SmarterVote uses a multi-phase AI agent to research election races and produce structured candidate profiles covering 12 policy issues, with sources, confidence levels, and optional multi-LLM review.

## Requirements

- Python 3.10+
- Node.js 22+
- `OPENROUTER_API_KEY` and `SERPER_API_KEY` for agent runs; `SEARLO_API_KEY` enables the search fallback when Serper credits are exhausted

## Local Development

```powershell
pip install -r requirements.txt
pip install -e shared/
copy .env.example .env

cd web
npm ci
cd ..

.\dev-start.ps1
```

Local services:

- Web app: `http://localhost:5173`
- Races API: `http://localhost:8080`
- Local-only pipeline dev API: `http://localhost:8001`

The admin dashboard is available at `http://localhost:5173/admin/pipeline`.

## Current Architecture

- **Production admin/public API**: `services/races-api`
- **Production agent execution**: `races-api` queue item -> one-shot Cloud Run Job -> `pipeline_client.worker` -> `AgentHandler`
- **Shared agent library**: `pipeline_client/agent`
- **Shared schema**: `shared/models.py`
- **Frontend**: `web`, which should target `races-api` for admin and public operations
- **Local-only development API**: `pipeline_client/backend/main.py`, retained for local agent iteration and debugging

The previous pipeline client API is no longer the production API surface. New admin API behavior should be added to `services/races-api` first, then mirrored locally only when useful for development.

## Data Flow

Production:

```text
Admin dashboard -> races-api queue endpoint -> Firestore pipeline_queue
    -> Cloud Run Job -> shared queue processor -> AgentHandler -> GCS drafts/{race_id}.json
    -> admin publish -> GCS races/{race_id}.json -> public races API
```

Local development:

```text
Admin dashboard -> local races-api
Direct runner debugging -> local pipeline dev API -> in-process agent run
```

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

For the broad local gate sequence, run:

```powershell
.\scripts\run-ci-gates.ps1
```

## Docs

- [Documentation map](docs/README.md) — current operational guides, plans, and historical records
- [Architecture](docs/architecture.md)
- [Local Development](docs/local-development.md)
- [Deployment](docs/deployment-guide.md)
- [Auth0 Configuration](docs/auth0-configuration.md)
- [IndexNow](docs/indexnow.md)
- [Pipeline Modes](PIPELINE_MODES.md)

## License

CC BY-NC-SA 4.0. See `LICENSE`.
