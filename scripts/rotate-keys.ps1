# SmarterVote API Key Rotation Script
#
# Rotates AI provider API keys across three targets:
#   1. Local .env file
#   2. GitHub Actions repository secrets (via gh CLI)
#   3. GCP Secret Manager (via gcloud CLI)
#
# Usage:
#   .\scripts\rotate-keys.ps1
#   .\scripts\rotate-keys.ps1 -Environment prod
#   .\scripts\rotate-keys.ps1 -SkipGitHub          # local + GCP only
#   .\scripts\rotate-keys.ps1 -SkipGCP             # local + GitHub only
#   .\scripts\rotate-keys.ps1 -SkipLocal           # GitHub + GCP only
#   .\scripts\rotate-keys.ps1 -DryRun              # show what WOULD change, write nothing
#
# Prerequisites:
#   - gh CLI installed and authenticated (https://cli.github.com/)
#   - gcloud CLI installed and authenticated (https://cloud.google.com/sdk)
#   - GCP_PROJECT_ID set in .env or passed via -ProjectId

param(
    [ValidateSet("dev", "staging", "prod")]
    [string]$Environment = "dev",

    [string]$ProjectId = "",       # falls back to GCP_PROJECT_ID in .env
    [string]$EnvFile   = "",       # defaults to <repo-root>/.env

    [switch]$SkipGitHub,
    [switch]$SkipGCP,
    [switch]$SkipLocal,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Header([string]$text) {
    Write-Host ""
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("  " + ("-" * $text.Length)) -ForegroundColor DarkCyan
}

function Write-Ok([string]$msg)   { Write-Host "  [OK]  $msg" -ForegroundColor Green }
function Write-Skip([string]$msg) { Write-Host "  [--]  $msg" -ForegroundColor DarkGray }
function Write-Warn([string]$msg) { Write-Host "  [!!]  $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host "  [ERR] $msg" -ForegroundColor Red }

function Read-SecureValue([string]$prompt) {
    # Read without echoing the value
    $secure = Read-Host -Prompt $prompt -AsSecureString
    $bstr   = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
    finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Get-EnvValue([string]$file, [string]$key) {
    $line = Get-Content $file -ErrorAction SilentlyContinue |
            Where-Object { $_ -match "^\s*${key}\s*=" } |
            Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -replace "^\s*${key}\s*=\s*", "").Trim()
}

function Set-EnvValue([string]$file, [string]$key, [string]$value) {
    $content = Get-Content $file -Raw
    if ($content -match "(?m)^\s*${key}\s*=") {
        # Use a scriptblock replacement so $value is treated as a literal string
        # (avoids regex back-reference interpretation of $ chars in API key values)
        $content = [regex]::Replace($content, "(?m)^(\s*${key}\s*=).*$", {
            param($m)
            $m.Groups[1].Value + $value
        })
    } else {
        # Append new key at end of file
        $content = $content.TrimEnd() + "`n${key}=${value}`n"
    }
    $content | Set-Content $file -NoNewline -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Locate repo root and .env
# ---------------------------------------------------------------------------
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $repoRoot ".env" }

if (-not (Test-Path $EnvFile)) {
    Write-Fail ".env not found at: $EnvFile"
    Write-Warn "Copy .env.example to .env and fill in your current keys first."
    exit 1
}

# Resolve project ID
if (-not $ProjectId) { $ProjectId = Get-EnvValue $EnvFile "GCP_PROJECT_ID" }
if (-not $ProjectId) { $ProjectId = $env:GCP_PROJECT_ID }

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  SmarterVote API Key Rotation" -ForegroundColor White
Write-Host "  =============================" -ForegroundColor White
Write-Host "  Environment : $Environment"  -ForegroundColor Yellow
Write-Host "  .env file   : $EnvFile"      -ForegroundColor Yellow
if ($DryRun) { Write-Host "  DRY RUN     : no changes will be written" -ForegroundColor Magenta }

if (-not $SkipGitHub) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Fail "gh CLI not found. Install from https://cli.github.com/ or pass -SkipGitHub"
        exit 1
    }
    try { gh auth status 2>&1 | Out-Null }
    catch {
        Write-Fail "gh CLI not authenticated. Run: gh auth login"
        exit 1
    }
}

if (-not $SkipGCP) {
    if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
        Write-Warn "gcloud CLI not found - skipping GCP Secret Manager updates."
        $SkipGCP = $true
    } elseif (-not $ProjectId) {
        Write-Warn "GCP_PROJECT_ID not set - skipping GCP Secret Manager updates."
        Write-Warn "Set GCP_PROJECT_ID in .env or pass -ProjectId <id> to enable."
        $SkipGCP = $true
    }
}

# Detect GitHub repo (owner/name) for gh secret set
$ghRepo = ""
if (-not $SkipGitHub) {
    try {
        $ghRepo = gh repo view --json nameWithOwner -q ".nameWithOwner" 2>&1
        if ($LASTEXITCODE -ne 0) { throw "gh repo view failed" }
    } catch {
        Write-Warn "Could not detect GitHub repo - skipping GitHub secrets update."
        $SkipGitHub = $true
    }
}

# ---------------------------------------------------------------------------
# Key definitions
#
# Each entry:  @{ Var = env var name; Secret = GCP secret base name; Url = rotation page }
# GCP secret name will be "${Secret}-${Environment}"
# GitHub Actions secret name equals Var
# ---------------------------------------------------------------------------
$keys = @(
    @{
        Var    = "OPENAI_API_KEY"
        Secret = "openai-api-key"
        Label  = "OpenAI"
        Url    = "https://platform.openai.com/api-keys"
    },
    @{
        Var    = "SERPER_API_KEY"
        Secret = "serper-api-key"
        Label  = "Serper"
        Url    = "https://serper.dev/api-key"
    },
    @{
        Var    = "ANTHROPIC_API_KEY"
        Secret = "anthropic-api-key"
        Label  = "Anthropic"
        Url    = "https://console.anthropic.com/settings/keys"
    },
    @{
        Var    = "GEMINI_API_KEY"
        Secret = "gemini-api-key"
        Label  = "Google Gemini"
        Url    = "https://aistudio.google.com/apikey"
    },
    @{
        Var    = "XAI_API_KEY"
        Secret = "xai-api-key"
        Label  = "xAI (Grok)"
        Url    = "https://console.x.ai/"
    }
)

# ---------------------------------------------------------------------------
# Per-key interactive loop
# ---------------------------------------------------------------------------
$changes = [System.Collections.Generic.List[hashtable]]::new()

Write-Header "Collecting new key values"
Write-Host "  Press ENTER to keep the existing value for any key." -ForegroundColor DarkGray
Write-Host "  Keys are masked while typing." -ForegroundColor DarkGray

foreach ($k in $keys) {
    $current = Get-EnvValue $EnvFile $k.Var
    $isSet   = ($null -ne $current -and $current -ne "")
    $hint    = if ($isSet) { "(currently set - press Enter to keep)" } else { "(not set - press Enter to skip)" }

    Write-Host ""
    Write-Host "  $($k.Label)" -ForegroundColor White
    Write-Host "  Rotate at: $($k.Url)" -ForegroundColor DarkGray
    $newVal = Read-SecureValue "  New $($k.Var) $hint"

    if ($newVal -eq "") {
        Write-Skip "Keeping existing value for $($k.Var)"
        continue
    }

    $changes.Add(@{
        Var     = $k.Var
        Secret  = "$($k.Secret)-$Environment"
        Label   = $k.Label
        NewVal  = $newVal
    })
    Write-Ok "Queued update for $($k.Var)"
}

if ($changes.Count -eq 0) {
    Write-Host ""
    Write-Host "  No keys to update. Exiting." -ForegroundColor Yellow
    exit 0
}

# ---------------------------------------------------------------------------
# Apply changes
# ---------------------------------------------------------------------------
$n = $changes.Count
Write-Header "Applying changes - $n keys"

$localOk  = $true
$ghOk     = $true
$gcpOk    = $true

foreach ($c in $changes) {
    # --- Local .env ---
    if (-not $SkipLocal) {
        if ($DryRun) {
            Write-Skip "[DRY RUN] Would write $($c.Var) to $EnvFile"
        } else {
            try {
                Set-EnvValue $EnvFile $c.Var $c.NewVal
                Write-Ok "Local .env: updated $($c.Var)"
            } catch {
                Write-Fail "Local .env: failed to update $($c.Var) - $_"
                $localOk = $false
            }
        }
    }

    # --- GitHub Actions secret ---
    if (-not $SkipGitHub) {
        if ($DryRun) {
            Write-Skip "[DRY RUN] Would set GitHub secret $($c.Var) on $ghRepo"
        } else {
            try {
                $c.NewVal | gh secret set $c.Var --repo $ghRepo 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "gh exited $LASTEXITCODE" }
                Write-Ok "GitHub Actions: set $($c.Var) on $ghRepo"
            } catch {
                Write-Fail "GitHub Actions: failed to set $($c.Var) - $_"
                $ghOk = $false
            }
        }
    }

    # --- GCP Secret Manager ---
    if (-not $SkipGCP) {
        if ($DryRun) {
            Write-Skip "[DRY RUN] Would add version to GCP secret: $($c.Secret) in project $ProjectId"
        } else {
            try {
                $tmpFile = [System.IO.Path]::GetTempFileName()
                try {
                    # Write to temp file so the value never appears in process args
                    [System.IO.File]::WriteAllText($tmpFile, $c.NewVal, [System.Text.Encoding]::UTF8)
                    gcloud secrets versions add $c.Secret `
                        --data-file="$tmpFile" `
                        --project="$ProjectId" `
                        --quiet 2>&1 | Out-Null
                    if ($LASTEXITCODE -ne 0) { throw "gcloud exited $LASTEXITCODE" }
                    Write-Ok "GCP Secret Manager: added version to $($c.Secret)"
                } finally {
                    Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
                }
            } catch {
                Write-Fail "GCP Secret Manager: failed to update $($c.Secret) - $_"
                Write-Warn "The secret may not exist yet for this environment. Run terraform apply first."
                $gcpOk = $false
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Header "Summary"

$updated = $changes | ForEach-Object { "    - $($_.Var) [$($_.Label)]" }
Write-Host ($updated -join "`n") -ForegroundColor White

$targets = @()
if (-not $SkipLocal)  { $targets += if ($localOk) { "Local .env [OK]" } else { "Local .env [ERRORS]" } }
if (-not $SkipGitHub) { $targets += if ($ghOk)    { "GitHub Actions [$ghRepo] [OK]" } else { "GitHub Actions [ERRORS]" } }
if (-not $SkipGCP)    { $targets += if ($gcpOk)   { "GCP Secret Manager [$ProjectId / $Environment] [OK]" } else { "GCP Secret Manager [ERRORS]" } }

Write-Host ""
foreach ($t in $targets) {
    if ($t -match "\[ERRORS\]") { Write-Fail $t } else { Write-Ok $t }
}

if (-not $DryRun) {
    Write-Host ""
    Write-Host "  REMINDER: The new keys are live immediately in:" -ForegroundColor Yellow
    if (-not $SkipLocal)  { Write-Host "    - Local .env (restart any running services)" -ForegroundColor DarkGray }
    if (-not $SkipGitHub) { Write-Host "    - GitHub Actions (next workflow run picks them up)" -ForegroundColor DarkGray }
    if (-not $SkipGCP) {
        Write-Host "    - GCP Secret Manager (Cloud Run picks up on next deploy/restart)" -ForegroundColor DarkGray
        Write-Host "      To force immediate pickup, run: gcloud run services update <name> --region us-central1 --project $ProjectId" -ForegroundColor DarkGray
    }
}

Write-Host ""
