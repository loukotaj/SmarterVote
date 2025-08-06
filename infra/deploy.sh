#!/bin/bash

# SmarterVote Infrastructure Deployment Script

set -e

echo "🚀 SmarterVote Infrastructure Deployment"
echo "========================================"

# Check if secrets.tfvars exists
if [ ! -f "secrets.tfvars" ]; then
    echo "❌ Error: secrets.tfvars file not found"
    echo "Please copy secrets.tfvars.example to secrets.tfvars and fill in your values"
    exit 1
fi

# Check if required tools are installed
command -v terraform >/dev/null 2>&1 || { echo "❌ Error: terraform is required but not installed."; exit 1; }
command -v gcloud >/dev/null 2>&1 || { echo "❌ Error: gcloud CLI is required but not installed."; exit 1; }

# Check if user is authenticated with gcloud
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Error: Not authenticated with gcloud. Please run: gcloud auth login"
    exit 1
fi

echo "✅ Prerequisites check passed"

# Get project ID and region from secrets.tfvars
PROJECT_ID=$(grep 'project_id' secrets.tfvars | cut -d'"' -f2)
REGION=$(grep 'region' secrets.tfvars | cut -d'"' -f2)
if [ -z "$REGION" ]; then
    REGION="us-central1"
fi

echo "📋 Project ID: $PROJECT_ID"
echo "📋 Region: $REGION"

# Set gcloud project
echo "🔧 Setting gcloud project..."
gcloud config set project $PROJECT_ID

# Initialize Terraform
echo "🔄 Initializing Terraform..."
terraform init

# Validate configuration
echo "✅ Validating Terraform configuration..."
terraform validate

# Plan deployment
echo "📋 Planning deployment..."
terraform plan -var-file=secrets.tfvars

# Ask for confirmation
read -p "Do you want to proceed with the deployment? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled"
    exit 0
fi

# Apply configuration
echo "🚀 Deploying infrastructure..."
terraform apply -var-file=secrets.tfvars -auto-approve

echo "✅ Infrastructure deployment completed!"
echo ""
echo "📋 Next steps:"
echo "1. Build and push your Docker images to Artifact Registry:"
echo "   - gcloud auth configure-docker $REGION-docker.pkg.dev"
echo "   - cd ../pipeline && docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/smartervote-dev/pipeline:latest ."
echo "   - docker push $REGION-docker.pkg.dev/$PROJECT_ID/smartervote-dev/pipeline:latest"
echo "   - cd ../services/enqueue-api && docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/smartervote-dev/enqueue-api:latest ."
echo "   - docker push $REGION-docker.pkg.dev/$PROJECT_ID/smartervote-dev/enqueue-api:latest"
echo "   - cd ../services/races-api && docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/smartervote-dev/races-api:latest ."
echo "   - docker push $REGION-docker.pkg.dev/$PROJECT_ID/smartervote-dev/races-api:latest"
echo ""
echo "2. Update Cloud Run services to use the new images"
echo "3. Test the API endpoints"
