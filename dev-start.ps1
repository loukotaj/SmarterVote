# SmarterVote Development Server Launcher
# This script starts the pipeline client, races API, and web frontend

Write-Host @"

╔═══════════════════════════════════════════════════════════════╗
║              🗳️  SmarterVote Local Development                 ║
╚═══════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# Function to check if a command exists
function Test-Command($command) {
    try {
        if (Get-Command $command -ErrorAction Stop) { return $true }
    } catch { return $false }
}

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

if (-not (Test-Command "python")) {
    Write-Host "ERROR: Python not found. Please install Python 3.10+ and add it to PATH." -ForegroundColor Red
    exit 1
}

if (-not (Test-Command "node")) {
    Write-Host "ERROR: Node.js not found. Please install Node.js 22+ and add it to PATH." -ForegroundColor Red
    exit 1
}

if (-not (Test-Command "npm")) {
    Write-Host "ERROR: npm not found. Please install npm 10+ and add it to PATH." -ForegroundColor Red
    exit 1
}

Write-Host "✅ Prerequisites check passed!" -ForegroundColor Green

# Check if data files exist
if (-not (Test-Path "data\published\*.json")) {
    Write-Host "WARNING: No race data files found in data\published\." -ForegroundColor Yellow
    if (-not (Test-Path "data\published")) {
        New-Item -ItemType Directory -Path "data\published" -Force | Out-Null
    }
}

# Create necessary directories
$directories = @("data\published", "data\chroma_db", "pipeline_client\artifacts", "pipeline_client\runs")
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

Write-Host ""
Write-Host "Starting services..." -ForegroundColor Yellow

# Set common environment
$env:PYTHONPATH = $PWD

# Start Pipeline Client API (port 8001)
$pipelineJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    $env:PYTHONPATH = $using:PWD
    Set-Location "pipeline_client"
    & "$using:PWD\.venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
}

# Start Races API (port 8080)
$apiJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    $env:PYTHONPATH = $using:PWD
    Set-Location "services\races-api"
    & "$using:PWD\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8080 --reload
}

# Function to start web frontend
$webJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    Set-Location "web"
    npm install --silent 2>$null
    npm run dev -- --host
}

# Wait for services to start
Start-Sleep -Seconds 3

Write-Host @"

╔═══════════════════════════════════════════════════════════════╗
║                   🚀 Services Running                         ║
╠═══════════════════════════════════════════════════════════════╣
║  Web Dashboard:       http://localhost:5173                   ║
║  Pipeline Admin:      http://localhost:5173/admin/pipeline    ║
║  Pipeline API Docs:   http://localhost:8001/docs              ║
║  Races API Docs:      http://localhost:8080/docs              ║
╠═══════════════════════════════════════════════════════════════╣
║  Press Ctrl+C to stop all services                            ║
╚═══════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Green

Write-Host "Waiting for services to fully initialize..." -ForegroundColor Yellow
Write-Host ""

try {
    # Wait for all jobs to complete or user interruption
    while ($pipelineJob.State -eq 'Running' -or $apiJob.State -eq 'Running' -or $webJob.State -eq 'Running') {
        Start-Sleep -Seconds 2

        # Check if any job failed
        if ($pipelineJob.State -eq 'Failed') {
            Write-Host "ERROR: Pipeline API failed to start:" -ForegroundColor Red
            Receive-Job $pipelineJob
        }
        if ($apiJob.State -eq 'Failed') {
            Write-Host "ERROR: Races API failed to start:" -ForegroundColor Red
            Receive-Job $apiJob
        }
        if ($webJob.State -eq 'Failed') {
            Write-Host "ERROR: Web Frontend failed to start:" -ForegroundColor Red
            Receive-Job $webJob
        }
    }
} catch {
    Write-Host ""
    Write-Host "Shutting down services..." -ForegroundColor Yellow
} finally {
    # Clean up jobs
    if ($pipelineJob) {
        Stop-Job $pipelineJob -ErrorAction SilentlyContinue
        Remove-Job $pipelineJob -Force -ErrorAction SilentlyContinue
    }
    if ($apiJob) {
        Stop-Job $apiJob -ErrorAction SilentlyContinue
        Remove-Job $apiJob -Force -ErrorAction SilentlyContinue
    }
    if ($webJob) {
        Stop-Job $webJob -ErrorAction SilentlyContinue
        Remove-Job $webJob -Force -ErrorAction SilentlyContinue
    }
    Write-Host "All services stopped." -ForegroundColor Green
}
