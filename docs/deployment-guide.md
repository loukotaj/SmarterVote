# SmarterVote Infrastructure Deployment & Rollback Guide

This guide covers the enhanced Terraform deployment system with state management, lifecycle protection, and automated rollback capabilities.

## 🚀 Quick Start

### Deploy Infrastructure
```powershell
# Plan changes (safe, no modifications)
.\scripts\deploy.ps1 -Environment dev -Action plan

# Apply changes to development
.\scripts\deploy.ps1 -Environment dev -Action apply

# Deploy to production
.\scripts\deploy.ps1 -Environment prod -Action apply
```

### Emergency Rollback
```powershell
# Rollback to previous commit
.\scripts\rollback.ps1 -Environment prod

# Rollback to specific commit
.\scripts\rollback.ps1 -Environment prod -ToCommit abc123f
```

### Validate Infrastructure
```powershell
# Check all components are healthy
.\scripts\validate-infra.ps1 -Environment prod
```

## 🔧 Key Features

### ✅ **Resource Protection**
- **Prevent Destroy**: Production resources cannot be accidentally deleted
- **Lifecycle Management**: Smart update detection prevents unnecessary recreations
- **Create Before Destroy**: Zero-downtime updates for Cloud Run services

### 🔄 **State Management**
- **Remote State**: Stored in Google Cloud Storage with versioning
- **State Locking**: Prevents concurrent modifications
- **Backup & Recovery**: Automatic state backups before changes

### 🛡️ **Automatic Rollback**
- **Failure Detection**: Automatically rollback on Terraform apply failures
- **Git-based Recovery**: Rollback to previous working commit
- **Manual Override**: Emergency rollback capabilities

### 📊 **Change Detection**
- **Version Tracking**: Git SHA included in resource metadata
- **Smart Updates**: Only redeploy when actual changes detected
- **Ignore Patterns**: Skip updates for metadata-only changes

## 🏗️ Infrastructure Components Protected

| Component | Lifecycle Rules | Rollback Support |
|-----------|----------------|------------------|
| Cloud Run Services | ✅ Create Before Destroy | ✅ Git-based |
| Storage Buckets | ✅ Prevent Destroy (prod) | ✅ State backup |
| Cloud Run Jobs | ✅ Ignore annotations | ✅ Version tracking |
| Secrets | ✅ Version management | ✅ Automatic |
| Pub/Sub | ✅ Standard protection | ✅ Configuration |

## 📋 Deployment Workflow

### 1. **Planning Phase**
```bash
# Triggered automatically on PR
Action: plan
Result: Shows what will change
Artifacts: terraform-plan.json
```

### 2. **Apply Phase**
```bash
# Triggered on main branch push
Action: apply
Steps:
  1. Backup current state
  2. Validate configuration
  3. Apply changes with monitoring
  4. Auto-rollback on failure
```

### 3. **Rollback Phase**
```bash
# Manual trigger or auto on failure
Action: rollback
Steps:
  1. Identify target commit
  2. Create rollback branch
  3. Apply previous configuration
  4. Validate restoration
```

## 🔐 Environment Configuration

### Development
- **State**: `smartervote-terraform-state/dev/`
- **Protection**: Standard lifecycle rules
- **Rollback**: Automatic on failure

### Staging
- **State**: `smartervote-terraform-state/staging/`
- **Protection**: Enhanced monitoring
- **Rollback**: Manual approval required

### Production
- **State**: `smartervote-terraform-state/prod/`
- **Protection**: `prevent_destroy = true`
- **Rollback**: Emergency procedures + approvals

## 🛠️ Manual Operations

### Initialize Remote State (First Time)
```bash
# Create state bucket manually first
gsutil mb -p YOUR_PROJECT_ID gs://smartervote-terraform-state

# Then run terraform with remote backend
cd infra
terraform init
```

### Force Resource Update
```bash
# Add to terraform variables
force_update = true

# Or target specific resource
terraform apply -target=google_cloud_run_v2_service.races_api
```

### View State History
```bash
# List state versions
gsutil ls -l gs://smartervote-terraform-state/terraform/state/

# Download specific version
gsutil cp gs://smartervote-terraform-state/terraform/state/default.tfstate.1234567890 ./
```

## 🚨 Emergency Procedures

### Complete Infrastructure Failure
1. **Assess Impact**
   ```powershell
   .\scripts\validate-infra.ps1 -Environment prod
   ```

2. **Emergency Rollback**
   ```powershell
   .\scripts\rollback.ps1 -Environment prod
   ```

3. **Manual Recovery** (if needed)
   ```bash
   # Switch to known good commit
   git checkout LAST_KNOWN_GOOD_COMMIT

   # Force apply
   cd infra
   terraform apply -var-file=github-actions.tfvars
   ```

### Terraform State Corruption
1. **Download State Backup**
   ```bash
   # Get from GitHub Actions artifacts
   gh run download --name terraform-state-backup-prod
   ```

2. **Restore State**
   ```bash
   # Copy backup to current state
   cp terraform-state-backup.json terraform.tfstate

   # Verify and refresh
   terraform refresh
   ```

## 📝 Best Practices

### ✅ **Do**
- Always run `plan` before `apply`
- Review GitHub Actions logs before proceeding
- Test changes in `dev` environment first
- Validate infrastructure after deployment
- Keep commit messages descriptive for rollback reference

### ❌ **Don't**
- Skip validation steps in production
- Force apply without understanding changes
- Delete state files manually
- Ignore lifecycle rule warnings
- Deploy to prod without staging validation

## 🔗 Related Documentation

- [Architecture Overview](../docs/architecture.md)
- [Local Development](../docs/local-development.md)
- [Testing Guide](../docs/testing-guide.md)
- [Deployment Validation](../infra/DEPLOYMENT-VALIDATION.md)

## 🆘 Support

If you encounter issues:

1. **Check Infrastructure Status**
   ```powershell
   .\scripts\validate-infra.ps1 -Environment ENVIRONMENT
   ```

2. **Review GitHub Actions Logs**
   ```bash
   gh run list --workflow=terraform-deploy.yaml
   gh run view RUN_ID --log
   ```

3. **Emergency Contact**
   - Slack: `#smartervote-alerts`
   - Email: `devops@smartervote.example`
   - On-call: Check PagerDuty rotation
