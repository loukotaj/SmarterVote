# SmarterVote Infrastructure

**Cloud-Native Electoral Analysis Platform** ☁️

*Infrastructure as Code for Google Cloud Platform | Updated: August 2025*

## 🎯 Overview

This directory contains production-ready Terraform configurations for deploying SmarterVote's cloud infrastructure on Google Cloud Platform. The architecture supports auto-scaling, high availability, and cost-effective processing of electoral data through serverless technologies.

## 🏗️ Architecture Components

### Core Infrastructure
- **Cloud Storage**: Multi-tiered data storage with lifecycle management
- **Secret Manager**: Encrypted API key storage and rotation
- **Pub/Sub**: Event-driven messaging for async processing
- **Cloud Run Services**: Auto-scaling API endpoints
- **Cloud Run Jobs**: Batch processing workers
- **Cloud Scheduler**: Automated pipeline triggers
- **IAM**: Principle of least privilege security model

### Data Flow Architecture
```
Internet → Cloud Load Balancer → Cloud Run (APIs) 
                                      ↓
                                 Pub/Sub Topics
                                      ↓  
                              Cloud Run Jobs (Workers)
                                      ↓
                            Cloud Storage (Data Lake)
```

## 📁 File Structure

```
infra/
├── main.tf                    # Core configuration & variables
├── bucket.tf                 # Cloud Storage with lifecycle rules
├── secrets.tf                # Secret Manager configuration
├── pubsub.tf                 # Messaging infrastructure
├── run-service.tf            # Auto-scaling API services
├── run-job.tf                # Batch processing workers
├── scheduler.tf              # Automated job scheduling
├── deploy.sh                 # Unix deployment script
├── deploy.ps1                # Windows PowerShell deployment
├── validate.sh               # Infrastructure validation
├── secrets.tfvars.example    # Configuration template
├── envs/                     # Environment-specific configs
│   └── dev/
│       └── main.tf           # Development environment
└── modules/                  # Reusable Terraform modules
```

## ⚡ Prerequisites

### Required Tools
1. **Google Cloud SDK** (latest version)
   ```bash
   # Install and authenticate
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   gcloud auth application-default login
   ```

2. **Terraform** (v1.5+)
   ```bash
   # Verify installation
   terraform --version
   ```

3. **Docker** (for container image builds)
   ```bash
   # Verify installation  
   docker --version
   ```

### Required API Keys
Obtain API keys for the following services:
- **OpenAI API** - GPT-4o model access
- **Anthropic API** - Claude-3.5 model access  
- **Grok API** (X.AI) - Grok-4 model access
- **Google Custom Search API** - Content discovery
- **Google Cloud APIs** - Enable in your GCP project:
  - Cloud Run API
  - Cloud Storage API
  - Cloud Scheduler API
  - Pub/Sub API
  - Secret Manager API
  - Container Registry API

### GCP Project Setup
```bash
# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable pubsub.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
```

## 🚀 Quick Deployment

### 1. Configure Environment Variables
```bash
# Copy and customize the configuration template
cp secrets.tfvars.example secrets.tfvars
```

Edit `secrets.tfvars` with your project-specific values:
```hcl
project_id = "your-gcp-project-id"
region     = "us-central1"

# API Keys (stored in Secret Manager)
openai_api_key     = "sk-your-openai-key"
anthropic_api_key  = "your-anthropic-key" 
grok_api_key       = "your-grok-key"
google_search_key  = "your-google-search-key"
google_search_cx   = "your-custom-search-engine-id"
```

> ⚠️ **Security Note**: The `secrets.tfvars` file contains sensitive credentials and is automatically excluded from version control.

### 2. Deploy Infrastructure

**Option A: Automated Deployment (Recommended)**
```bash
# Unix/Linux/macOS
./deploy.sh

# Windows PowerShell  
.\deploy.ps1
```

**Option B: Manual Deployment**
```bash
# Initialize Terraform
terraform init

# Review planned changes
terraform plan -var-file=secrets.tfvars

# Deploy infrastructure
terraform apply -var-file=secrets.tfvars
```

### 3. Build and Deploy Application Images
```bash
# Build and push pipeline worker
cd ../pipeline
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-worker:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-worker:latest

# Build and push enqueue API
cd ../services/enqueue-api  
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest

# Update Cloud Run services
gcloud run services update enqueue-api \
  --image gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest \
  --region us-central1

gcloud run jobs update race-worker \
  --image gcr.io/YOUR_PROJECT_ID/smartervote-worker:latest \
  --region us-central1
```

### 4. Validate Deployment
```bash
# Run infrastructure validation
./validate.sh

# Test API endpoint
curl "$(terraform output -raw enqueue_api_url)/health"
```
```

### 4. Update Cloud Run Services

After pushing images, update the Cloud Run services:
```bash
gcloud run services update enqueue-api --image gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest --region us-central1
gcloud run jobs update race-worker --image gcr.io/YOUR_PROJECT_ID/smartervote-pipeline:latest --region us-central1
```

## 🏗️ Infrastructure Components

### 📦 Storage Architecture
- **sv-data Cloud Storage bucket**: Multi-tiered data lake with folders:
  - `raw/` - Original source content
  - `norm/` - Processed and normalized text
  - `out/` - Final RaceJSON outputs
  - `arb/` - Arbitration results and metadata
- **Lifecycle Management**: Auto-archive after 30 days, delete after 90 days
- **Versioning**: Enabled for data protection and audit trails
- **Access Controls**: IAM-based with service-specific permissions

### 🔐 Security Framework
- **Service Accounts**: Dedicated accounts per service with minimal permissions
- **Secret Manager**: Encrypted storage for API keys with rotation support
- **IAM Policies**: Principle of least privilege access control
- **Network Security**: VPC-native services with private connectivity

### ⚡ Compute Services
- **Enqueue API**: Publicly accessible service for triggering race processing
  - Auto-scaling: 0-100 instances based on traffic
  - Resource allocation: 1 CPU, 512MB memory per instance
  - Request timeout: 30 seconds
- **Race Worker**: Batch job for processing races through the pipeline
  - Resource allocation: 2 CPUs, 4GB memory per job
  - Timeout: 1 hour per race processing
  - Parallelism: 1 (sequential processing for consistency)

### 📬 Messaging & Events
- **Pub/Sub Topics**: Event-driven architecture
  - `race-jobs`: Main processing queue
  - `race-jobs-dlq`: Dead letter queue for failed jobs
- **Cloud Scheduler**: Automated triggers
  - Daily race checking: 6 AM EST
  - Weekly full refresh: Sundays at 1 AM UTC
- **Retry Policies**: Exponential backoff with 5 max attempts

## 📊 Monitoring & Observability

### Logging
```bash
# View application logs
gcloud logs read "resource.type=cloud_run_revision" --limit=50

# Monitor job execution  
gcloud logs read "resource.type=cloud_run_job" --limit=20

# Check Pub/Sub message flow
gcloud logs read "resource.type=pubsub_topic" --limit=10
```

### Health Checks
```bash
# Service health
curl "$(terraform output -raw enqueue_api_url)/health"

# Infrastructure validation
./validate.sh

# Resource status
gcloud run services list --region=us-central1
gcloud run jobs list --region=us-central1
```

### Performance Metrics
- **Response Time**: <2 seconds for API endpoints
- **Processing Time**: <10 minutes per race analysis
- **Uptime**: 99.9% target availability
- **Cost Optimization**: Pay-per-use serverless architecture

## 🎯 Deployment Outputs

After successful deployment, Terraform provides:
- `bucket_name`: Name of the data storage bucket
- `enqueue_api_url`: Public URL for the enqueue API
- `pubsub_topic`: Name of the main processing topic
- `race_worker_job`: Name of the Cloud Run batch job
- `project_id`: Deployed GCP project identifier
- `region`: Deployment region
## 🧹 Cleanup & Maintenance

### Destroy Infrastructure
```bash
# Remove all cloud resources
terraform destroy -var-file=secrets.tfvars
```

### Cost Management
```bash
# Monitor spending
gcloud billing budgets list

# Check resource usage
gcloud logging metrics list
gcloud monitoring metrics list
```

### Backup & Recovery
```bash
# Export Terraform state
terraform state pull > terraform-state-backup.json

# Backup configuration
cp secrets.tfvars secrets.tfvars.backup.$(date +%Y%m%d)
```

## 🚨 Troubleshooting

### Common Issues

#### API Not Enabled
```bash
# Enable missing APIs
gcloud services list --available | grep -E "(run|storage|secretmanager)"
gcloud services enable [API_NAME]
```

#### Permission Errors
```bash
# Check current permissions
gcloud auth list
gcloud projects get-iam-policy $PROJECT_ID

# Re-authenticate if needed
gcloud auth application-default login
```

#### Docker Image Issues
```bash
# Configure Docker authentication
gcloud auth configure-docker gcr.io

# Test image build
docker build -t test-image .
docker run --rm test-image echo "Container works"
```

#### Service Deployment Failures
```bash
# Check service logs
gcloud run services describe SERVICE_NAME --region=us-central1
gcloud logs read "resource.type=cloud_run_revision" --limit=10

# Update service manually
gcloud run services update SERVICE_NAME \
  --image gcr.io/PROJECT_ID/IMAGE:TAG \
  --region us-central1
```

### Recovery Procedures

#### State File Corruption
```bash
# Import existing resources
terraform import google_storage_bucket.sv_data sv-data-RANDOM_SUFFIX
terraform import google_cloud_run_v2_service.enqueue_api projects/PROJECT_ID/locations/us-central1/services/enqueue-api
```

#### Resource Conflicts
```bash
# Force resource recreation
terraform taint google_cloud_run_v2_service.enqueue_api
terraform apply -var-file=secrets.tfvars
```

## 🔄 Environment Management

### Development Environment
```bash
cd envs/dev
terraform init
terraform apply -var-file=../../secrets.tfvars
```

### Production Considerations
- **Separate Projects**: Use different GCP projects for dev/staging/prod
- **State Management**: Enable remote state storage with GCS backend
- **Access Controls**: Implement stricter IAM policies
- **Monitoring**: Enable Cloud Monitoring and Alerting
- **Backup Strategy**: Automated daily backups with cross-region replication

### CI/CD Integration
The infrastructure supports automated deployment through GitHub Actions:
- **Terraform Plan**: On pull requests
- **Terraform Apply**: On main branch merges
- **Image Building**: Automated container builds
- **Service Updates**: Rolling deployments with zero downtime

---

**Infrastructure as Code for Democratic Technology** 🗳️

*Built with scalability, security, and cost-effectiveness in mind*

*Last updated: August 2025*
