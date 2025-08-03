# SmarterVote Development Server Launcher
# This script starts both the races API and the web frontend

Write-Host "Starting SmarterVote Development Environment" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

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

Write-Host "Prerequisites check passed!" -ForegroundColor Green

# Check if data files exist
if (-not (Test-Path "data\published\*.json")) {
    Write-Host "WARNING: No race data files found in data\published\. Creating demo data..." -ForegroundColor Yellow
    if (-not (Test-Path "data\published")) {
        New-Item -ItemType Directory -Path "data\published" -Force | Out-Null
    }
    Write-Host "Demo data should be available. If races API shows no data, check data\published\ directory." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Starting services..." -ForegroundColor Yellow

# Function to start races API
$apiJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    Set-Location "services\races-api"
    Write-Host "Starting Races API on http://localhost:8080" -ForegroundColor Cyan
    $env:PYTHONPATH = $using:PWD
    $env:DATA_DIR = "../../data/published"
    & "$using:PWD\.venv\Scripts\python.exe" main.py
}

# Function to start web frontend  
$webJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    Set-Location "web"
    Write-Host "Installing npm dependencies..." -ForegroundColor Cyan
    npm install --silent
    Write-Host "Starting Web Frontend on http://localhost:3000" -ForegroundColor Cyan
    npm run dev
}

Write-Host ""
Write-Host "Services are starting up..." -ForegroundColor Green
Write-Host "Races API: http://localhost:8080" -ForegroundColor Cyan
Write-Host "Web Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Please wait 10-15 seconds for services to fully start..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Available API endpoints:" -ForegroundColor White
Write-Host "  GET http://localhost:8080/races - List all races" -ForegroundColor Gray
Write-Host "  GET http://localhost:8080/races/tx-governor-2024 - Get specific race" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop both services" -ForegroundColor Red
Write-Host ""

try {
    # Wait for both jobs to complete or user interruption
    while ($apiJob.State -eq 'Running' -or $webJob.State -eq 'Running') {
        Start-Sleep -Seconds 2
        
        # Check if either job failed
        if ($apiJob.State -eq 'Failed') {
            Write-Host "ERROR: Races API failed to start. Check error below:" -ForegroundColor Red
            Receive-Job $apiJob
            break
        }
        if ($webJob.State -eq 'Failed') {
            Write-Host "ERROR: Web Frontend failed to start. Check error below:" -ForegroundColor Red
            Receive-Job $webJob
            break
        }
    }
} catch {
    Write-Host ""
    Write-Host "Shutting down services..." -ForegroundColor Yellow
} finally {
    # Clean up jobs
    if ($apiJob) {
        Stop-Job $apiJob -PassThru | Remove-Job
    }
    if ($webJob) {
        Stop-Job $webJob -PassThru | Remove-Job
    }
    Write-Host "All services stopped." -ForegroundColor Green
}
