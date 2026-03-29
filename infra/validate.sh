#!/bin/bash

# SmarterVote Infrastructure Validation Script
# Updated to include ChromaDB vector database validation

set -e

echo "🔍 SmarterVote Infrastructure Validation (with ChromaDB Support)"
echo "================================================================="

# Get project ID from secrets.tfvars
if [ ! -f "secrets.tfvars" ]; then
    echo "❌ Error: secrets.tfvars file not found"
    exit 1
fi

PROJECT_ID=$(grep 'project_id' secrets.tfvars | cut -d'"' -f2)
REGION=$(grep 'region' secrets.tfvars | cut -d'"' -f2 || echo "us-central1")
ENVIRONMENT=$(grep 'environment' secrets.tfvars | cut -d'"' -f2 || echo "dev")

echo "📋 Project ID: $PROJECT_ID"
echo "📋 Region: $REGION"
echo "📋 Environment: $ENVIRONMENT"
echo ""

# Check if resources exist
echo "🔍 Checking infrastructure resources..."

# Check Cloud Storage buckets
echo -n "☁️  Main storage bucket: "
if gsutil ls -b gs://$PROJECT_ID-sv-data-$ENVIRONMENT >/dev/null 2>&1; then
    echo "✅ EXISTS"
else
    echo "❌ MISSING"
fi

echo -n "🧠 ChromaDB storage bucket: "
if gsutil ls -b gs://$PROJECT_ID-chroma-$ENVIRONMENT >/dev/null 2>&1; then
    echo "✅ EXISTS"
else
    echo "❌ MISSING"
fi

# Check Secret Manager secrets
echo -n "🔐 Secret Manager: "
SECRET_COUNT=$(gcloud secrets list --project=$PROJECT_ID --format="value(name)" | wc -l)
if [ $SECRET_COUNT -gt 0 ]; then
    echo "✅ $SECRET_COUNT secrets found"
else
    echo "❌ NO SECRETS FOUND"
fi

# Check Cloud Scheduler jobs

echo ""
echo "🧪 Testing API endpoint (if available)..."
RACES_URL=$(gcloud run services describe "races-api-$ENVIRONMENT" --region=$REGION --project=$PROJECT_ID --format="value(status.url)" 2>/dev/null || echo "")
if [ ! -z "$RACES_URL" ]; then
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$RACES_URL/health" || echo "000")
    if [ "$HTTP_STATUS" = "200" ]; then
        echo "✅ API endpoint is responding"
    else
        echo "⚠️  API endpoint returned status: $HTTP_STATUS"
    fi
else
    echo "⏭️  Skipping API test (service not found)"
fi

echo ""
echo "📋 Summary:"
echo "Infrastructure deployment validation completed."
echo "If any resources show as NOT FOUND, re-run the deployment script."
