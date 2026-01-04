# Pipeline Modes

The SmarterVote pipeline supports local and cloud operation modes.

## Local Mode (Default)

Best for development and small-scale use.

**How it works**:
- Pipeline runs on your machine via `pipeline_client/run.py`
- Data publishes to `data/published/` as JSON files
- Races API reads directly from local files
- ChromaDB stores vectors in `data/chroma_db/`

**Setup**:
```powershell
# Install dependencies
pip install -r pipeline/requirements.txt

# Set API keys in .env
# OPENAI_API_KEY, ANTHROPIC_API_KEY, XAI_API_KEY, SERPER_API_KEY

# Run pipeline
python pipeline_client/run.py mo-senate-2024

# Serve data
cd services/races-api && python main.py
```

## Cloud Mode

For production scaling. Enable via Terraform.

**How it works**:
- Pipeline runs on Cloud Run (triggered via Pub/Sub or enqueue-api)
- Data publishes to Google Cloud Storage (`gs://bucket/races/`)
- Races API reads from GCS with local caching
- ChromaDB stored in GCS-backed volume

**Setup**:
```bash
# Enable cloud deployment
cd infra
# Edit terraform.tfvars: enable_pipeline_client = true
terraform apply

# Set environment variables
export GOOGLE_CLOUD_PROJECT=your-project
export GCS_BUCKET_NAME=your-bucket
```

## Mode Detection

The pipeline auto-detects mode based on environment:

| Variable | Indicates |
|----------|-----------|
| `GOOGLE_CLOUD_PROJECT` | Cloud mode |
| `K_SERVICE` | Cloud Run |
| None of above | Local mode |

## Storage Abstraction

Both modes use the same code via storage backends:

```python
# Local mode
storage = LocalStorageBackend(base_path="data/published")

# Cloud mode
storage = GCPStorageBackend(bucket_name="sv-data")
```

Switch by setting `STORAGE_BACKEND=gcp` environment variable.

## Output

Both modes produce identical RaceJSON v0.2 files:
- `{race-id}.json` with candidates, issues, sources
- 12 canonical issues per candidate
- Confidence levels (high/medium/low) from multi-LLM consensus
