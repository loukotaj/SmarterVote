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
    $pythonExe = "python"
    $pythonPrefixArgs = @()
    # Respect an activated virtual environment even when its Scripts directory
    # was not prepended to PATH (a common Windows shell configuration).
    if ($env:VIRTUAL_ENV) {
        $venvPython = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
        if (Test-Path -LiteralPath $venvPython) {
            $pythonExe = $venvPython
        }
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExe = "py"
        $pythonPrefixArgs = @("-3.11")
    }

    function Invoke-Python {
        & $pythonExe @pythonPrefixArgs @args
        if ($LASTEXITCODE -ne 0) {
            throw "Python command failed with exit code $LASTEXITCODE"
        }
    }

    $pythonVersion = Invoke-Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($pythonVersion -ne "3.11") {
        throw "Local CI requires Python 3.11; selected interpreter reports $pythonVersion. Recreate .venv with 'py -3.11 -m venv .venv'."
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
        # Match a clean CI checkout even when the local worktree contains
        # ignored .env files, dependency trees, Terraform providers, caches,
        # or audit exports. Include tracked files plus non-ignored untracked
        # files so new source is scanned before it is staged.
        $scanRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("smartervote-gitleaks-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $scanRoot | Out-Null
        try {
            $scanFiles = git ls-files --cached --others --exclude-standard
            foreach ($relativePath in $scanFiles) {
                $sourcePath = Join-Path $repoRoot $relativePath
                if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
                    continue
                }
                $destinationPath = Join-Path $scanRoot $relativePath
                $destinationDirectory = Split-Path -Parent $destinationPath
                if (-not (Test-Path -LiteralPath $destinationDirectory)) {
                    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
                }
                Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
            }
            docker run --rm -v "${scanRoot}:/repo:ro" "ghcr.io/gitleaks/gitleaks:v8.29.0@sha256:71d3ee5990f2176f763b438298453fc37e87b119122045e176ca9d44ff00b08b" dir --redact --no-banner /repo
            $secretScanExitCode = $LASTEXITCODE
            if ($secretScanExitCode -ne 0) {
                throw "Gitleaks failed with exit code $secretScanExitCode"
            }
        }
        finally {
            $resolvedScanRoot = [System.IO.Path]::GetFullPath($scanRoot)
            $resolvedTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
            if (-not $resolvedScanRoot.StartsWith($resolvedTempRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
                -not (Split-Path -Leaf $resolvedScanRoot).StartsWith("smartervote-gitleaks-")) {
                throw "Refusing to remove unexpected secret-scan path: $resolvedScanRoot"
            }
            Remove-Item -LiteralPath $resolvedScanRoot -Recurse -Force
        }
        # Native-command exit state survives PowerShell cmdlets in the finally
        # block. Make the successful outcome explicit for Invoke-Step.
        $global:LASTEXITCODE = 0
    }

    if (-not $SkipInstall) {
        Invoke-Step "Install pipeline test dependencies" {
            Invoke-Python -m pip install --upgrade pip
            Invoke-Python -m pip install -c requirements-constraints.txt -r pipeline_client/backend/requirements.txt
            Invoke-Python -m pip install -c requirements-constraints.txt -r services/races-api/requirements.txt
            Invoke-Python -m pip install -c requirements-constraints.txt -r requirements-mcp.txt
            Invoke-Python -m pip install -c requirements-constraints.txt pytest pytest-asyncio pytest-cov httpx
            Invoke-Python -m pip install pip-audit==2.10.0
            Invoke-Python -m pip install black==23.11.0 isort==5.12.0 mypy==1.15.0
        }

        Invoke-Step "Install races-api test dependencies" {
            Push-Location "services/races-api"
            try {
                Invoke-Python -m pip install --upgrade pip
                Invoke-Python -m pip install -c ../../requirements-constraints.txt -r requirements.txt
                Invoke-Python -m pip install -c ../../requirements-constraints.txt -r test-requirements.txt
            }
            finally {
                Pop-Location
            }
        }

        Invoke-Step "Install web dependencies" {
            Push-Location "web"
            try {
                npm ci
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "npm ci encountered an error (e.g. locked node_modules files). Falling back to npm install..." -ForegroundColor Yellow
                    npm install
                }
            }
            finally {
                Pop-Location
            }
        }

        Invoke-Step "Install design-system dependencies" {
            Push-Location "design-system"
            try {
                npm ci
            }
            finally {
                Pop-Location
            }
        }
    }

    Invoke-Step "Dependency audit" {
        Invoke-Python -m pip_audit -r pipeline_client/backend/requirements.txt
        Invoke-Python -m pip_audit -r services/races-api/requirements.txt
        Push-Location "web"
        try {
            npm audit --omit=dev --audit-level=high
            if ($LASTEXITCODE -ne 0) {
                throw "Web dependency audit failed"
            }
        }
        finally {
            Pop-Location
        }
        Push-Location "design-system"
        try {
            npm audit --audit-level=high
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Pipeline tests" {
        $env:PYTHONPATH = "."
        # Keep --cov-fail-under equal to the value in .github/workflows/ci.yaml.
        # The floor is ratcheted upward over time, and a lower one here makes this
        # script pass a branch that CI then rejects — which is the one thing a
        # local mirror of CI must never do.
        Invoke-Python -m pytest tests -v --ignore=tests/test_races_api_admin.py --cov=pipeline_client --cov=shared --cov=smartervote_mcp --cov-report=term-missing --cov-report=json:coverage.json --cov-fail-under=70
        Invoke-Python scripts/check_coverage_thresholds.py coverage.json
    }

    Invoke-Step "Frontend/backend type sync" {
        $env:PYTHONPATH = "."
        Invoke-Python scripts/check_type_sync.py
    }

    Invoke-Step "Python formatting" {
        Invoke-Python -m black --check shared smartervote_mcp services/races-api tests pipeline_client scripts
        Invoke-Python -m isort --check-only shared smartervote_mcp services/races-api tests pipeline_client scripts
    }

    Invoke-Step "Generated type and model catalog sync" {
        $env:PYTHONPATH = "."
        Invoke-Python scripts/check_type_sync.py
        Invoke-Python scripts/generate_model_catalog_ts.py --check
        Invoke-Python -m mypy shared/pipeline_options.py shared/race_titles.py shared/kalshi_markets.py
    }

    Invoke-Step "Races API tests and coverage" {
        Push-Location "services/races-api"
        try {
            $env:PYTHONPATH = "../.."
            Invoke-Python -m pytest . ../../tests/test_races_api_admin.py -v --cov=. --cov-report=term-missing --cov-fail-under=65
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

    Invoke-Step "Web unit tests and coverage" {
        Push-Location "web"
        try {
            npm run test:coverage -- --run
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

    Invoke-Step "Design-system type check and build" {
        Push-Location "design-system"
        try {
            npm run typecheck
            if ($LASTEXITCODE -ne 0) {
                throw "Design-system type check failed"
            }
            npm run build
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
    $failureDetails = $_.Exception.Message
    if ([string]::IsNullOrWhiteSpace($failureDetails)) {
        $failureDetails = ($_ | Out-String).Trim()
    }
    Write-Host $failureDetails -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
