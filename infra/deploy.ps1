# SmarterVote Infrastructure Deployment Script (PowerShell)

Write-Host "SmarterVote Infrastructure Deployment" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# Check if secrets.tfvars exists
if (!(Test-Path "secrets.tfvars")) {
    Write-Host "Error: secrets.tfvars file not found" -ForegroundColor Red
    Write-Host "Please copy secrets.tfvars.example to secrets.tfvars and fill in your values" -ForegroundColor Yellow
    exit 1
}

# Check if required tools are installed
try {
    terraform --version | Out-Null
} catch {
    Write-Host "Error: terraform is required but not installed." -ForegroundColor Red
    exit 1
}

try {
    gcloud --version | Out-Null
} catch {
    Write-Host "Error: gcloud CLI is required but not installed." -ForegroundColor Red
    exit 1
}

# Check if user is authenticated with gcloud
$activeAccount = gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null
if ([string]::IsNullOrEmpty($activeAccount)) {
    Write-Host "Error: Not authenticated with gcloud. Please run: gcloud auth login" -ForegroundColor Red
    exit 1
}

Write-Host "Prerequisites check passed" -ForegroundColor Green

# Get project ID from secrets.tfvars
$projectId = (Get-Content secrets.tfvars | Where-Object { $_ -match 'project_id' } | ForEach-Object { ($_ -split '"')[1] })
$region = (Get-Content secrets.tfvars | Where-Object { $_ -match 'region' } | ForEach-Object { ($_ -split '"')[1] })
if ([string]::IsNullOrEmpty($region)) { $region = "us-central1" }

Write-Host "Project ID: $projectId" -ForegroundColor Cyan
Write-Host "Region: $region" -ForegroundColor Cyan

# Set gcloud project
Write-Host "Setting gcloud project..." -ForegroundColor Yellow
gcloud config set project $projectId

# Initialize Terraform
Write-Host "Initializing Terraform..." -ForegroundColor Yellow
terraform init

# Validate configuration
Write-Host "Validating Terraform configuration..." -ForegroundColor Yellow
terraform validate

# Plan deployment
Write-Host "Planning deployment..." -ForegroundColor Yellow
terraform plan -var-file=secrets.tfvars

# Ask for confirmation
$confirmation = Read-Host "Do you want to proceed with the deployment? (y/N)"
if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
    Write-Host "Deployment cancelled" -ForegroundColor Red
    exit 0
}

# Apply configuration
Write-Host "Deploying infrastructure..." -ForegroundColor Green
terraform apply -var-file=secrets.tfvars -auto-approve

Write-Host "Infrastructure deployment completed!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Build and push the races-api Docker image to Artifact Registry:" -ForegroundColor White
Write-Host "   - gcloud auth configure-docker $region-docker.pkg.dev" -ForegroundColor Gray
Write-Host "   - cd ../services/races-api && docker build -t $region-docker.pkg.dev/$projectId/smartervote-dev/races-api:latest ." -ForegroundColor Gray
Write-Host "   - docker push $region-docker.pkg.dev/$projectId/smartervote-dev/races-api:latest" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Build and push the pipeline worker image used by the pipeline Cloud Run Job" -ForegroundColor White
Write-Host "3. Update the races-api service and pipeline Job image tags if they changed" -ForegroundColor White
Write-Host "4. Test the API endpoints and queue a smoke race through the admin UI" -ForegroundColor White
