# SmarterVote AI Assistant Instructions

## 🏗️ Architecture Overview

SmarterVote is a **corpus-first AI pipeline** for electoral analysis with three main components:
- **Pipeline** (`pipeline/`): Python-based 7-step processing engine using Pydantic models
- **Services** (`services/`): FastAPI microservices for enqueue-api and races-api
- **Web** (`web/`): SvelteKit + TypeScript frontend with static site generation

## 🔄 Core Processing Workflow

The pipeline follows a strict 7-step sequence (see `pipeline/app/__main__.py`):
1. **DISCOVER** → 2. **FETCH** → 3. **EXTRACT** → 4. **CORPUS** → 5. **SUMMARIZE** → 6. **ARBITRATE** → 7. **PUBLISH**

Each step has its own service class (e.g., `DiscoveryService`, `FetchService`) and processes data through the `ProcessingJob` schema.

## 📊 Data Standards

### RaceJSON v0.2 Format
All race data follows the standardized schema in `pipeline/app/schema.py`:
- **11 Canonical Issues**: Healthcare, Economy, Climate/Energy, etc. (see `CanonicalIssue` enum)
- **Confidence Levels**: `high|medium|low|unknown` based on 2-of-3 LLM consensus
- **Source Types**: website, pdf, api, social_media, news, government, fresh_search

### Key Pydantic Models
- `RaceJSON`: Complete race analysis output
- `Candidate`: Individual candidate with issue stances
- `IssueStance`: Position on canonical issue with confidence + sources
- `ProcessingJob`: Pipeline execution state tracking

## 🛠️ Development Patterns

### Local Development Workflow
```bash
# Pipeline testing
python scripts/run_local.py <race-id>
python scripts/validate_project.py

# Web development
cd web && npm run dev
npm run check  # Svelte type checking

# Infrastructure
cd infra && terraform plan
```

### Multi-LLM Triangulation
The system uses 3 AI models (GPT-4o, Claude-3.5, grok-3) for consensus:
- **2-of-3 agreement** = HIGH confidence
- **Partial consensus** = MEDIUM confidence
- **No consensus** = LOW confidence (minority view stored)

### Testing Conventions
- **Pipeline**: pytest with async tests, mock external services
- **Services**: FastAPI TestClient for endpoint testing
- **Web**: Playwright for integration, Vitest for units
- Path setup: `sys.path.insert(0, str(Path(__file__).parent.parent.parent))`

## 🏗️ Infrastructure & Deployment

### Terraform Architecture
- **GCP-based**: Cloud Run services, Pub/Sub messaging, Secret Manager
- **Multi-environment**: Uses `var.environment` for dev/staging/prod isolation
- **API Keys**: Stored in `secrets.tfvars` (never commit), deployed via Secret Manager

### Service Communication
- **Enqueue API** → publishes jobs to Pub/Sub → triggers pipeline Cloud Run
- **Races API** → serves processed RaceJSON data from Cloud Storage
- **Web Frontend** → static site consuming races-api data

## 💻 Code Quality & Conventions

### Python Standards
- **Formatting**: Black + isort for consistent imports
- **Type Hints**: Pydantic models for data validation, async/await patterns
- **Logging**: Structured logging with module-level loggers
- **Error Handling**: Graceful degradation with confidence scoring

### TypeScript/Svelte Patterns
- **Type Safety**: Shared types in `web/src/lib/types.ts` mirror Python schemas
- **Component Structure**: Use `+page.svelte` for routes, components in `lib/components/`
- **Static Generation**: `@sveltejs/adapter-static` for GitHub Pages deployment

## 📂 Key Files for Context

- `pipeline/app/schema.py` - Core data models and enums
- `pipeline/app/__main__.py` - Pipeline orchestration and workflow
- `web/src/lib/types.ts` - Frontend type definitions
- `scripts/run_local.py` - Local development execution
- `infra/main.tf` - Infrastructure as code patterns
- `docs/architecture.md` - Detailed system design
- `docs/issues-list.md` - Current development priorities

## 🎯 Project-Specific Considerations

- **Corpus-First**: Always build vector database before analysis (ChromaDB integration)
- **Bias Reduction**: Multi-model consensus is core to accuracy - never use single LLM
- **11 Canonical Issues**: Maintain consistency across all races for comparability
- **Source Attribution**: Track content lineage for transparency and validation
- **Confidence Scoring**: Include reliability metrics in all analysis outputs
