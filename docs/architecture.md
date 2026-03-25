# SmarterVote Architecture

**Multi-Phase AI Agent for Electoral Analysis**

## Overview

SmarterVote uses an AI research agent to produce structured candidate profiles for U.S. election races. The agent uses OpenAI function calling with Serper web search to gather information across three phases, producing RaceJSON v0.2 output with policy stances, source URLs, and confidence levels.

## Agent Phases

```
DISCOVER → RESEARCH (×6 issue groups) → REFINE
```

### Phase 1: Discovery (1 LLM call)
- Identify the race (office, jurisdiction, election date)
- Find all candidates (name, party, incumbent status)
- Locate campaign websites and social media
- Write brief nonpartisan summaries

### Phase 2: Issue Research (6 LLM calls)
- One focused call per issue-group pair:
  - Healthcare + Reproductive Rights
  - Economy + Education
  - Climate/Energy + Tech & AI
  - Immigration + Foreign Policy
  - Guns & Safety + Social Justice
  - Election Reform + Local Issues
- Each call searches the web for candidate positions on those 2 issues
- Returns stance, confidence level, and source URLs per candidate

### Phase 3: Refinement (1 LLM call)
- Merge all issue research into the full profile
- Verify and fix factual inconsistencies via additional web searches
- Fill in weak/missing stances
- Improve candidate summaries
- Add top donor information if findable
- Ensure all 12 issues are covered for each candidate

**Total: 8 LLM calls per fresh run.**

### Update/Rerun Mode
When a published profile already exists for a race (`data/published/{race_id}.json`), the agent enters update mode:
- Searches for new developments since last update
- Verifies existing stances still hold
- Fills in missing or weak positions
- Single LLM call with the existing profile as context

## Components

```
pipeline_v2/              # AI research agent
├── agent.py              # Agent loop, search caching, multi-phase orchestration
└── prompts.py            # Phase-specific prompt templates

pipeline_client/          # Execution engine
├── backend/
│   ├── handlers/
│   │   └── v2_agent.py   # Agent step handler
│   ├── main.py           # FastAPI API (POST /api/v2/run)
│   ├── pipeline_runner.py  # Step execution + logging
│   ├── step_registry.py  # Handler registry
│   ├── run_manager.py    # Run lifecycle management
│   ├── logging_manager.py  # WebSocket log broadcasting
│   ├── storage.py        # Artifact storage
│   └── storage_backend.py  # Local/GCP storage abstraction
└── run.py                # CLI entry point

services/
└── races-api/            # REST API serving published data

shared/
└── models.py             # Pydantic models (Candidate, Race, CanonicalIssue)

web/                      # SvelteKit frontend
└── src/lib/types.ts      # TypeScript types (must sync with shared/models.py)
```

## AI Model Configuration

| Mode | Model | Use Case |
|------|-------|----------|
| Cheap (default) | gpt-4.1-mini | Fast, low-cost research |
| Standard | gpt-4.1 | Higher quality research |

**Configuration**:
- `SMARTERVOTE_CHEAP_MODE=true` (default) — Use gpt-4.1-mini
- Set to `false` for gpt-4.1

## Confidence Levels

| Level | Criteria |
|-------|----------|
| HIGH | Multiple corroborating sources or official campaign position |
| MEDIUM | Single credible source |
| LOW | Inferred or unverified |

## Search Caching

Web search results are cached in a SQLite database to avoid redundant Serper API calls:

- **Location**: `data/cache/search_cache.db` (configurable)
- **TTL**: 7 days (configurable via `SEARCH_CACHE_TTL_HOURS`)
- **Scope**: Cached per query string, optionally tagged by race_id
- **Benefit**: Re-runs and iterative development don't waste search API calls

## Data Flow

```
Race ID (e.g., mo-senate-2024)
    ↓
Phase 1: Discover candidates via web search
    ↓
Phase 2: Research 12 issues across 6 focused calls
    ↓
Phase 3: Refine, verify, and improve the profile
    ↓
Publish RaceJSON to data/published/
    ↓
Races API serves data to web frontend
```

## Storage

| Backend | Location | Use |
|---------|----------|-----|
| Local | `data/published/` | Published race profiles |
| Local | `data/cache/` | Search cache (SQLite) |
| GCS | `gs://bucket/races/` | Production (cloud mode) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v2/run` | Start agent research for a race |
| GET | `/runs` | List recent runs |
| GET | `/runs/{run_id}` | Get run details |
| DELETE | `/runs/{run_id}` | Cancel a run |
| GET | `/artifacts` | List artifacts |
| GET | `/health` | Health check |
| WS | `/ws/logs` | Live log streaming |

## Infrastructure (Terraform)

Located in `infra/`. Disabled by default (`enable_pipeline_client = false`).

When enabled:
- Cloud Run: races-api, pipeline-client
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

Defined in `shared/models.py` as `CanonicalIssue` enum and `pipeline_v2/prompts.py`.
