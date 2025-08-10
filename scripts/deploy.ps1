# SmarterVote Deployment Script for GitHub Actions
# PowerShell script to trigger deployments via GitHub Actions

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("dev", "staging", "prod")]
    [string]$Environment,

    [Parameter(Mandatory=$false)]
    [ValidateSet("plan", "apply", "rollback")]
    [string]$Action = "plan"
)

Write-Host "SmarterVote Deployment via GitHub Actions" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host "Environment: $Environment" -ForegroundColor Yellow
Write-Host "Action: $Action" -ForegroundColor Yellow
Write-Host ""

# Check if GitHub CLI is installed
if (!(Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "Error: GitHub CLI (gh) is required but not installed" -ForegroundColor Red
    Write-Host "Please install from: https://cli.github.com/" -ForegroundColor Yellow
    exit 1
}

# Check if authenticated with GitHub
try {
    gh auth status 2>&1 | Out-Null
} catch {
    Write-Host "Error: Not authenticated with GitHub CLI" -ForegroundColor Red
    Write-Host "Please run: gh auth login" -ForegroundColor Yellow
    exit 1
}

# Get current git status
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Host "Warning: You have uncommitted changes:" -ForegroundColor Yellow
    git status --short
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne "y" -and $continue -ne "Y") {
        Write-Host "Deployment cancelled" -ForegroundColor Red
        exit 0
    }
}

# Show current version
$currentCommit = git rev-parse --short HEAD
Write-Host "Current version: $currentCommit" -ForegroundColor Cyan

# Confirm deployment
if ($Action -eq "apply") {
    Write-Host ""
    Write-Host "This will deploy infrastructure to $Environment environment!" -ForegroundColor Yellow
    $confirm = Read-Host "Are you sure? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "Deployment cancelled" -ForegroundColor Red
        exit 0
    }
} elseif ($Action -eq "rollback") {
    Write-Host ""
    Write-Host "This will rollback infrastructure in $Environment environment!" -ForegroundColor Red
    $confirm = Read-Host "Are you sure? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "Rollback cancelled" -ForegroundColor Red
        exit 0
    }
}

# Trigger GitHub Actions workflow
Write-Host ""
Write-Host "Triggering GitHub Actions workflow..." -ForegroundColor Cyan

try {
    gh workflow run terraform-deploy.yaml `
        --field environment=$Environment `
        --field action=$Action

    Write-Host "Deployment triggered successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Monitor progress at:" -ForegroundColor Cyan
    Write-Host "   https://github.com/loukotaj/SmarterVote/actions" -ForegroundColor Blue
    Write-Host ""
    Write-Host "To view logs in real-time, run:" -ForegroundColor Yellow
    Write-Host "   gh run watch" -ForegroundColor Gray

} catch {
    Write-Host "Failed to trigger deployment: $_" -ForegroundColor Red
    exit 1
}
