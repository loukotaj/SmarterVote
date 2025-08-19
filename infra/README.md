# SmarterVote Infrastructure

**Cloud-Native Electoral Analysis Platform** ☁️

*Infrastructure as Code for Google Cloud Platform | Updated: August 2025*

## 🎯 Overview

This directory contains Terraform configurations for deploying SmarterVote's infrastructure on Google Cloud Platform.

## 🏗️ Architecture Components

- Cloud Storage, Secret Manager, Pub/Sub
- Cloud Run Services and Jobs, Cloud Scheduler
- IAM with least-privilege

## 📁 File Structure

```
infra/
├── main.tf                    # Core configuration & variables
├── variables.tf               # Input variable definitions
├── outputs.tf                 # Infrastructure outputs
├── bucket.tf                  # Cloud Storage with lifecycle rules
├── secrets.tf                 # Secret Manager configuration
├── pubsub.tf                  # Messaging infrastructure
├── enqueue-api.tf             # Enqueue API service deployment
├── races-api.tf               # Races API service deployment
├── pipeline-client.tf         # Pipeline client service deployment
├── run-job.tf                 # Batch processing workers
├── scheduler.tf               # Automated job scheduling
├── deploy.sh                  # Unix deployment script
├── deploy.ps1                 # Windows PowerShell deployment
├── validate.sh                # Infrastructure validation
├── secrets.tfvars.example     # Configuration template
└── modules/                   # Reusable Terraform modules
```

## ⚡ Prerequisites

- Google Cloud SDK
- Terraform v1.5+
- Docker

Enable GCP APIs (once per project):
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  storage.googleapis.com secretmanager.googleapis.com \
  pubsub.googleapis.com cloudscheduler.googleapis.com
```

## 🚀 Quick Deployment

1) Configure secrets
```bash
cp secrets.tfvars.example secrets.tfvars
```

Edit `secrets.tfvars`:
```hcl
project_id            = "your-gcp-project-id"
region                = "us-central1"
openai_api_key        = "sk-your-openai-key"
anthropic_api_key     = "your-anthropic-key"
grok_api_key          = "your-grok-key"
google_search_api_key = "your-google-search-key"
google_search_cx      = "your-custom-search-engine-id"
```

2) Deploy
```bash
terraform init
terraform plan -var-file=secrets.tfvars
terraform apply -var-file=secrets.tfvars
```

3) Build and push images
```bash
# Pipeline worker
cd ../pipeline
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-worker:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-worker:latest

# Pipeline client
cd ../pipeline_client
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-pipeline-client:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-pipeline-client:latest

# Enqueue API
cd ../services/enqueue-api
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest
```

4) Update Cloud Run
```bash
gcloud run services update enqueue-api \
  --image gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest \
  --region us-central1

gcloud run jobs update race-worker \
  --image gcr.io/YOUR_PROJECT_ID/smartervote-worker:latest \
  --region us-central1

gcloud run services update pipeline-client \
  --image gcr.io/YOUR_PROJECT_ID/smartervote-pipeline-client:latest \
  --region us-central1
```

5) Validate
```bash
./validate.sh
curl "$(terraform output -raw enqueue_api_url)/health"
```

## 🏗️ Components

- Storage: data lake with lifecycle, versioning, IAM
- Security: service accounts, Secret Manager, IAM policies
- Compute: Cloud Run services and jobs with sensible defaults
- Messaging: Pub/Sub topics + DLQ, Cloud Scheduler

## 📊 Monitoring

- Logs: `gcloud logs read` for run revisions and jobs
- Health: `curl $(terraform output -raw enqueue_api_url)/health`
- Listing: `gcloud run services list --region=us-central1`

## 🧹 Cleanup

```bash
terraform destroy -var-file=secrets.tfvars
```

---

Built with scalability, security, and cost-effectiveness in mind.
