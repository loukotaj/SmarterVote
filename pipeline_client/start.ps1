# Enhanced Pipeline Client Startup Script
# This script starts the enhanced pipeline client with live logging

param(
    [string]$Port = "8001",
    [string]$ServerHostess = "0.0.0.0",
    [switch]$Dev = $false
)

Write-Host "Starting Enhanced Pipeline Client..." -ForegroundColor Green
Write-Host "Features: Live Logging, Run Management, Real-time Dashboard" -ForegroundColor Cyan

# Check if we're in the correct directory
$currentDir = Get-Location
if (-not (Test-Path "backend/main.py")) {
    Write-Host "Error: Please run this script from the pipeline_client directory" -ForegroundColor Red
    Write-Host "Current directory: $currentDir" -ForegroundColor Yellow
    exit 1
}

# Check if Python virtual environment exists
$venvPath = "../.venv"
if (Test-Path $venvPath) {
    Write-Host "Found virtual environment at $venvPath" -ForegroundColor Green

    # Activate virtual environment
    $activateScript = "$venvPath/Scripts/Activate.ps1"
    if (Test-Path $activateScript) {
        Write-Host "Activating virtual environment..." -ForegroundColor Yellow
        & $activateScript
    } else {
        Write-Host "Virtual environment found but activation script missing" -ForegroundColor Yellow
    }
} else {
    Write-Host "No virtual environment found at $venvPath" -ForegroundColor Yellow
    Write-Host "   You may need to install dependencies manually" -ForegroundColor Yellow
}

# Install/update dependencies
Write-Host "Installing/updating dependencies..." -ForegroundColor Yellow
try {
    pip install -r backend/requirements.txt
    Write-Host "Dependencies installed successfully" -ForegroundColor Green
} catch {
    Write-Host "Failed to install dependencies: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "   Continuing anyway..." -ForegroundColor Yellow
}

# Create necessary directories
$directories = @("runs", "artifacts")
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created directory: $dir" -ForegroundColor Cyan
    }
}

# Set environment variables
$env:PYTHONPATH = (Get-Location).Parent.FullName

if ($Dev) {
    Write-Host "Starting in development mode..." -ForegroundColor Magenta
    Write-Host "   Hot reload enabled" -ForegroundColor Cyan

    # Start with auto-reload for development
    python -m uvicorn backend.main:app --host $ServerHostess --port $Port --reload
} else {
    Write-Host "Starting production server..." -ForegroundColor Green
    Write-Host "   Server will be available at: http://$ServerHostess`:$Port" -ForegroundColor Cyan
    Write-Host "   Dashboard: http://localhost:$Port" -ForegroundColor Cyan
    Write-Host "   API Docs: http://localhost:$Port/docs" -ForegroundColor Cyan

    # Start with the custom run script
    python run.py
}
