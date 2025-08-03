# SmarterVote Infrastructure Deployment Script (PowerShell)

Write-Host "🚀 SmarterVote Infrastructure Deployment" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# Check if secrets.tfvars exists
if (!(Test-Path "secrets.tfvars")) {
    Write-Host "❌ Error: secrets.tfvars file not found" -ForegroundColor Red
    Write-Host "Please copy secrets.tfvars.example to secrets.tfvars and fill in your values" -ForegroundColor Yellow
    exit 1
}

# Check if required tools are installed
try {
    terraform --version | Out-Null
} catch {
    Write-Host "❌ Error: terraform is required but not installed." -ForegroundColor Red
    exit 1
}

try {
    gcloud --version | Out-Null
} catch {
    Write-Host "❌ Error: gcloud CLI is required but not installed." -ForegroundColor Red
    exit 1
}

# Check if user is authenticated with gcloud
$activeAccount = gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null
if ([string]::IsNullOrEmpty($activeAccount)) {
    Write-Host "❌ Error: Not authenticated with gcloud. Please run: gcloud auth login" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Prerequisites check passed" -ForegroundColor Green

# Get project ID from secrets.tfvars
$projectId = (Get-Content secrets.tfvars | Where-Object { $_ -match 'project_id' } | ForEach-Object { ($_ -split '"')[1] })
Write-Host "📋 Project ID: $projectId" -ForegroundColor Cyan

# Set gcloud project
Write-Host "🔧 Setting gcloud project..." -ForegroundColor Yellow
gcloud config set project $projectId

# Initialize Terraform
Write-Host "🔄 Initializing Terraform..." -ForegroundColor Yellow
terraform init

# Validate configuration
Write-Host "✅ Validating Terraform configuration..." -ForegroundColor Yellow
terraform validate

# Plan deployment
Write-Host "📋 Planning deployment..." -ForegroundColor Yellow
terraform plan -var-file=secrets.tfvars

# Ask for confirmation
$confirmation = Read-Host "Do you want to proceed with the deployment? (y/N)"
if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
    Write-Host "❌ Deployment cancelled" -ForegroundColor Red
    exit 0
}

# Apply configuration
Write-Host "🚀 Deploying infrastructure..." -ForegroundColor Green
terraform apply -var-file=secrets.tfvars -auto-approve

Write-Host "✅ Infrastructure deployment completed!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Next steps:" -ForegroundColor Cyan
Write-Host "1. Build and push your Docker images:" -ForegroundColor White
Write-Host "   - cd ../pipeline && docker build -t gcr.io/$projectId/smartervote-pipeline:latest ." -ForegroundColor Gray
Write-Host "   - docker push gcr.io/$projectId/smartervote-pipeline:latest" -ForegroundColor Gray
Write-Host "   - cd ../services/enqueue-api && docker build -t gcr.io/$projectId/smartervote-enqueue-api:latest ." -ForegroundColor Gray
Write-Host "   - docker push gcr.io/$projectId/smartervote-enqueue-api:latest" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Update Cloud Run services to use the new images" -ForegroundColor White
Write-Host "3. Test the enqueue API endpoint" -ForegroundColor White
