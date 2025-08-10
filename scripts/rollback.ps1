# SmarterVote Emergency Rollback Script
# PowerShell script for emergency infrastructure rollback

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("dev", "staging", "prod")]
    [string]$Environment,

    [Parameter(Mandatory=$false)]
    [string]$ToCommit = ""
)

Write-Host "SmarterVote Emergency Rollback" -ForegroundColor Red
Write-Host "=================================" -ForegroundColor Red
Write-Host "Environment: $Environment" -ForegroundColor Yellow
Write-Host ""

# Safety check for production
if ($Environment -eq "prod") {
    Write-Host "PRODUCTION ROLLBACK REQUESTED!" -ForegroundColor Red
    Write-Host "This is a critical operation that affects live services." -ForegroundColor Yellow
    Write-Host ""
    $prodConfirm = Read-Host "Type 'ROLLBACK-PROD' to confirm"
    if ($prodConfirm -ne "ROLLBACK-PROD") {
        Write-Host "Production rollback cancelled" -ForegroundColor Red
        exit 0
    }
}

# Check if GitHub CLI is installed
if (!(Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "Error: GitHub CLI (gh) is required" -ForegroundColor Red
    exit 1
}

# Show recent commits for reference
Write-Host "Recent infrastructure commits:" -ForegroundColor Cyan
git log --oneline -n 10 --format="%h %s (%ar)" -- infra/
Write-Host ""

# Determine target commit
if ($ToCommit -eq "") {
    Write-Host "Select rollback target:" -ForegroundColor Yellow
    Write-Host "1. Previous commit (recommended)" -ForegroundColor Gray
    Write-Host "2. Specific commit hash" -ForegroundColor Gray
    Write-Host "3. Use GitHub Actions rollback" -ForegroundColor Gray
    Write-Host ""
    $choice = Read-Host "Enter choice (1-3)"

    switch ($choice) {
        "1" {
            $ToCommit = git log --oneline -n 2 --format="%H" -- infra/ | Select-Object -Last 1
            Write-Host "Selected previous commit: $ToCommit" -ForegroundColor Green
        }
        "2" {
            $ToCommit = Read-Host "Enter commit hash"
            # Validate commit exists
            $null = git cat-file -e "$ToCommit^{commit}" 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Invalid commit hash: $ToCommit" -ForegroundColor Red
                exit 1
            }
        }
        "3" {
            Write-Host "Triggering GitHub Actions rollback..." -ForegroundColor Cyan
            gh workflow run terraform-deploy.yaml `
                --field environment=$Environment `
                --field action=rollback

            Write-Host "GitHub Actions rollback triggered!" -ForegroundColor Green
            Write-Host "Monitor at: https://github.com/loukotaj/SmarterVote/actions" -ForegroundColor Blue
            exit 0
        }
        default {
            Write-Host "Invalid choice" -ForegroundColor Red
            exit 1
        }
    }
}

# Show what will be rolled back
Write-Host ""
Write-Host "Changes to be rolled back:" -ForegroundColor Yellow
git diff --name-only HEAD $ToCommit -- infra/
Write-Host ""

# Final confirmation
Write-Host "This will rollback $Environment infrastructure to commit $ToCommit" -ForegroundColor Red
$final = Read-Host "Continue? (y/N)"
if ($final -ne "y" -and $final -ne "Y") {
    Write-Host "Rollback cancelled" -ForegroundColor Red
    exit 0
}

# Create rollback branch and trigger deployment
$rollbackBranch = "rollback-$Environment-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

Write-Host ""
Write-Host "Creating rollback branch: $rollbackBranch" -ForegroundColor Cyan

try {
    # Create and switch to rollback branch
    git checkout -b $rollbackBranch

    # Reset infra to target commit
    git checkout $ToCommit -- infra/

    # Commit the rollback
    git add infra/
    git commit -m "Emergency rollback to $ToCommit for $Environment"

    # Push rollback branch
    git push origin $rollbackBranch

    # Trigger deployment from rollback branch
    Write-Host "Triggering deployment from rollback branch..." -ForegroundColor Cyan
    gh workflow run terraform-deploy.yaml `
        --ref $rollbackBranch `
        --field environment=$Environment `
        --field action=apply

    Write-Host ""
    Write-Host "Emergency rollback initiated!" -ForegroundColor Green
    Write-Host "Monitor progress: https://github.com/loukotaj/SmarterVote/actions" -ForegroundColor Blue
    Write-Host ""
    Write-Host "Rollback branch created: $rollbackBranch" -ForegroundColor Yellow
    Write-Host "After successful rollback, merge this branch to main" -ForegroundColor Gray

} catch {
    Write-Host "Rollback failed: $_" -ForegroundColor Red

    # Cleanup on failure
    git checkout main
    git branch -D $rollbackBranch 2>$null

    exit 1
}
