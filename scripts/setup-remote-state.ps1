# SmarterVote Terraform State Migration Script
# One-time script to migrate from local to remote state

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,

    [Parameter(Mandatory=$false)]
    [string]$Region = "us-central1"
)

Write-Host "SmarterVote Terraform State Migration" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "Project: $ProjectId" -ForegroundColor Yellow
Write-Host "Region: $Region" -ForegroundColor Yellow
Write-Host ""

# Check prerequisites
if (!(Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "Error: gcloud CLI is required" -ForegroundColor Red
    exit 1
}

if (!(Get-Command terraform -ErrorAction SilentlyContinue)) {
    Write-Host "Error: terraform CLI is required" -ForegroundColor Red
    exit 1
}

# Check Google Cloud authentication
Write-Host "Checking Google Cloud authentication..." -ForegroundColor Cyan
try {
    $authResult = gcloud auth list --filter="status:ACTIVE" --format="value(account)" 2>$null
    if ($LASTEXITCODE -ne 0 -or !$authResult) {
        Write-Host "  No active Google Cloud authentication found" -ForegroundColor Yellow
        Write-Host "  Please run: gcloud auth login" -ForegroundColor Yellow
        Write-Host "  Then run: gcloud auth application-default login" -ForegroundColor Yellow
        exit 1
    } else {
        Write-Host "  Authenticated as: $authResult" -ForegroundColor Green
    }
} catch {
    Write-Host "  Failed to check authentication: $_" -ForegroundColor Red
    exit 1
}

# Set gcloud project
Write-Host "Setting gcloud project..." -ForegroundColor Cyan
gcloud config set project $ProjectId

# Check if state bucket already exists
$bucketName = "smartervote-terraform-state"
Write-Host "Checking if state bucket exists..." -ForegroundColor Cyan

$bucketExists = $false
try {
    gsutil ls -b "gs://$bucketName" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $bucketExists = $true
        Write-Host "  State bucket already exists: gs://$bucketName" -ForegroundColor Green
    }
} catch {
    # Bucket doesn't exist, we'll create it
}

if (!$bucketExists) {
    Write-Host "  Creating state bucket: gs://$bucketName" -ForegroundColor Yellow

    try {
        gsutil mb -p $ProjectId -l $Region "gs://$bucketName"
        gsutil versioning set on "gs://$bucketName"

        Write-Host "  State bucket created successfully" -ForegroundColor Green
    } catch {
        Write-Host "  Failed to create state bucket: $_" -ForegroundColor Red
        exit 1
    }
}

# Check if we have existing local state
# Resolve script directory in a way compatible with Windows PowerShell 5.1
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$infraParent = Join-Path $scriptDir ".."
$infraDir = Join-Path $infraParent "infra"
$infraDir = [System.IO.Path]::GetFullPath($infraDir)

$localStateFile = Join-Path $infraDir "terraform.tfstate"

# Check for required terraform variable files
$terraformTfvars = Join-Path $infraDir "terraform.tfvars"
$secretsTfvars = Join-Path $infraDir "secrets.tfvars"

if (!(Test-Path $terraformTfvars)) {
    Write-Host ""
    Write-Host "Error: terraform.tfvars file not found at: $terraformTfvars" -ForegroundColor Red
    Write-Host "This file should have been created automatically. Please check the infra directory." -ForegroundColor Yellow
    exit 1
}

if (!(Test-Path $secretsTfvars)) {
    Write-Host ""
    Write-Host "Error: secrets.tfvars file not found at: $secretsTfvars" -ForegroundColor Red
    Write-Host "Please run: .\scripts\setup-secrets.ps1 -ProjectId $ProjectId" -ForegroundColor Yellow
    Write-Host "Then edit the secrets.tfvars file to add your API keys before continuing." -ForegroundColor Yellow
    exit 1
}

# Check if secrets.tfvars has placeholder values
$secretsContent = Get-Content $secretsTfvars -Raw
if ($secretsContent -match "your-gcp-project-id" -or $secretsContent -match "sk-your-openai-api-key") {
    Write-Host ""
    Write-Host "Warning: secrets.tfvars contains placeholder values" -ForegroundColor Yellow
    Write-Host "Please update the following in $secretsTfvars:" -ForegroundColor Yellow
    Write-Host "  1. Replace 'your-gcp-project-id' with your actual GCP project ID: $ProjectId" -ForegroundColor Gray
    Write-Host "  2. Replace 'sk-your-openai-api-key' with your actual OpenAI API key" -ForegroundColor Gray
    Write-Host "  3. Replace 'your-anthropic-api-key' with your actual Anthropic API key" -ForegroundColor Gray
    Write-Host "  4. Update other placeholder values as needed" -ForegroundColor Gray
    Write-Host ""

    $proceed = Read-Host "Do you want to continue anyway? (y/N)"
    if ($proceed -ne "y" -and $proceed -ne "Y") {
        Write-Host "Setup cancelled. Please update secrets.tfvars and run again." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "  Found required configuration files" -ForegroundColor Green

if (Test-Path $localStateFile) {
    Write-Host ""
    Write-Host "Local state file found: $localStateFile" -ForegroundColor Yellow

    $migrate = Read-Host "Do you want to migrate existing state to remote backend? (y/N)"
    if ($migrate -eq "y" -or $migrate -eq "Y") {

        # Backup local state first
        $backupFile = Join-Path $infraDir "terraform.tfstate.local-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item $localStateFile $backupFile
        Write-Host "  Local state backed up to: $backupFile" -ForegroundColor Cyan

        # Initialize with remote backend (this will prompt for migration)
        Push-Location $infraDir
        try {
            Write-Host "  Initializing with remote backend..." -ForegroundColor Cyan
            Write-Host "  You will be prompted to migrate existing state - answer 'yes'" -ForegroundColor Yellow

            terraform init -reconfigure

            if ($LASTEXITCODE -eq 0) {
                Write-Host "  State migration completed successfully!" -ForegroundColor Green

                # Verify remote state
                terraform state list > remote-state-verification.txt
                $resourceCount = (Get-Content remote-state-verification.txt).Count
                Write-Host "  Verified $resourceCount resources in remote state" -ForegroundColor Green
                Remove-Item remote-state-verification.txt

            } else {
                Write-Host "  State migration failed" -ForegroundColor Red
                Write-Host "  You can restore from backup: $backupFile" -ForegroundColor Yellow
            }

        } finally {
            Pop-Location
        }
    }
} else {
    Write-Host ""
    Write-Host "No local state file found - setting up remote backend..." -ForegroundColor Yellow

    Push-Location $infraDir
    try {
        terraform init

        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Remote backend initialized successfully!" -ForegroundColor Green
        } else {
            Write-Host "  Remote backend initialization failed" -ForegroundColor Red
        }

    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Test deployment: .\scripts\deploy.ps1 -Environment dev -Action plan" -ForegroundColor Gray
Write-Host "2. Validate infrastructure: .\scripts\validate-infra.ps1 -Environment dev" -ForegroundColor Gray
Write-Host "3. Deploy to dev: .\scripts\deploy.ps1 -Environment dev -Action apply" -ForegroundColor Gray
Write-Host ""
Write-Host "Important: Make sure your secrets.tfvars file has valid values before deploying!" -ForegroundColor Yellow
Write-Host ""
Write-Host "Migration completed!" -ForegroundColor Green
