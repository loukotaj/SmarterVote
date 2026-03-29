# SmarterVote Development Server Launcher
# This script starts the pipeline client, races API, and web frontend

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host @"

╔═══════════════════════════════════════════════════════════════╗
║            SmarterVote Local Development                      ║
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

Write-Host "OK  Prerequisites check passed!" -ForegroundColor Green

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
$projectRoot = $PWD.Path
$env:PYTHONPATH = $projectRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

# Helper: launch a service in a new titled window, return the process handle
function Start-Service {
    param([string]$Label, [string]$Command, [string]$WorkDir = $projectRoot)
    $proc = Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", $Command `
        -WorkingDirectory $WorkDir `
        -PassThru
    Write-Host "  Started: $Label  (PID $($proc.Id))" -ForegroundColor DarkGreen
    return $proc
}

$pipelineProc = Start-Service "Pipeline API  :8001" `
    "[Console]::Title='Pipeline API :8001'; [Console]::OutputEncoding=[Text.Encoding]::UTF8; `$env:PYTHONPATH='$projectRoot'; & '$pythonExe' -m uvicorn pipeline_client.backend.main:app --host 127.0.0.1 --port 8001 --reload"

$apiProc = Start-Service "Races API     :8080" `
    "[Console]::Title='Races API :8080'; [Console]::OutputEncoding=[Text.Encoding]::UTF8; `$env:PYTHONPATH='$projectRoot'; & '$pythonExe' -m uvicorn main:app --host 127.0.0.1 --port 8080 --reload" `
    (Join-Path $projectRoot "services\races-api")

$webProc = Start-Service "Web Frontend  :5173" `
    "[Console]::Title='Web Frontend :5173'; npm run dev" `
    (Join-Path $projectRoot "web")

# Wait briefly for services to bind their ports
Start-Sleep -Seconds 3

Write-Host @"

╔═══════════════════════════════════════════════════════════════╗
║                    Services Running                           ║
╠═══════════════════════════════════════════════════════════════╣
║  Web Dashboard:       http://localhost:5173                   ║
║  Pipeline Admin:      http://localhost:5173/admin/pipeline    ║
║  Pipeline API Docs:   http://localhost:8001/docs              ║
║  Races API Docs:      http://localhost:8080/docs              ║
╠═══════════════════════════════════════════════════════════════╣
║  Press Ctrl+C to stop all services                            ║
╚═══════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Green

try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Write-Host ""
    Write-Host "Shutting down services..." -ForegroundColor Yellow
    foreach ($proc in @($pipelineProc, $apiProc, $webProc)) {
        if ($proc -and -not $proc.HasExited) {
            # /T kills the entire process tree (window + uvicorn/node children)
            taskkill /F /T /PID $proc.Id 2>$null
        }
    }
    Write-Host "All services stopped." -ForegroundColor Green
}
