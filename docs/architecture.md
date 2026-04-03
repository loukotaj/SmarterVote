# SmarterVote Architecture

**Multi-Phase AI Agent for Electoral Analysis**

## Overview

SmarterVote uses an AI research agent to produce structured candidate profiles for U.S. election races. The agent uses OpenAI function calling with Serper web search to gather information across seven pipeline steps, producing RaceJSON v0.3 output with policy stances, source URLs, and confidence levels.

## Agent Phases

```
DISCOVERY → IMAGES → ISSUES (×12 per-candidate) → FINANCE → REFINEMENT → REVIEW (optional) → ITERATION
```

### Step 1: Discovery (15% weight)
- Identify the race (office, jurisdiction, election date)
- Find all candidates (name, party, incumbent status)
- Locate campaign websites, social media, career history
- Write brief nonpartisan summaries
- Gather polling data if available

### Step 2: Image Resolution (5% weight)
- Verify/find direct image URLs per candidate
- Sources: Wikipedia, house.gov, Ballotpedia, official campaign sites

### Step 3: Issue Research (35% weight)
- 12 per-candidate sub-agent calls (one per canonical issue)
- Each call searches the web for a candidate's position on a single issue
- Returns stance, confidence level, and source URLs per candidate per issue

### Step 4: Finance & Voting (10% weight)
- Dedicated donor and voting-record research per candidate
- FEC filings, campaign finance databases, legislative voting records

### Step 5: Refinement (15% weight)
- Tools-mode per-candidate and meta cleanup
- Verify and fix factual inconsistencies via additional web searches
- Fill in weak/missing stances
- Improve candidate summaries
- Ensure all 12 issues are covered for each candidate

### Step 6: AI Review (12% weight, optional)
- Send results to Claude, Gemini, and Grok for independent fact-checking
- Returns `AgentReview[]` with flags and verdict per reviewer
- Computes `ValidationGrade` (A–F) from combined scores

### Step 7: Review Iteration (8% weight)
- Tools-mode pass to address review flags
- Up to 2 cycles of corrections based on reviewer feedback

### Update/Rerun Mode
When a published profile already exists for a race, the agent enters update mode:
- Adds Phase 0: **Roster Sync** (sync candidate list) + **Meta Update** (refresh race metadata)
- Runs the same steps but reuses existing data as context
- Images phase runs after refinement instead of after discovery
- Each issue is re-researched with existing stances as context

## Components

```
pipeline_client/agent/              # AI research agent
├── agent.py              # Agent loop, multi-phase orchestration, search + fetch
├── prompts.py            # Phase-specific prompt templates
├── tools.py              # Tool definitions for agent tool-use loop
├── handlers.py           # LLM request/response handling, JSON extraction
├── review.py             # Multi-LLM review (Claude, Gemini, Grok) + ValidationGrade
├── images.py             # Candidate image URL resolution strategies
├── ballotpedia.py        # Ballotpedia lookup helper
├── search_cache.py       # SQLite cache for Serper results (7-day TTL)
├── cost.py               # Token counting + cost estimation per model
└── utils.py              # Logging, JSON extraction utilities

pipeline_client/          # Execution engine
├── backend/
│   ├── handlers/
│   │   └── agent.py      # AgentHandler — wraps run_agent() with progress updates
│   ├── main.py            # FastAPI app — 40+ endpoints, Auth0, WebSocket
│   ├── models.py          # PipelineStep enum, RunOptions, RunInfo, RunStep
│   ├── pipeline_runner.py # Async step execution, logging, artifact saving
│   ├── step_registry.py   # Handler registry (step name → StepHandler)
│   ├── run_manager.py     # Run lifecycle (in-memory active, Firestore completed)
│   ├── queue_manager.py   # Persistent queue (Firestore cloud / JSON local)
│   ├── race_manager.py    # Unified race records + metadata + run history
│   ├── settings.py        # Pydantic Settings from env (storage mode, auth, etc.)
│   ├── logging_manager.py # WebSocket log broadcasting
│   ├── storage.py         # Artifact + race JSON storage routing
│   ├── storage_backend.py # LocalStorageBackend / GCPStorageBackend
│   ├── alerts.py          # Monitoring and alerting (optional)
│   └── pipeline_metrics.py# Token usage + cost tracking (optional)
└── run.py                 # CLI entry point

services/
└── races-api/             # Public REST API serving published data

shared/
└── models.py              # Pydantic v2 models (RaceJSON, Candidate, CanonicalIssue)

web/                       # SvelteKit frontend (static, deployed to GitHub Pages)
└── src/lib/types.ts       # TypeScript types (must sync with shared/models.py)
```

## AI Model Configuration

| Mode | Research Model | Sub-task Model | Use Case |
|------|---------------|----------------|----------|
| Cheap (default) | gpt-5.4-mini | gpt-5-nano | Fast, low-cost research |
| Standard | gpt-5.4 | gpt-5.4-mini | Higher quality research |

### Review Models

| Provider | Cheap Mode | Full Mode |
|----------|-----------|-----------|
| Claude | claude-haiku-4-5-20251001 | claude-sonnet-4-6 |
| Gemini | gemini-3.1-flash-lite-preview | gemini-3-flash-preview |
| Grok | grok-3-mini | grok-3 |

**Configuration**: `cheap_mode=true` (default) in RunOptions. Override specific models via `research_model`, `claude_model`, `gemini_model`, `grok_model`.

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
Race ID (e.g., ga-senate-2026)
    ↓
Step 1: Discover candidates, career history, polls via web search
    ↓
Step 2: Resolve candidate headshot image URLs
    ↓
Step 3: Research 12 issues per candidate (12 × N sub-agent calls)
    ↓
Step 4: Research finance + voting records per candidate
    ↓
Step 5: Refine and clean full profile via tools-mode passes
    ↓
Step 6 (optional): Multi-LLM review (Claude + Gemini + Grok)
    ↓
Step 7: Address review flags (up to 2 iterations)
    ↓
Save draft RaceJSON → admin publishes → Races API serves it
```

## Storage

### Local Dev

| Location | Use |
|----------|-----|
| `data/published/` | Published race profiles (JSON) |
| `data/drafts/` | Agent output before publish |
| `data/cache/` | Search cache (SQLite, 7-day TTL) |
| `pipeline_client/artifacts/` | Per-run RunResponse snapshots |
| `pipeline_client/queue.json` | Queue state (JSON file) |
| In-memory | Active runs + race records (lost on restart) |

### Cloud (GCP)

| Service | Use |
|---------|-----|
| GCS `races/` | Published race profiles |
| GCS `drafts/` | Agent output before publish |
| Firestore `pipeline_runs/` | Completed run records |
| Firestore `races/` | Race metadata + run history |
| Firestore `pipeline_queue` | Queue items |
| Secret Manager | API keys |

## Pipeline Client API Endpoints (Auth0-protected except `/health`)

### Race Management (`/api/races/`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/races` | List all races with metadata |
| GET | `/api/races/{race_id}` | Get race metadata + status |
| DELETE | `/api/races/{race_id}` | Delete a race |
| POST | `/api/races/queue` | Add race_ids to batch queue |
| POST | `/api/races/{race_id}/run` | Run agent for a race |
| POST | `/api/races/{race_id}/cancel` | Cancel queued/running race |
| POST | `/api/races/{race_id}/recheck` | Re-check race status |
| POST | `/api/races/{race_id}/publish` | Promote draft → published |
| POST | `/api/races/{race_id}/unpublish` | Move published → draft |
| GET | `/api/races/{race_id}/runs` | List runs for a race |
| GET | `/api/races/{race_id}/runs/{run_id}` | Get specific run for a race |
| DELETE | `/api/races/{race_id}/runs/{run_id}` | Delete a run |
| GET | `/api/races/{race_id}/data` | Get race JSON data |

### Legacy / Quick-access

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/run` | Start agent run (legacy) |
| GET | `/races` | List published races |
| GET | `/races/{race_id}` | Get published race |
| DELETE | `/races/{race_id}` | Delete published race |
| GET | `/drafts` | List all drafts |
| GET | `/drafts/{race_id}` | Get a draft |
| DELETE | `/drafts/{race_id}` | Delete a draft |
| POST | `/drafts/{race_id}/publish` | Publish a draft |
| POST | `/races/{race_id}/unpublish` | Unpublish a race |

### Pipeline Infrastructure

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/queue` | List queue items |
| POST | `/queue` | Add to queue |
| DELETE | `/queue/{item_id}` | Remove queue item |
| DELETE | `/queue/finished` | Clear finished queue items |
| GET | `/runs` | List recent runs |
| GET | `/runs/active` | List active runs |
| GET | `/runs/{run_id}` | Get run details |
| DELETE | `/runs/{run_id}` | Delete a run |
| GET | `/run/{run_id}` | Get run info (alt) |
| POST | `/run/{step}` | Run a named pipeline step |
| GET | `/steps` | List available pipeline steps |
| GET | `/artifacts` | List artifacts |
| GET | `/artifacts/{artifact_id}` | Get artifact |
| GET | `/artifact/{artifact_id}` | Get artifact (alt) |
| GET | `/health` | Health check (unauthenticated) |

### Monitoring

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/alerts` | Active alerts |
| POST | `/alerts/{alert_id}/acknowledge` | Acknowledge alert |
| GET | `/analytics/overview` | Request analytics overview |
| GET | `/analytics/races` | Per-race request counts |
| GET | `/analytics/timeseries` | Request timeseries |
| GET | `/pipeline/metrics` | Token usage + cost metrics |
| GET | `/pipeline/metrics/summary` | Metrics summary |

### WebSocket

| Path | Purpose |
|------|---------|
| `/ws/logs` | Live log streaming (all runs) |
| `/ws/logs/{run_id}` | Live logs for a specific run |

## Races API Endpoints (Public)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/races` | None | List race IDs |
| GET | `/races/summaries` | None | Race summaries for search |
| GET | `/races/{race_id}` | None | Full race data |
| POST | `/cache/clear` | X-Admin-Key | Clear GCS cache |
| GET | `/analytics/overview` | X-Admin-Key | Request stats |
| GET | `/analytics/races` | X-Admin-Key | Per-race request counts |
| GET | `/analytics/timeseries` | X-Admin-Key | Request timeseries |

## Infrastructure (Terraform)

Located in `infra/`. Pipeline client disabled by default (`enable_pipeline_client = false`).

When enabled:
- **Cloud Run**: races-api (public), pipeline-client (Auth0-protected)
- **GCS**: Data bucket (`races/`, `drafts/`, `analytics/`)
- **Firestore**: Run history, race metadata, queue persistence
- **Secret Manager**: API keys (openai, serper, anthropic, gemini, xai, admin)
- **Artifact Registry**: Docker images (keeps 5 versions, deletes >30 days)

## Canonical Issues

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

Defined in `shared/models.py` as `CanonicalIssue` enum and `pipeline_client/agent/prompts.py`.
