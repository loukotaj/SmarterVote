# SmarterVote Architecture

**Corpus-First AI Pipeline for Electoral Analysis**

## Overview

SmarterVote processes electoral data through a 4-stage pipeline that builds semantic understanding before generating summaries. Multiple AI models validate outputs for reliability.

## Pipeline Flow

```
INGEST → CORPUS → SUMMARIZE → PUBLISH
```

### Stage 1: INGEST (`step01_*`)
- **Discovery**: Find candidate websites, news, social media via Serper/Google Search
- **Fetch**: Download content with rate limiting and retries
- **Extract**: Parse HTML/PDF to clean text
- **Metadata**: Build race structure (candidates, office, jurisdiction)

### Stage 2: CORPUS (`step02_corpus`)
- **Embedding**: Generate vectors for all extracted content
- **Storage**: Index in ChromaDB for semantic search
- **Retrieval**: Support RAG queries for summarization

### Stage 3: SUMMARIZE (`step03_summarise`)
- **Multi-LLM Query**: Send prompts to GPT-4o, Claude-3.5, grok-3
- **Issue Extraction**: Get positions on 12 canonical issues per candidate
- **Consensus**: 2-of-3 agreement for confidence scoring
- **Arbitration**: Resolve conflicts, assign confidence levels

### Stage 4: PUBLISH (`step04_publish`)
- **Format**: Generate RaceJSON v0.2
- **Store**: Write to local files or GCS
- **Validate**: Check schema compliance

## Components

```
pipeline/app/           # Core modules
├── providers/          # AI provider abstraction (OpenAI, Anthropic, xAI)
├── schema.py           # Pipeline data models
├── step01_ingest/      # Discovery, fetching, extraction
├── step02_corpus/      # Vector database operations
├── step03_summarise/   # LLM summarization + consensus
└── step04_publish/     # Output generation

pipeline_client/        # Execution engine
├── backend/
│   ├── handlers/       # Step handlers
│   └── main.py         # CLI entry point
└── run.py              # Main runner script

services/
├── races-api/          # REST API serving published data
└── enqueue-api/        # Job queue API (cloud mode)

shared/                 # Common models
└── models.py           # Pydantic models (Candidate, Race, CanonicalIssue)

web/                    # SvelteKit frontend
└── src/lib/types.ts    # TypeScript types (must sync with shared/models.py)
```

## AI Models

| Mode | Provider | Model | Use Case |
|------|----------|-------|----------|
| Local | Local | (configurable) | Free, offline testing |
| Cheap (default) | OpenAI | gpt-4o-mini | Fast, low-cost |
| Cheap | Anthropic | claude-3-haiku | Structured output |
| Cheap | xAI | grok-3-mini | Alternative view |
| Standard | OpenAI | gpt-4o | Higher quality |
| Standard | Anthropic | claude-3.5 | Best structure |
| Standard | xAI | grok-3 | Alternative view |

**Configuration**:
- `SMARTERVOTE_CHEAP_MODE=true` (default) - Use mini/cheap models
- `LOCAL_LLM_ENABLED=true` - Enable local LLM (Ollama, LM Studio)
- `LOCAL_LLM_BASE_URL=http://localhost:11434/v1` - Local server URL
- `LOCAL_LLM_MODEL=llama3.2:3b` - Model name

## Confidence Levels

| Level | Criteria |
|-------|----------|
| HIGH | 2+ models agree, quality sources |
| MEDIUM | Partial agreement or limited sources |
| LOW | Disagreement or contradictory info |

## Data Flow

```
Race ID (e.g., mo-senate-2024)
    ↓
Step 01: Discover sources, fetch content, extract text
    ↓
Step 02: Build vector corpus in ChromaDB
    ↓
Step 03: Query 3 LLMs, build consensus, assign confidence
    ↓
Step 04: Publish RaceJSON to data/published/
    ↓
Races API serves data to web frontend
```

## Storage

| Backend | Location | Use |
|---------|----------|-----|
| Local | `data/published/` | Development |
| Local | `data/chroma_db/` | Vector DB |
| GCS | `gs://bucket/races/` | Production |

## Infrastructure (Terraform)

Located in `infra/`. Disabled by default (`enable_pipeline_client = false`).

When enabled:
- Cloud Run: races-api, enqueue-api, pipeline-client
- Pub/Sub: Job queuing
- GCS: Data storage
- Secret Manager: API keys

## 12 Canonical Issues

1. Healthcare
2. Economy
3. Climate/Energy
4. Reproductive Rights
5. Immigration
6. Guns & Safety
7. Foreign Policy
8. Social Justice
9. Education
10. Tech & AI
11. Election Reform
12. Local Issues

Defined in `shared/models.py` as `CanonicalIssue` enum.
