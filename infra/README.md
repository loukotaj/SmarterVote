# SmarterVote Infrastructure

**Cloud deployment for the AI agent electoral analysis pipeline** ☁️

## Overview

Terraform configurations for deploying SmarterVote on Google Cloud Platform.

**Default deployment**: Lightweight (races-api + storage only)
**Full deployment**: Enable `enable_pipeline_client = true` for cloud pipeline processing

## Quick Start

### 1. Configure

```bash
cp secrets.tfvars.example secrets.tfvars
```

Edit `secrets.tfvars`:
```hcl
project_id     = "your-gcp-project-id"
region         = "us-central1"
openai_api_key = "sk-your-openai-key"
serper_api_key = "your-serper-key"

# Enable cloud pipeline (disabled by default - run locally instead)
enable_pipeline_client = false
```

### 2. Deploy

```bash
terraform init
terraform plan -var-file=secrets.tfvars
terraform apply -var-file=secrets.tfvars
```

### 3. Validate

```bash
curl "$(terraform output -raw races_api_url)/health"
```

## Components

| Component | Default | With enable_pipeline_client |
|-----------|---------|---------------------------|
| races-api | ✅ | ✅ |
| GCS bucket | ✅ | ✅ |
| pipeline-client | ❌ | ✅ |
| Pub/Sub | ❌ | ✅ |
| Cloud Run Jobs | ❌ | ✅ |
| Scheduler | ❌ | ✅ |

## File Structure

```
infra/
├── main.tf              # Provider config
├── variables.tf         # Input variables (incl. enable_pipeline_client)
├── outputs.tf           # Terraform outputs
├── bucket.tf            # GCS storage
├── races-api.tf         # Data serving API
├── secrets.tf           # Secret Manager (OpenAI + Serper keys)
├── pipeline-client.tf   # Pipeline service (conditional)
├── pubsub.tf            # Messaging (conditional)
├── run-job.tf           # Batch workers (conditional)
├── scheduler.tf         # Cron triggers (conditional)
└── secrets.tfvars       # Your secrets (gitignored)
```

## Prerequisites

- Google Cloud SDK
- Terraform 1.5+
- Docker (for building images)

Enable APIs:
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  storage.googleapis.com secretmanager.googleapis.com
```

## Cleanup

```bash
terraform destroy -var-file=secrets.tfvars
```
