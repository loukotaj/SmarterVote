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
ANTHROPIC_API_KEY=your_key
XAI_API_KEY=your_key
SERPER_API_KEY=your_key

# Optional
CHROMA_PERSIST_DIR=./data/chroma_db
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

## Running the Pipeline

### Full Pipeline

```powershell
# Run all 4 steps for a race
python pipeline_client/run.py mo-senate-2024
```

### Individual Steps

```powershell
python pipeline_client/run.py mo-senate-2024 --step step01_metadata
python pipeline_client/run.py mo-senate-2024 --step step02_corpus
python pipeline_client/run.py mo-senate-2024 --step step03_summarise
python pipeline_client/run.py mo-senate-2024 --step step04_publish
```

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

## Project Structure

```
data/
├── chroma_db/      # Vector database
└── published/      # Output JSON files

pipeline/
└── app/            # Core pipeline modules

pipeline_client/
├── backend/        # Step handlers
└── run.py          # Main entry point

services/
└── races-api/      # REST API

web/                # SvelteKit frontend
```

## Configuration

Key environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | GPT models | Required |
| `ANTHROPIC_API_KEY` | Claude models | Required |
| `XAI_API_KEY` | Grok models | Required |
| `SERPER_API_KEY` | Web search | Required |
| `SMARTERVOTE_CHEAP_MODE` | Use mini models | `true` |
| `CHROMA_PERSIST_DIR` | Vector DB path | `./data/chroma_db` |

## Troubleshooting

**ChromaDB errors**: Ensure `data/chroma_db/` exists and is writable.

**API key errors**: Check `.env` file exists and keys are valid.

**Port conflicts**: Default ports are 8000 (API) and 5173 (web).

**Import errors**: Ensure you're in the virtual environment (`.venv\Scripts\Activate.ps1`).
