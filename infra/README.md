# SmarterVote Infrastructure

This directory contains the Terraform configuration for deploying SmarterVote infrastructure on Google Cloud Platform.

## Architecture

The infrastructure includes:

- **Cloud Storage**: Bucket for storing race data (`sv-data`)
- **Secret Manager**: Secure storage for API keys (OpenAI, Anthropic, Grok, Google Search)
- **Pub/Sub**: Message queue for race processing jobs
- **Cloud Run Service**: API for enqueueing race processing jobs
- **Cloud Run Job**: Worker for processing races through the pipeline
- **Cloud Scheduler**: Automated daily race checking
- **IAM**: Service accounts and permissions

## File Structure

```
infra/
├── main.tf              # Core Terraform configuration and variables
├── bucket.tf           # Cloud Storage bucket configuration
├── secrets.tf          # Secret Manager for API keys
├── pubsub.tf           # Pub/Sub topic and subscription
├── run-service.tf      # Cloud Run service (API)
├── run-job.tf          # Cloud Run job (worker)
├── scheduler.tf        # Cloud Scheduler configuration
├── deploy.sh           # Linux/Mac deployment script
├── deploy.ps1          # Windows PowerShell deployment script
├── validate.sh         # Infrastructure validation script
├── secrets.tfvars.example  # Example configuration file
├── envs/               # Environment-specific configurations
└── modules/            # Reusable Terraform modules (empty)
```

## Prerequisites

1. **Google Cloud SDK**: Install and authenticate
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Terraform**: Install Terraform >= 1.0

3. **Docker**: For building and pushing container images

4. **API Keys**: Obtain keys for:
   - OpenAI API
   - Anthropic API
   - Grok API (X.AI)
   - Google Custom Search API

## Deployment

### 1. Configure Variables

Copy the example file and fill in your values:
```bash
cp secrets.tfvars.example secrets.tfvars
```

Edit `secrets.tfvars` with your:
- GCP project ID
- API keys
- Region (optional, defaults to us-central1)

> **⚠️ Security Note**: The `secrets.tfvars` file contains sensitive API keys and is excluded from version control via `.gitignore`. Never commit this file to your repository.

### 2. Deploy Infrastructure

**Option A: Using the deployment script (recommended)**
```bash
# On Linux/Mac
chmod +x deploy.sh
./deploy.sh

# On Windows PowerShell
.\deploy.ps1
```

**Option B: Manual deployment**
```bash
terraform init
terraform plan -var-file=secrets.tfvars
terraform apply -var-file=secrets.tfvars
```

### 3. Build and Push Docker Images

After infrastructure deployment, build and push your application images:

```bash
# Build pipeline image
cd ../pipeline
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-pipeline:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-pipeline:latest

# Build enqueue API image
cd ../services/enqueue-api
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest
```

### 4. Update Cloud Run Services

After pushing images, update the Cloud Run services:
```bash
gcloud run services update enqueue-api --image gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest --region us-central1
gcloud run jobs update race-worker --image gcr.io/YOUR_PROJECT_ID/smartervote-pipeline:latest --region us-central1
```

## Infrastructure Components

### Storage
- **sv-data bucket**: Stores race data with folders `raw/`, `norm/`, `out/`, `arb/`
- Lifecycle rules: Archive after 30 days, delete after 90 days
- Versioning enabled for data protection

### Security
- **Service Accounts**: Separate accounts for each service with minimal permissions
- **Secret Manager**: Encrypted storage for API keys
- **IAM**: Principle of least privilege access

### Compute
- **Enqueue API**: Publicly accessible service for triggering race processing
- **Race Worker**: Batch job for processing races through the pipeline
- **Auto-scaling**: Services scale based on demand

### Monitoring
- **Cloud Scheduler**: Daily automated race checking at 6 AM EST
- **Dead Letter Queue**: Failed jobs are moved to DLQ for investigation
- **Logging**: All services log to Cloud Logging

## Outputs

After deployment, Terraform outputs:
- `bucket_name`: Name of the storage bucket
- `enqueue_api_url`: URL of the enqueue API
- `pubsub_topic`: Name of the Pub/Sub topic
- `race_worker_job`: Name of the Cloud Run job

## Cleanup

To destroy all infrastructure:
```bash
terraform destroy -var-file=secrets.tfvars
```

## Troubleshooting

### Common Issues

1. **API not enabled**: Ensure all required APIs are enabled in your GCP project
2. **Permissions**: Verify your gcloud account has necessary permissions
3. **Docker images**: Cloud Run services will fail until images are pushed
4. **Secrets**: Ensure all API keys are valid and properly formatted

### Logs

Check Cloud Run logs:
```bash
gcloud logs read "resource.type=cloud_run_revision" --limit=50
```

Check Pub/Sub subscription:
```bash
gcloud pubsub subscriptions pull race-jobs-sub --auto-ack
```

## Development vs Production

For production deployment:
1. Enable GCS backend for Terraform state
2. Use separate projects for dev/staging/prod
3. Implement CI/CD pipeline
4. Enable additional monitoring and alerting
5. Configure custom domains and SSL certificates
