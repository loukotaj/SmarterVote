# SmarterVote

AI-powered candidate research for U.S. elections.

Live site: [smarter.vote](https://smarter.vote)

SmarterVote uses a multi-phase AI agent to research election races and produce structured candidate profiles covering 12 policy issues, with sources, confidence levels, and optional multi-LLM review.

## Requirements

- Python 3.11+
- Node.js 22+
- `OPENROUTER_API_KEY` and `SERPER_API_KEY` for agent runs; `SEARLO_API_KEY` enables the search fallback when Serper credits are exhausted; `JINA_API_KEY` gives page fetches an authenticated Jina Reader quota (without it the shared anonymous quota 403s for every host once spent, leaving all evidence at snippet tier)

## Local Development

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e shared/
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
- **Frontend**: `web`; production bundles the published GCS race snapshot into the Cloudflare Pages build, while admin operations target `races-api`
- **Local-only development API**: `pipeline_client/backend/main.py`, retained for local agent iteration and debugging

The previous pipeline client API is no longer the production API surface. New admin API behavior should be added to `services/races-api` first, then mirrored locally only when useful for development.

## Data Flow

Production:

```text
Admin dashboard -> races-api queue endpoint -> Firestore pipeline_queue
    -> Cloud Run Job -> shared queue processor -> AgentHandler -> GCS drafts/{race_id}.json
    -> admin publish -> GCS races/{race_id}.json
    -> Cloudflare deploy copies published JSON into the static site build
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

## Repository Layout Notes

- `web/static/summaries.json` and `web/static/chamber_forecasts.json` are deliberately minimal fixtures in Git. CI rewrites them and the Cloudflare deployment replaces them with current published data from GCS before building. The generated `web/static/sitemap.xml` is not tracked.
- `design-system/` is a private React export used only by the design-sync workflow. The production application is the SvelteKit project in `web/`; see [design-system/README.md](design-system/README.md).

## License

[CC BY-NC-SA 4.0](LICENSE).
