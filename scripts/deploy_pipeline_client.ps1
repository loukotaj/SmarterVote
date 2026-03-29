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

# Check if service already exists
$existsOutput = gcloud run services describe $Service --region $Region --project $ProjectId --format 'value(name)' 2>&1
$serviceExists = ($LASTEXITCODE -eq 0) -and ($existsOutput -notmatch "ERROR")

$envVars = "PROJECT_ID=$ProjectId,ENVIRONMENT=$Environment,LOG_LEVEL=DEBUG,STORAGE_MODE=gcp,GCS_BUCKET_NAME=smartervote-sv-data-$Environment"
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
        --set-env-vars $envVars `
        --set-secrets $secrets
} else {
    Write-Host "==> Updating $Service..."
    gcloud run services update $Service `
        --region $Region `
        --project $ProjectId `
        --image $Image `
        --set-env-vars $envVars `
        --set-secrets $secrets
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Service URL:"
gcloud run services describe $Service --region $Region --project $ProjectId --format 'value(status.url)'
