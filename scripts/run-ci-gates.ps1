param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Name (exit code $LASTEXITCODE)"
    }
    Write-Host "PASS: $Name" -ForegroundColor Green
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

try {
    $python = "python"
    # Respect an activated virtual environment. The Windows `py` launcher bypasses
    # it and can leak incompatible optional packages into otherwise clean CI checks.
    if (-not $env:VIRTUAL_ENV -and (Get-Command py -ErrorAction SilentlyContinue)) {
        $python = "py -3.10"
    }

    Write-Host "Running local CI gate checks from: $repoRoot" -ForegroundColor Yellow
    Write-Host "SkipInstall: $SkipInstall" -ForegroundColor Yellow

    Invoke-Step "Reject tracked Terraform artifacts" {
        $trackedArtifacts = git ls-files | Select-String -Pattern '(^|/)(tfplan|[^/]+\.tfplan|terraform\.tfstate(\..*)?|secrets\.tfvars)$'
        if ($trackedArtifacts) {
            $trackedArtifacts | ForEach-Object { Write-Host $_.Line -ForegroundColor Red }
            throw "Generated or sensitive Terraform files are tracked"
        }
    }

    Invoke-Step "Secret scan" {
        docker run --rm -v "${repoRoot}:/repo" "ghcr.io/gitleaks/gitleaks:v8.29.0@sha256:71d3ee5990f2176f763b438298453fc37e87b119122045e176ca9d44ff00b08b" dir --redact --no-banner /repo
    }

    if (-not $SkipInstall) {
        Invoke-Step "Install pipeline test dependencies" {
            Invoke-Expression "$python -m pip install --upgrade pip"
            Invoke-Expression "$python -m pip install -c requirements-constraints.txt -r pipeline_client/backend/requirements.txt"
            Invoke-Expression "$python -m pip install -c requirements-constraints.txt -r services/races-api/requirements.txt"
            Invoke-Expression "$python -m pip install -c requirements-constraints.txt pytest pytest-asyncio pytest-cov httpx"
            Invoke-Expression "$python -m pip install pip-audit==2.10.0"
            Invoke-Expression "$python -m pip install black==23.11.0 isort==5.12.0"
        }

        Invoke-Step "Install races-api test dependencies" {
            Push-Location "services/races-api"
            try {
                Invoke-Expression "$python -m pip install --upgrade pip"
                Invoke-Expression "$python -m pip install -c ../../requirements-constraints.txt -r requirements.txt"
                Invoke-Expression "$python -m pip install -c ../../requirements-constraints.txt -r test-requirements.txt"
            }
            finally {
                Pop-Location
            }
        }

        Invoke-Step "Install web dependencies" {
            Push-Location "web"
            try {
                npm ci
            }
            finally {
                Pop-Location
            }
        }
    }

    Invoke-Step "Dependency audit" {
        # PYSEC-2026-1325 affects ECDSA signing. SmarterVote only verifies Auth0 RS256 tokens.
        Invoke-Expression "$python -m pip_audit --ignore-vuln PYSEC-2026-1325 -r pipeline_client/backend/requirements.txt"
        Invoke-Expression "$python -m pip_audit --ignore-vuln PYSEC-2026-1325 -r services/races-api/requirements.txt"
        Invoke-Expression "$python -m pip_audit -r functions/admin_agent/requirements.txt"
        Push-Location "web"
        try {
            npm audit --omit=dev --audit-level=high
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Pipeline tests" {
        $env:PYTHONPATH = "."
        Invoke-Expression "$python -m pytest tests -v --ignore=tests/test_races_api_admin.py --cov=pipeline_client --cov=shared --cov=functions --cov=smartervote_mcp --cov-report=term-missing --cov-fail-under=55"
    }

    Invoke-Step "Python formatting" {
        Invoke-Expression "$python -m black --check shared smartervote_mcp services/races-api tests pipeline_client functions scripts"
        Invoke-Expression "$python -m isort --check-only shared smartervote_mcp services/races-api tests pipeline_client functions scripts"
    }

    Invoke-Step "Races API tests" {
        Push-Location "services/races-api"
        try {
            $env:PYTHONPATH = "../.."
            Invoke-Expression "$python -m pytest . -v"
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Races API admin tests" {
        Push-Location "services/races-api"
        try {
            $env:PYTHONPATH = "../.."
            Invoke-Expression "$python -m pytest ../../tests/test_races_api_admin.py -v"
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Web type check" {
        Push-Location "web"
        try {
            npm run check
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Web lint" {
        Push-Location "web"
        try {
            npm run lint
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Web build" {
        Push-Location "web"
        try {
            if (-not (Test-Path "static/summaries.json")) {
                New-Item -ItemType Directory -Force "static" | Out-Null
                Set-Content -Encoding UTF8 "static/summaries.json" "[]"
            }
            if (-not (Test-Path "static/chamber_forecasts.json")) {
                Set-Content -Encoding UTF8 "static/chamber_forecasts.json" '{"schema_version":"chamber_forecasts.v2","house":"","senate":"","governors":"","chambers":{"house":{"projected_seats":{"Democratic":0,"Republican":0},"tossup_count":0,"competitive_race_count":0},"senate":{"projected_seats":{"Democratic":0,"Republican":0},"tossup_count":0,"competitive_race_count":0},"governors":{"projected_seats":{"Democratic":0,"Republican":0},"tossup_count":0,"competitive_race_count":0}}}'
            }
            $env:FAST_BUILD = "true"
            npm run build
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Web unit tests" {
        Push-Location "web"
        try {
            npm run test:unit -- --run
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Web browser smoke tests" {
        Push-Location "web"
        try {
            npm run test:e2e
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Build release containers" {
        docker build --pull -f services/races-api/Dockerfile -t smartervote/races-api:local-ci .
        docker build --pull -f pipeline_client/Dockerfile.worker -t smartervote/pipeline-worker:local-ci .
    }

    Invoke-Step "Scan release containers" {
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock "aquasec/trivy:0.69.3@sha256:bcc376de8d77cfe086a917230e818dc9f8528e3c852f7b1aff648949b6258d1c" image --scanners vuln --skip-version-check --exit-code 1 --ignore-unfixed --severity CRITICAL smartervote/races-api:local-ci
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock "aquasec/trivy:0.69.3@sha256:bcc376de8d77cfe086a917230e818dc9f8528e3c852f7b1aff648949b6258d1c" image --scanners vuln --skip-version-check --exit-code 1 --ignore-unfixed --severity CRITICAL smartervote/pipeline-worker:local-ci
    }

    Invoke-Step "Terraform format check" {
        Push-Location "infra"
        try {
            terraform fmt -check -recursive
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Terraform validate" {
        Push-Location "infra"
        try {
            terraform init -backend=false
            terraform validate
        }
        finally {
            Pop-Location
        }
    }

    Write-Host ""
    Write-Host "All CI gate checks passed." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ""
    Write-Host "CI gate checks failed." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
