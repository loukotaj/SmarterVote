# SmarterVote Infrastructure Validation Script
# PowerShell script to validate infrastructure deployment

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("dev", "staging", "prod")]
    [string]$Environment
)

Write-Host "SmarterVote Infrastructure Validation" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Environment: $Environment" -ForegroundColor Yellow
Write-Host ""

# Check if gcloud is installed and authenticated
if (!(Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "Error: gcloud CLI is required" -ForegroundColor Red
    exit 1
}

# Get project ID from gcloud config
$projectId = gcloud config get-value project 2>$null
if (!$projectId) {
    Write-Host "Error: No GCP project configured" -ForegroundColor Red
    Write-Host "Run: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Yellow
    exit 1
}

Write-Host "Project: $projectId" -ForegroundColor Cyan
Write-Host ""

# Validation results
$validationResults = @()

function Test-Resource {
    param($Name, $Command, $ExpectedOutput = $null)

    Write-Host "Checking $Name..." -ForegroundColor Gray

    try {
        $result = Invoke-Expression $Command 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            Write-Host "  $($Name): OK" -ForegroundColor Green
            $script:validationResults += @{Name = $Name; Status = "OK"; Details = $result}
        } else {
            Write-Host "  $($Name): FAILED" -ForegroundColor Red
            $script:validationResults += @{Name = $Name; Status = "FAILED"; Details = "No result"}
        }
    } catch {
        Write-Host "  $($Name): ERROR - $_" -ForegroundColor Red
        $script:validationResults += @{Name = $Name; Status = "ERROR"; Details = $_.Exception.Message}
    }
}

# Test Cloud Run services
Write-Host "Validating Cloud Run Services" -ForegroundColor Cyan
Test-Resource "Enqueue API" "gcloud run services describe enqueue-api-$Environment --region=us-central1 --format='value(status.url)'"
Test-Resource "Races API" "gcloud run services describe races-api-$Environment --region=us-central1 --format='value(status.url)'"

# Test Cloud Run Job
Write-Host ""
Write-Host "Validating Cloud Run Jobs" -ForegroundColor Cyan
Test-Resource "Race Worker Job" "gcloud run jobs describe race-worker-$Environment --region=us-central1 --format='value(metadata.name)'"

# Test Storage Buckets
Write-Host ""
Write-Host "Validating Storage Buckets" -ForegroundColor Cyan
Test-Resource "Data Bucket" "gsutil ls gs://$projectId-sv-data-$Environment"
Test-Resource "ChromaDB Bucket" "gsutil ls gs://$projectId-chroma-storage-$Environment"

# Test Pub/Sub
Write-Host ""
Write-Host "Validating Pub/Sub" -ForegroundColor Cyan
Test-Resource "Race Jobs Topic" "gcloud pubsub topics describe race-jobs-$Environment"
Test-Resource "Race Jobs Subscription" "gcloud pubsub subscriptions describe race-jobs-sub-$Environment"

# Test Secret Manager
Write-Host ""
Write-Host "Validating Secret Manager" -ForegroundColor Cyan
Test-Resource "OpenAI API Key" "gcloud secrets describe openai-api-key-$Environment"
Test-Resource "Anthropic API Key" "gcloud secrets describe anthropic-api-key-$Environment"
Test-Resource "Grok API Key" "gcloud secrets describe grok-api-key-$Environment"

# Test API endpoints if services are running
Write-Host ""
Write-Host "Testing API Endpoints" -ForegroundColor Cyan

$enqueueUrl = gcloud run services describe "enqueue-api-$Environment" --region=us-central1 --format='value(status.url)' 2>$null
if ($enqueueUrl) {
    try {
        $response = Invoke-WebRequest -Uri "$enqueueUrl/health" -Method GET -TimeoutSec 30 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Host "  Enqueue API Health: OK" -ForegroundColor Green
        } else {
            Write-Host "  Enqueue API Health: HTTP $($response.StatusCode)" -ForegroundColor Red
        }
    } catch {
        Write-Host "  Enqueue API Health: UNREACHABLE" -ForegroundColor Red
    }
}

$racesUrl = gcloud run services describe "races-api-$Environment" --region=us-central1 --format='value(status.url)' 2>$null
if ($racesUrl) {
    try {
        $response = Invoke-WebRequest -Uri "$racesUrl/health" -Method GET -TimeoutSec 30 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Host "  Races API Health: OK" -ForegroundColor Green
        } else {
            Write-Host "  Races API Health: HTTP $($response.StatusCode)" -ForegroundColor Red
        }
    } catch {
        Write-Host "  Races API Health: UNREACHABLE" -ForegroundColor Red
    }
}

# Summary
Write-Host ""
Write-Host "Validation Summary" -ForegroundColor Cyan
Write-Host "=====================" -ForegroundColor Cyan

$okCount = ($validationResults | Where-Object { $_.Status -eq "OK" }).Count
$failedCount = ($validationResults | Where-Object { $_.Status -ne "OK" }).Count
$totalCount = $validationResults.Count

Write-Host "Total Checks: $totalCount" -ForegroundColor White
Write-Host "Passed: $okCount" -ForegroundColor Green
Write-Host "Failed: $failedCount" -ForegroundColor Red

if ($failedCount -eq 0) {
    Write-Host ""
    Write-Host "All infrastructure components are healthy!" -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "Infrastructure validation failed!" -ForegroundColor Red
    Write-Host "Failed components:" -ForegroundColor Yellow
    $validationResults | Where-Object { $_.Status -ne "OK" } | ForEach-Object {
        Write-Host "  - $($_.Name): $($_.Status)" -ForegroundColor Red
    }
    exit 1
}
