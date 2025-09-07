# SmarterVote Pipeline - Dual Mode Operation

## Overview

The SmarterVote pipeline has been enhanced to support **two primary modes of operation** based on environment detection:

1. **Local Mode** - For development, testing, and single-machine deployments
2. **Cloud Mode** - For production deployments in cloud environments

## Mode Detection

The pipeline automatically detects which mode to operate in based on environment variables:

### Local Mode Indicators
- No cloud environment variables present
- Running on local development machine
- Used for development and testing

### Cloud Mode Indicators
- `GOOGLE_CLOUD_PROJECT` environment variable set
- `CLOUD_RUN_SERVICE` environment variable set
- `K_SERVICE` environment variable set (Cloud Run)
- `GAE_APPLICATION` environment variable set (App Engine)
- `FUNCTION_NAME` environment variable set (Cloud Functions)

## Local Mode Operation

### Data Publishing
- **Target**: Local file system only
- **Location**: `data/published/` directory
- **Format**: JSON files named `{race-id}.json`
- **Backup**: Automatic backup creation before overwriting

### Source Collection
- Uses mock/placeholder results when API keys not configured
- Falls back gracefully when external services unavailable
- Focuses on seed sources and basic discovery

### Races API
- Reads directly from local `data/published/` directory
- Fast file system access
- No network dependencies

### Example Local Setup
```bash

# Start local races API
cd services/races-api
python main.py
```

## Cloud Mode Operation

### Data Publishing
- **Primary Target**: Google Cloud Storage (`gs://bucket/races/`)
- **Secondary Targets**:
  - Database (PostgreSQL via Cloud SQL)
  - Pub/Sub messaging
  - Webhook notifications
  - Local backup files

### Source Collection
- Full Google Custom Search API integration
- Comprehensive candidate and issue-specific searches
- Rate limiting and error handling
- Quality filtering and deduplication

### Races API
- **Primary**: Reads from local cache files (fast)
- **Fallback**: Reads from Google Cloud Storage
- **Caching**: Automatically caches cloud data locally
- **Scalability**: Handles high request volumes

### Example Cloud Setup
```bash
# Set environment variables
export GOOGLE_CLOUD_PROJECT=smartervote-prod
export GCS_BUCKET_NAME=sv-data
export GOOGLE_SEARCH_API_KEY=your-key
export GOOGLE_SEARCH_ENGINE_ID=your-engine-id

# Deploy to Cloud Run
gcloud run deploy smartervote-pipeline --source .
```

## Enhanced Functionality

### 1. Comprehensive Source Discovery

The pipeline now collects sources using search for:

#### Issues (All 11 Canonical Issues)
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

#### Candidates
- Individual candidate searches
- Campaign website discovery
- Social media account detection
- Biography and background sources

#### Race Overview
- General race information
- Electoral dynamics
- Recent developments

### 2. Multi-Level Summarization

The pipeline generates summaries for:

#### Race Summary
- Overall race dynamics
- Competitive landscape
- Major themes and issues
- Historical context

#### Candidate Summaries
- Individual candidate profiles
- Policy positions
- Background and experience
- Campaign messaging

#### Issue Summaries
- Issue-specific analysis
- Candidate positions per issue
- Recent developments
- Voter impact assessment

### 3. Publication Targets by Mode

| Target | Local Mode | Cloud Mode |
|--------|------------|------------|
| Local Files | ✅ Primary | ✅ Backup |
| Cloud Storage | ❌ | ✅ Primary |
| Database | ❌ | ✅ |
| Pub/Sub | ❌ | ✅ |
| Webhooks | ❌ | ✅ |

### 4. Races API Data Sources

| Data Source | Local Mode | Cloud Mode |
|-------------|------------|------------|
| Local Files | ✅ Only | ✅ Cache |
| Cloud Storage | ❌ | ✅ Fallback |
| Database | ❌ | ⚠️ Future |

## Configuration

### Local Mode Configuration
```env
# Minimal configuration for local development
DATA_DIR=data/published/
```

### Cloud Mode Configuration
```env
# Required for cloud operation
GOOGLE_CLOUD_PROJECT=your-project-id
GCS_BUCKET_NAME=your-bucket-name

# Optional API integrations
GOOGLE_SEARCH_API_KEY=your-search-key
GOOGLE_SEARCH_ENGINE_ID=your-engine-id
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
XAI_API_KEY=your-xai-key

# Optional database
DATABASE_URL=postgresql://user:pass@host:port/db

# Optional webhooks
WEBHOOK_URLS=https://api1.com/webhook,https://api2.com/webhook
WEBHOOK_SECRET=your-webhook-secret
```

## Error Handling & Fallbacks

### Graceful Degradation
- Missing API keys → Use mock data
- Network issues → Retry with exponential backoff
- Cloud storage unavailable → Use local files
- External services down → Continue with available data

### Quality Assurance
- 2-of-3 LLM consensus for high confidence
- Source quality scoring and filtering
- Content validation before publishing
- Comprehensive error logging

## Testing

### Local Testing
```bash
# Test pipeline logic
python -m pytest pipeline/app/ -v

# Test code quality
python scripts/validate_project.py

# Test integration
python -m pytest tests/ -v
```

### Cloud Testing
```bash
# Test with cloud environment variables
export GOOGLE_CLOUD_PROJECT=test-project
python -m pytest tests/ -v

# Test races API with cloud fallback
cd services/races-api
python -c "from simple_publish_service import SimplePublishService; print(SimplePublishService().cloud_enabled)"
```

## Monitoring & Observability

### Local Mode
- File system logs in `data/logs/`
- Console output for development
- Basic error tracking

### Cloud Mode
- Google Cloud Logging integration
- Pub/Sub message tracking
- API usage statistics
- Performance metrics
- Error alerting

## Migration Between Modes

### Local to Cloud
1. Set up Google Cloud Project
2. Configure environment variables
3. Deploy to Cloud Run/App Engine
4. Update DNS to point to cloud service

### Cloud to Local
1. Download published data from cloud storage
2. Clear cloud environment variables
3. Run local pipeline
4. Update API endpoints

## Conclusion

The dual-mode architecture ensures the SmarterVote pipeline can operate effectively in both development and production environments while maintaining feature parity and data consistency across deployments.
