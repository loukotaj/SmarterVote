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
    if (Get-Command py -ErrorAction SilentlyContinue) {
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

    if (-not $SkipInstall) {
        Invoke-Step "Install pipeline test dependencies" {
            Invoke-Expression "$python -m pip install --upgrade pip"
            Invoke-Expression "$python -m pip install -r pipeline_client/backend/requirements.txt"
            Invoke-Expression "$python -m pip install pytest pytest-asyncio httpx"
            Invoke-Expression "$python -m pip install black==23.11.0 isort==5.12.0"
        }

        Invoke-Step "Install races-api test dependencies" {
            Push-Location "services/races-api"
            try {
                Invoke-Expression "$python -m pip install --upgrade pip"
                Invoke-Expression "$python -m pip install -r requirements.txt"
                Invoke-Expression "$python -m pip install -r test-requirements.txt"
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

    Invoke-Step "Pipeline tests" {
        $env:PYTHONPATH = "."
        Invoke-Expression "$python -m pytest tests -v --ignore=tests/test_races_api_admin.py"
    }

    Invoke-Step "Python formatting" {
        Invoke-Expression "$python -m black --check shared smartervote_mcp services/races-api tests pipeline_client functions scripts"
        Invoke-Expression "$python -m isort --check-only shared smartervote_mcp services/races-api tests pipeline_client functions scripts"
    }

    Invoke-Step "Races API tests" {
        Push-Location "services/races-api"
        try {
            $env:PYTHONPATH = "../.."
            Invoke-Expression "$python -m pytest test_races_api.py -v"
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
