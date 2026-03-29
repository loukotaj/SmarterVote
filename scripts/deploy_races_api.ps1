# Deploy the races-api service to Cloud Run.
#
# Usage:
#   .\scripts\deploy_races_api.ps1              # build + push + deploy
#   .\scripts\deploy_races_api.ps1 -NoBuild     # deploy existing image only

param(
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$ProjectId  = "smartervote"
$Region     = "us-central1"
$Environment = "dev"
$Service    = "races-api-$Environment"
$Image      = "$Region-docker.pkg.dev/$ProjectId/smartervote-$Environment/races-api:latest"
$RepoRoot   = Split-Path $PSScriptRoot -Parent

if (-not $NoBuild) {
    Write-Host "==> Building Docker image..."
    docker build -f "$RepoRoot\services\races-api\Dockerfile" -t $Image $RepoRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "==> Configuring Docker auth..."
    gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "==> Pushing image to Artifact Registry..."
    docker push $Image
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "==> Deploying $Service to Cloud Run..."
gcloud run services update $Service `
    --region $Region `
    --project $ProjectId `
    --image $Image
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Service URL:"
gcloud run services describe $Service `
    --region $Region `
    --project $ProjectId `
    --format "value(status.url)"
