# SmarterVote

**AI-Powered Electoral Analysis Platform** 🗳️

SmarterVote transforms how voters access candidate information through advanced AI analysis and corpus-first data processing. Our platform aggregates, processes, and synthesizes electoral race data to provide comprehensive, unbiased candidate comparisons across 11 canonical political issues.


## 🎯 Project Overview

SmarterVote employs a sophisticated **corpus-first approach** to electoral analysis:

1. **Intelligent Discovery**: Multi-source content discovery including fresh issue-specific searches
2. **Content Processing**: Advanced extraction from HTML, PDF, and structured data
3. **Vector Corpus**: ChromaDB-powered semantic search and content indexing
4. **AI Triangulation**: Multiple LLM consensus for accuracy and bias reduction
5. **Confidence Scoring**: 2-of-3 arbitration with reliability metrics
6. **Standardized Output**: Structured RaceJSON format for consistent analysis

## ⚡ Quick Start

### Prerequisites
- **Python**: 3.10+ (Pipeline and services)
- **Node.js**: 22.0+ (Web frontend)
- **Docker**: Container runtime
- **Terraform**: 1.5+ (Infrastructure as Code)
- **Google Cloud SDK**: For cloud deployment

### 🏃‍♂️ Local Development

1. **Clone and setup**
   ```bash
   git clone https://github.com/loukotaj/SmarterVote.git
   cd SmarterVote

   # Copy environment template
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

2. **Install dependencies**
   ```bash
   # Python environment
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # macOS/Linux
   pip install -r pipeline/requirements.txt

   # Web frontend
   cd web && npm install && cd ..
   ```

3. **Test Vector Database**
   ```bash
   # Verify ChromaDB setup
   python test_vector_db.py
   ```

4. **Start development services**
   ```bash
   # All services (Windows PowerShell)
   .\dev-start.ps1

   # Or individually:
   # Races API: cd services/races-api && python main.py
   # Web: cd web && npm run dev
   python scripts/run_local.py
   ```

5. **Set up development environment with pre-commit hooks**
   ```bash
   # For Windows users
   .\setup-dev.ps1

   # For Unix/Linux/macOS users
   python scripts/setup_dev.py
   ```

6. **Validate project health**
   ```bash
   python scripts/validate_project.py
   ```

## 🏗️ Architecture Overview

### Core Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Pipeline** | Python + Pydantic | Corpus-first AI processing engine |
| **Services** | FastAPI + Cloud Run | Microservices for API endpoints |
| **Web Frontend** | SvelteKit + TypeScript | Modern responsive user interface |
| **Infrastructure** | Terraform + GCP | Cloud-native resource management |
| **Data Storage** | ChromaDB + Cloud Storage | Vector database and file storage |

### Processing Workflow

```mermaid
graph LR
    A[Discover] --> B[Fetch]
    B --> C[Extract]
    C --> D[Corpus]
    D --> E[Summarize]
    E --> F[Arbitrate]
    F --> G[Publish]
```

**7-Step Pipeline:**
1. **DISCOVER** - Seed URLs + Google dorks + Fresh issue search
2. **FETCH** - Download raw content from sources
3. **EXTRACT** - Convert HTML/PDF to plain text
4. **CORPUS** - Index content in ChromaDB vector database
5. **SUMMARIZE** - RAG + 3-model LLM triangulation
6. **ARBITRATE** - 2-of-3 consensus with confidence scoring
7. **PUBLISH** - Generate standardized RaceJSON v0.2

## 📊 Data Standards

### Canonical Issues Framework
Our analysis focuses on 11 consistent political issues:
- Healthcare
- Economy
- Climate/Energy
- Reproductive Rights
- Immigration
- Guns & Safety
- Foreign Policy
- Social Justice
- Education
- Tech & AI
- Election Reform

### RaceJSON v0.2 Format
Standardized output format ensuring consistent candidate comparisons across all electoral races. The schema includes:

- **Candidate Information**: Name, party, website, key positions
- **Issue Analysis**: Stances on all 11 canonical political issues
- **Confidence Scoring**: AI consensus levels (HIGH/MEDIUM/LOW)
- **Source Attribution**: Transparent sourcing for all claims
- **Processing Metadata**: Timestamps, version info, and audit trails

## 🔧 Development Tools

### Code Quality
- **Python**: Black formatting, isort imports, pytest testing
- **TypeScript**: ESLint, Prettier, Svelte-check
- **Infrastructure**: Terraform validate, plan verification
- **Pre-commit Hooks**: Automated code formatting and linting before commits

### Project Health Validation
```bash
# Validate project structure and imports
python scripts/validate_project.py

# Run all tests
python -m pytest -v

# Check code formatting
black --check pipeline/
npm run lint                     # From web/ directory

# Validate infrastructure
cd infra && terraform validate
```

### CI/CD Pipeline
- **GitHub Actions**: Automated testing and deployment
- **Multi-environment**: Dev, staging, production workflows
- **Quality Gates**: Code quality, security, and performance checks

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [`docs/architecture.md`](docs/architecture.md) | Detailed system architecture and design patterns |
| [`docs/issues-list.md`](docs/issues-list.md) | Current development priorities and feature roadmap |
| [`docs/testing.md`](docs/testing.md) | Testing strategy and test organization |
| [`infra/README.md`](infra/README.md) | Infrastructure deployment and management guide |
| [`web/README.md`](web/README.md) | Frontend development and deployment instructions |
| [`AGENTS.md`](AGENTS.md) | AI agent instructions and development guidelines |

## 🤝 Contributing

We welcome contributions! Please ensure:

1. **Code Quality**: Run linting and formatting tools
2. **Testing**: Add tests for new features
3. **Documentation**: Update relevant docs with changes
4. **CI/CD**: Ensure all GitHub Actions workflows pass

### Development Workflow
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Set up pre-commit hooks (first time only)
pre-commit install

# Make your changes - pre-commit will run automatically on commit
# Or run manually:
pre-commit run --all-files

# Run tests (now adjacent to source code)
python -m pytest                    # All Python tests
python -m pytest pipeline/          # Pipeline unit tests
python -m pytest services/          # Service tests
python -m pytest tests/             # Integration tests
npm test                            # Web frontend tests

# Format and lint
npm run format        # Frontend formatting
black pipeline/       # Python formatting

# Submit pull request
```

## 🛡️ Security & Compliance

- **API Keys**: Stored in Google Secret Manager
- **Data Privacy**: No personally identifiable information stored
- **Content Sourcing**: Public electoral information only
- **AI Ethics**: Multi-model consensus to reduce bias

## 📈 Performance & Scaling

- **Serverless Architecture**: Auto-scaling Cloud Run services
- **Vector Database**: ChromaDB for efficient similarity search
- **CDN Delivery**: Static site optimized for global distribution
- **Monitoring**: Cloud Logging and error tracking

## 📄 License

This project is licensed under CC BY-NC-SA 4.0- see the [LICENSE](LICENSE) file for details.

---

**Built with ❤️ for democracy and informed voting**

*Last updated: August 2025*
