# Deploy the pipeline-client service to Cloud Run.
#
# Usage:
#   .\scripts\deploy_pipeline_client.ps1              # build + push + deploy
#   .\scripts\deploy_pipeline_client.ps1 -NoBuild     # deploy existing image only

param(
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$ProjectId   = "smartervote"
$Region      = "us-central1"
$Environment = "dev"
$Service     = "pipeline-client-$Environment"
$Image       = "$Region-docker.pkg.dev/$ProjectId/smartervote-$Environment/pipeline-client:latest"
$RepoRoot    = Split-Path $PSScriptRoot -Parent

if (-not $NoBuild) {
    Write-Host "==> Building Docker image..."
    docker build -f "$RepoRoot\pipeline_client\Dockerfile" -t $Image $RepoRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "==> Configuring Docker auth..."
    gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "==> Pushing image to Artifact Registry..."
    docker push $Image
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Check if service already exists (suppress error — non-zero exit is expected when service is new)
$ErrorActionPreference = "Continue"
$existsOutput = gcloud run services describe $Service --region $Region --project $ProjectId --format 'value(name)' 2>&1
$serviceExists = ($LASTEXITCODE -eq 0) -and ($existsOutput -notmatch "ERROR")
$ErrorActionPreference = "Stop"

$Bucket  = "smartervote-sv-data-$Environment"

# Look up the races-api URL so analytics proxy can reach it
Write-Host "==> Looking up races-api URL..."
$RacesApiService = "races-api-$Environment"
$RacesApiUrl = gcloud run services describe $RacesApiService --region $Region --project $ProjectId --format 'value(status.url)' 2>$null
if (-not $RacesApiUrl) {
    Write-Warning "Could not resolve races-api URL; RACES_API_URL will not be updated"
    $RacesApiUrl = ""
}

# Use ^;^ as delimiter so commas inside values don't confuse gcloud
$envParts = @(
    "PROJECT_ID=$ProjectId",
    "ENVIRONMENT=$Environment",
    "LOG_LEVEL=DEBUG",
    "STORAGE_MODE=gcp",
    "GCS_BUCKET=$Bucket",
    "GCS_BUCKET_NAME=$Bucket",
    "BUCKET_NAME=$Bucket",
    "FIRESTORE_PROJECT=$ProjectId",
    "AUTH0_DOMAIN=dev-t37rz-ur.auth0.com",
    "AUTH0_AUDIENCE=https://pipeline-client.smarter.vote",
    "ALLOWED_ORIGINS=https://smarter.vote,https://www.smarter.vote,http://localhost:5173,http://localhost:4173"
)
if ($RacesApiUrl) { $envParts += "RACES_API_URL=$RacesApiUrl" }
$envVars = "^;^" + ($envParts -join ";")

# --update-secrets merges with existing secrets instead of replacing them,
# so Terraform-managed secrets (e.g. ADMIN_API_KEY) are preserved.
$secrets  = "OPENAI_API_KEY=openai-api-key-${Environment}:latest,SERPER_API_KEY=serper-api-key-${Environment}:latest,ANTHROPIC_API_KEY=anthropic-api-key-${Environment}:latest,GEMINI_API_KEY=gemini-api-key-${Environment}:latest,XAI_API_KEY=xai-api-key-${Environment}:latest"

if (-not $serviceExists) {
    Write-Host "==> Service $Service does not exist - deploying fresh..."
    gcloud run deploy $Service `
        --region $Region `
        --project $ProjectId `
        --image $Image `
        --port 8001 `
        --memory 2Gi `
        --cpu 2 `
        --min-instances 0 `
        --max-instances 1 `
        --allow-unauthenticated `
        --update-env-vars $envVars `
        --update-secrets $secrets
} else {
    Write-Host "==> Updating $Service..."
    gcloud run services update $Service `
        --region $Region `
        --project $ProjectId `
        --image $Image `
        --update-env-vars $envVars `
        --update-secrets $secrets
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Service URL:"
gcloud run services describe $Service --region $Region --project $ProjectId --format 'value(status.url)'
