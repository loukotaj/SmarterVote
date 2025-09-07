# Local Development Setup for SmarterVote

This guide helps you set up the SmarterVote pipeline for local development with proper environment configuration.

## 📋 Prerequisites

- Python 3.10+
- Node.js 22+
- Git
- Google Cloud CLI (for production deployment)

## 🚀 Quick Start

### 1. Clone and Setup Repository

```bash
git clone https://github.com/loukotaj/SmarterVote.git
cd SmarterVote
```

### 2. Environment Configuration

Copy the environment template and configure for your setup:

```bash
cp .env.example .env
```

Edit the `.env` file with your configuration:

```bash
# ChromaDB Vector Database Configuration
CHROMA_CHUNK_SIZE=500
CHROMA_CHUNK_OVERLAP=50
CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2
CHROMA_SIMILARITY_THRESHOLD=0.7
CHROMA_MAX_RESULTS=100
CHROMA_PERSIST_DIR=./data/chroma_db

# LLM API Keys (Required for full pipeline functionality)
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
XAI_API_KEY=your_xai_grok_api_key_here

# Serper Search API (default web search provider)
SERPER_API_KEY=your_serper_api_key

# Google Search API (optional fallback)
GOOGLE_SEARCH_API_KEY=your_google_search_api_key
GOOGLE_SEARCH_CX=your_custom_search_engine_id

# Local Development Settings
ENVIRONMENT=development
LOG_LEVEL=DEBUG
DEBUG=true
```

### 3. Python Environment Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r pipeline/requirements.txt
```

### 4. Test Vector Database Setup

```bash
# Run vector database test
python -m pytest pipeline/app/step02_corpus/test_service.py::TestVectorDatabaseManager::test_build_corpus -v

# Run comprehensive tests
python -m pytest pipeline/app/step02_corpus/test_service.py -v
```

### 5. Start Development Services

#### Option A: Start All Services
```bash
# Windows PowerShell
.\dev-start.ps1
```

#### Option B: Start Individual Services

**Races API Only:**
```bash
cd services/races-api
python main.py
```

**Web Frontend Only:**
```bash
cd web
npm install
npm run dev
```

**Pipeline Components:**
```bash
cd pipeline
python -m pytest app/step02_corpus/test_service.py -v  # Test vector DB
```

## 🔧 Configuration Details

### ChromaDB Vector Database

The vector database is the core of SmarterVote's corpus-first approach:

- Storage: Local SQLite database at `./data/chroma_db/`
- Embedding Model: `all-MiniLM-L6-v2` (sentence transformers)
- Chunking: 500 words per chunk with 50-word overlap
- Search: Semantic similarity with 0.7 threshold

### Required API Keys

1. OpenAI API Key: For GPT-4o summarization
2. Anthropic API Key: For Claude-3.5 summarization
3. X.AI API Key: For grok-3 summarization
4. Google Custom Search API: For fresh content discovery (GOOGLE_SEARCH_API_KEY + GOOGLE_SEARCH_CX)

### Directory Structure

```
SmarterVote/
├── .env                          # Your local configuration (DO NOT COMMIT)
├── .env.example                  # Configuration template
├── data/
│   ├── chroma_db/               # Vector database storage
│   └── published/               # Sample race data
├── pipeline/
│   └── app/
│       └── step02_corpus/
│           ├── vector_database_manager.py  # Vector DB implementation
│           └── test_service.py             # Comprehensive tests
├── services/
│   ├── races-api/              # Race data API
│   └── enqueue-api/            # Job enqueueing API
└── web/                        # Frontend application
```

## 🧪 Testing and Validation

### Run Vector Database Tests
```bash
# Run all corpus tests
python -m pytest pipeline/app/step02_corpus/ -v

# Run specific test categories
python -m pytest pipeline/app/step02_corpus/test_service.py::TestVectorDatabaseManager::test_initialization -v
python -m pytest pipeline/app/step02_corpus/test_service.py::TestVectorDatabaseManager::test_build_corpus -v
```

### Test Pipeline Components
```bash
# Test full pipeline workflow
python scripts/run_local.py test-race-2024

# Validate project setup
python scripts/validate_project.py
```

## 🚀 Production Deployment

The infrastructure is managed with Terraform and automatically deployed via GitHub Actions.

### Environment Variables in Production

- ChromaDB settings via `infra/variables.tf`
- API keys stored in Secret Manager
- Storage in Google Cloud Storage buckets

### Deploy to Production

1. Push to main branch (triggers automatic deployment)
2. Manual deployment: use GitHub Actions workflow dispatch
3. Infrastructure changes: modify `infra/*.tf`

## 🔍 Troubleshooting

Common issues

1. ChromaDB initialization fails
   - Ensure `./data/chroma_db/` exists and is writable
   - Verify `sentence-transformers` installation

2. API key errors
   - Ensure all required API keys are set in `.env`
   - Check API key validity and quotas

3. Memory issues during embedding
   - Reduce `CHROMA_CHUNK_SIZE`
   - Consider a smaller embedding model

4. Port conflicts
   - Check ports 8000, 8001, 8002
   - Modify port settings as needed

## ✅ Success Criteria

- Vector database initializes and stores content
- Tests pass
- Services start without errors
- Sample race data processed end-to-end
- Web frontend displays race information

Happy coding! 🎉
