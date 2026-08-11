---
mode: agent
description: Run the full CI check suite matching GitHub Actions gates and report any failures.
---

Run the full SmarterVote CI suite. Execute each step and report failures clearly.
Use `./scripts/run-ci-gates.ps1` on Windows. It mirrors every locally reproducible
gate in `.github/workflows/ci.yaml`; CodeQL remains CI-only.

## Step 1 — Secret scan check (Terraform artifacts)

Verify no tracked Terraform artifacts exist:

```bash
git ls-files | grep -E '(^|/)(tfplan|[^/]+\.tfplan|terraform\.tfstate(\..*)?|secrets\.tfvars)$'
```

If any are listed, they must be removed from tracking.

## Step 2 — Python pipeline tests

```bash
PYTHONPATH=. python -m pytest tests -v \
  --ignore=tests/test_races_api_admin.py \
  --cov=pipeline_client --cov=shared --cov=smartervote_mcp \
  --cov-report=term-missing --cov-report=json:coverage.json --cov-fail-under=70
PYTHONPATH=. python scripts/check_coverage_thresholds.py coverage.json
```

## Step 3 — Python formatting check

```bash
python -m black --check shared smartervote_mcp services/races-api tests pipeline_client functions scripts
python -m isort --check-only shared smartervote_mcp services/races-api tests pipeline_client functions scripts
```

## Step 4 — Races API tests

```bash
(cd services/races-api && PYTHONPATH=../.. python -m pytest . ../../tests/test_races_api_admin.py -v \
  --cov=. --cov-report=term-missing --cov-fail-under=65)

# Incrementally typed Python modules
PYTHONPATH=. python -m mypy shared/pipeline_options.py shared/race_titles.py shared/kalshi_markets.py
```

## Step 5 — Frontend (TypeScript check, lint, build, browser and unit tests)

```bash
(cd web && npm ci && npm run check && npm run lint && npm run build && npm run test:e2e && npm run test:coverage -- --run)
(cd design-system && npm ci && npm run typecheck && npm run build)
```

## Step 6 — Terraform validate

```bash
cd infra && terraform fmt -check -recursive && terraform init -backend=false && terraform validate
```

## Step 7 — Dependency and release-artifact checks

Run the Python and npm production dependency audits, build both release
containers from the repository root, and scan them for critical vulnerabilities.
The PowerShell helper contains the canonical commands and pinned scanner images.

After running all steps, produce a summary table:

| Step                          | Status  | Failures |
| ----------------------------- | ------- | -------- |
| Secret/Terraform artifact scan | ✅ / ❌ | ...      |
| Python pipeline tests         | ✅ / ❌ | ...      |
| Python formatting             | ✅ / ❌ | ...      |
| Races API tests               | ✅ / ❌ | ...      |
| Frontend (check+lint+build+test) | ✅ / ❌ | ...   |
| Terraform validate            | ✅ / ❌ | ...      |
| Dependency audits             | ✅ / ❌ | ...      |
| Container build and scan      | ✅ / ❌ | ...      |

If any step fails, show the relevant error output and suggest a fix.
