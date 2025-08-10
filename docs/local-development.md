# Local Development Setup for SmarterVote

This guide helps you set up the SmarterVote pipeline for local development with proper environment configuration.

## 📋 Prerequisites

- Python 3.10+
- Node.js 18+
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

# Google Search API (Required for fresh content discovery)
GOOGLE_SEARCH_API_KEY=your_google_search_api_key
GOOGLE_SEARCH_ENGINE_ID=your_custom_search_engine_id

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
python test_vector_db.py

# Run comprehensive tests
python -m pytest pipeline/app/corpus/test_service.py -v
```

### 5. Start Development Services

#### Option A: Start All Services
```bash
# Windows PowerShell
.\dev-start.ps1

# Or run individual components:
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
python -m app.corpus.vector_database_manager  # Test vector DB
```

## 🔧 Configuration Details

### ChromaDB Vector Database

The vector database is the core of SmarterVote's corpus-first approach:

- **Storage**: Local SQLite database at `./data/chroma_db/`
- **Embedding Model**: `all-MiniLM-L6-v2` (sentence transformers)
- **Chunking**: 500 words per chunk with 50-word overlap
- **Search**: Semantic similarity with 0.7 threshold

### Required API Keys

1. **OpenAI API Key**: For GPT-4o summarization
   - Get from: https://platform.openai.com/api-keys

2. **Anthropic API Key**: For Claude-3.5 summarization
   - Get from: https://console.anthropic.com/

3. **X.AI API Key**: For Grok-4 summarization
   - Get from: https://x.ai/api

4. **Google Search API**: For fresh content discovery
   - Get from: https://developers.google.com/custom-search/v1/introduction

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
│       └── corpus/
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
python -m pytest pipeline/app/corpus/ -v

# Run specific test categories
python -m pytest pipeline/app/corpus/test_service.py::TestVectorDatabaseManager::test_initialization -v
python -m pytest pipeline/app/corpus/test_service.py::TestVectorDatabaseManager::test_build_corpus -v
```

### Test Pipeline Components
```bash
# Test full pipeline workflow
python scripts/run_local.py test-race-2024

# Validate project setup
python scripts/validate_project.py
```

## 🚀 Production Deployment

The infrastructure is managed with Terraform and automatically deployed via GitHub Actions:

### Environment Variables in Production

All configuration is managed through Terraform variables:
- ChromaDB settings are configured via `infra/variables.tf`
- API keys are stored in Google Secret Manager
- Storage is provided by Google Cloud Storage buckets

### Deploy to Production

1. **Push to main branch** (triggers automatic deployment)
2. **Manual deployment**: Use GitHub Actions workflow dispatch
3. **Infrastructure changes**: Modify `infra/*.tf` files

## 🔍 Troubleshooting

### Common Issues

1. **ChromaDB initialization fails**
   - Check that `./data/chroma_db/` directory exists and is writable
   - Verify `sentence-transformers` is installed correctly

2. **API key errors**
   - Ensure all required API keys are set in `.env`
   - Check API key validity and quotas

3. **Memory issues during embedding**
   - Reduce `CHROMA_CHUNK_SIZE` for systems with limited RAM
   - Consider using a smaller embedding model

4. **Port conflicts**
   - Check that ports 8000, 8001, 8002 are available
   - Modify port settings in service configurations

### Get Help

- **Documentation**: Check `docs/` directory
- **Issues**: Create GitHub issue with error details
- **Architecture**: See `docs/architecture.md`

## ✅ Success Criteria

Your local setup is working correctly when:

- ✅ Vector database initializes and stores content
- ✅ Tests pass with >90% success rate
- ✅ Services start without errors
- ✅ Sample race data can be processed end-to-end
- ✅ Web frontend displays race information

Happy coding! 🎉
