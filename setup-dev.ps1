# SmarterVote Development Environment Setup Script
# Installs pre-commit hooks and ensures proper development setup

Write-Host "🚀 Setting up SmarterVote development environment..." -ForegroundColor Green

# Check if we're in the right directory
if (-not (Test-Path ".pre-commit-config.yaml")) {
    Write-Host "❌ Error: .pre-commit-config.yaml not found. Are you in the project root?" -ForegroundColor Red
    exit 1
}

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-Host "❌ Error: Virtual environment not found. Please run 'python -m venv .venv' first." -ForegroundColor Red
    exit 1
}

# Set up the pre-commit executable path
$precommitPath = ".\.venv\Scripts\pre-commit.exe"

# Function to run commands with error handling
function Invoke-SafeCommand {
    param(
        [string]$Command,
        [string]$Description
    )

    Write-Host "🔧 $Description..." -ForegroundColor Cyan

    try {
        Invoke-Expression $Command
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ $Description completed successfully" -ForegroundColor Green
            return $true
        } else {
            Write-Host "❌ $Description failed with exit code $LASTEXITCODE" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "❌ $Description failed: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

$success = $true

# Install shared schema package first
$success = $success -and (Invoke-SafeCommand "python scripts/install_shared.py" "Installing shared schema package")

# Install pre-commit hooks
$success = $success -and (Invoke-SafeCommand "$precommitPath install" "Installing pre-commit hooks")

# Install commit-msg hook for conventional commits (optional)
$success = $success -and (Invoke-SafeCommand "$precommitPath install --hook-type commit-msg" "Installing commit-msg hook")

# Run pre-commit on all files to ensure everything is properly formatted
Write-Host "🔧 Running pre-commit on all files (this may take a moment)..." -ForegroundColor Cyan
try {
    & $precommitPath run --all-files
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ All files are properly formatted" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Some files needed formatting. Please review and commit the changes." -ForegroundColor Yellow
        $success = $false
    }
}
catch {
    Write-Host "❌ Pre-commit run failed: $($_.Exception.Message)" -ForegroundColor Red
    $success = $false
}

if ($success) {
    Write-Host ""
    Write-Host "🎉 Development environment setup complete!" -ForegroundColor Green
    Write-Host "📝 Pre-commit hooks will now run automatically before each commit." -ForegroundColor Cyan
    Write-Host "💡 To manually run all hooks: $precommitPath run --all-files" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "⚠️  Setup completed with some issues. Please review the errors above." -ForegroundColor Yellow
    exit 1
}
