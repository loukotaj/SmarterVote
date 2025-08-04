# 🚀 SmarterVote Infrastructure Deployment

**Ready-to-deploy modular Terraform configuration for the complete SmarterVote corpus-first AI pipeline.**

## ✅ **What's Fixed & Ready:**

- **✅ Single GCP Project** - All resources use `var.project_id` consistently
- **✅ Environment Isolation** - Resources named with `${var.environment}` suffix
- **✅ Modular Architecture** - Clean separation by component type
- **✅ Complete Dependencies** - All resource references properly linked
- **✅ IAM Security** - Principle of least privilege for all service accounts
- **✅ Multi-LLM Support** - GPT-4o, Claude-3.5, Grok-4 API keys in Secret Manager

## 📁 **Modular File Structure:**

```
infra/
├── main.tf              # Core provider & API enablement
├── variables.tf         # All input variables
├── outputs.tf           # Infrastructure outputs
├── bucket.tf           # Cloud Storage with lifecycle
├── secrets.tf          # Secret Manager + Service Accounts + IAM
├── pubsub.tf           # Messaging infrastructure
├── run-job.tf          # Race processing worker job
├── run-service.tf      # Enqueue & Races API services
├── scheduler.tf        # Automated processing triggers
├── deploy.ps1          # Windows deployment script
└── secrets.tfvars.example  # Configuration template
```

## 🚀 **Quick Deployment:**

### **Option A: Automated via GitHub Actions** ⭐ **RECOMMENDED**

1. **Set up GitHub Secrets** (see `.github/workflows/README.md`)
2. **Push to main branch** - GitHub Actions handles everything:
   - ✅ Terraform infrastructure deployment
   - ✅ Docker image builds
   - ✅ Cloud Run service updates
   - ✅ Endpoint testing

```bash
git add .
git commit -m "Deploy SmarterVote infrastructure"
git push origin main
```

### **Option B: Manual Local Deployment**

### 1. **Configure Secrets**
```powershell
# Copy template and edit with your values
cp secrets.tfvars.example secrets.tfvars
# Edit secrets.tfvars with your project ID and API keys
```

### 2. **Deploy Infrastructure**
```powershell
# Option A: Automated (Recommended)
.\deploy.ps1

# Option B: Manual
terraform init
terraform plan -var-file=secrets.tfvars
terraform apply -var-file=secrets.tfvars
```

### 3. **Automated Image Build & Deploy via GitHub Actions**

Your GitHub Actions workflows automatically handle:

- **🏗️ Infrastructure**: `.github/workflows/terraform-deploy.yaml`
  - Terraform plan & apply on infrastructure changes
  - Environment selection (dev/staging/prod)
  - Secure secret management

- **🚀 Services**: `.github/workflows/GCPDeploy.yaml`  
  - Docker builds for all services (pipeline, APIs)
  - Push to Google Container Registry
  - Deploy to Cloud Run with proper naming
  - Endpoint health testing

**Just push to main branch and everything deploys automatically!** 🚀

#### Manual Build & Deploy (if needed):
```powershell
# Pipeline worker
cd ..\pipeline
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-pipeline:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-pipeline:latest

# Enqueue API
cd ..\services\enqueue-api
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-enqueue-api:latest

# Races API  
cd ..\services\races-api
docker build -t gcr.io/YOUR_PROJECT_ID/smartervote-races-api:latest .
docker push gcr.io/YOUR_PROJECT_ID/smartervote-races-api:latest
```

## 🏗️ **Architecture Deployed:**

- **📦 Cloud Storage**: `${project_id}-sv-data-${environment}` bucket
- **🔐 Secret Manager**: All AI API keys encrypted
- **📨 Pub/Sub**: `race-jobs-${environment}` topic with DLQ
- **⚡ Cloud Run**: Auto-scaling enqueue & races APIs
- **🔄 Cloud Run Jobs**: Race processing pipeline worker
- **⏰ Cloud Scheduler**: Automated nightly & weekly processing
- **🛡️ IAM**: Secure service accounts with minimal permissions

## 🎯 **Ready for Production:**

All resources are properly namespaced with `${var.environment}` so you can deploy multiple environments (dev/staging/prod) in the same project without conflicts.

## 🤖 **Complete Automation Pipeline:**

1. **🔄 Infrastructure as Code**: Terraform manages all GCP resources
2. **🚀 Continuous Deployment**: GitHub Actions builds & deploys on push
3. **🏗️ Multi-Environment**: Easy dev/staging/prod switching
4. **🛡️ Secure**: API keys in Secret Manager, IAM least privilege
5. **📊 Observable**: Monitoring, logging, and health checks built-in
6. **⚡ Scalable**: Auto-scaling Cloud Run services with 0-to-N instances

### **🎉 Your Complete DevOps Flow:**
```bash
# 1. Make changes to services or infrastructure
git add .
git commit -m "Feature: improved race analysis"

# 2. Push to main branch
git push origin main

# 3. GitHub Actions automatically:
#    ✅ Deploys infrastructure changes (Terraform)
#    ✅ Builds & pushes Docker images  
#    ✅ Updates Cloud Run services
#    ✅ Tests API endpoints
#    ✅ Reports deployment status

# 4. Your SmarterVote corpus-first AI pipeline is live! 🚀
```

**Your infrastructure is now ready to deploy the complete SmarterVote corpus-first AI pipeline with full automation! 🎉**
