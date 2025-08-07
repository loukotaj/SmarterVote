# 🤖 GitHub Actions Setup for SmarterVote

**Automated build and deployment pipeline for the complete SmarterVote infrastructure.**

## 🔧 Required GitHub Secrets

Add these secrets to your GitHub repository settings:

### 1. **GCP Service Account Key** (`GCP_SA_KEY`)
```bash
# Create service account with required permissions
gcloud iam service-accounts create github-actions \
  --description="GitHub Actions deployment" \
  --display-name="GitHub Actions"

# Grant necessary roles
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:github-actions@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:github-actions@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:github-actions@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Create and download key
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account=github-actions@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Copy the entire JSON content to GitHub secret GCP_SA_KEY
```

### 2. **GCP Project ID** (`GCP_PROJECT_ID`)
```
your-gcp-project-id
```

## 🚀 Automated Workflow

The GitHub Actions workflow automatically:

### **On Push to Main:**
1. **🔨 Builds** all Docker images (pipeline, enqueue-api, races-api)
2. **📤 Pushes** images to Google Container Registry
3. **🚀 Deploys** to Cloud Run services with environment naming
4. **🧪 Tests** API endpoints post-deployment

### **Triggered When:**
- Changes to `services/**` (API updates)
- Changes to `pipeline/**` (Processing logic updates)
- Changes to `infra/**` (Infrastructure updates)
- Manual workflow dispatch

### **Environment Configuration:**
```yaml
env:
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  REGION: us-central1
  ENVIRONMENT: dev  # Change to 'staging' or 'prod' as needed
```

## 🏗️ Infrastructure Alignment

The workflow uses your Terraform naming convention:
- **Cloud Run Job**: `race-worker-${environment}`
- **Enqueue API**: `enqueue-api-${environment}`
- **Races API**: `races-api-${environment}`

## 📋 Deployment Process

### 1. **Infrastructure First** (One-time setup)
```bash
# Deploy infrastructure via Terraform
cd infra
terraform apply -var-file=secrets.tfvars
```

### 2. **Automated Deployments** (Ongoing)
```bash
# Just push to main - GitHub Actions handles the rest!
git add .
git commit -m "Update services"
git push origin main
```

### 3. **Monitor Deployments**
- Check GitHub Actions tab for build/deploy status
- Monitor Cloud Run logs in GCP Console
- API endpoints tested automatically

## 🔄 Workflow Features

### **Build Optimization:**
- Tags images with both `git-sha` and `latest`
- Parallel builds for faster deployment
- Docker layer caching

### **Deployment Safety:**
- Updates existing services (no recreation)
- Maintains traffic routing during updates
- Endpoint health checks post-deployment

### **Environment Support:**
- Easy environment switching via `ENVIRONMENT` variable
- Supports dev/staging/prod in same project
- Consistent naming with Terraform

## 🎯 Benefits

- **🔄 Continuous Deployment**: Push to deploy automatically
- **⚡ Fast Builds**: Parallel processing and caching
- **🛡️ Secure**: Uses IAM service accounts
- **📊 Visibility**: Full deployment logs and status
- **🧪 Tested**: Automatic endpoint verification

**Your SmarterVote pipeline now deploys automatically on every push! 🚀**
