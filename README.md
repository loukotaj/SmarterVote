# SmarterVote

AI-powered candidate research for U.S. elections.

SmarterVote uses a multi-phase AI agent to research election races and produce structured candidate profiles covering 12 policy issues — with sources, confidence levels, and optional multi-LLM review.

## Requirements

- Python 3.10+
- Node.js 22+
- `OPENAI_API_KEY` and `SERPER_API_KEY` (see `.env.example`)

## Getting Started

```bash
# Install dependencies and configure environment
pip install -r requirements.txt
pip install -e shared/
cp .env.example .env   # add your API keys

# Start the pipeline backend (from repo root)
python -m uvicorn pipeline_client.backend.main:app --port 8001 --reload

# Start the races API and web UI (separate terminals)
cd services/races-api && python main.py
cd web && npm install && npm run dev
```

The pipeline dashboard is available at `http://localhost:5173/admin/pipeline`.

## Docs

- [Architecture](docs/architecture.md)
- [Local Development](docs/local-development.md)
- [Deployment](docs/deployment-guide.md)

## License

CC BY-NC-SA 4.0 (see LICENSE)
