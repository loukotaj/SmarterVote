---
mode: agent
description: Run the full CI check suite matching GitHub Actions gates and report any failures.
---

Run the full SmarterVote CI suite. Execute each step and report failures clearly.
These steps mirror `.github/workflows/ci.yaml` exactly.

## Step 1 — Secret scan check (Terraform artifacts)

Verify no tracked Terraform artifacts exist:

```bash
git ls-files | grep -E '(^|/)(tfplan|[^/]+\.tfplan|terraform\.tfstate(\..*)?|secrets\.tfvars)$'
```

If any are listed, they must be removed from tracking.

## Step 2 — Python pipeline tests

```bash
PYTHONPATH=. python -m pytest tests -v \
  --ignore=tests/test_races_api_admin.py
```

## Step 3 — Python formatting check

```bash
python -m black --check shared smartervote_mcp services/races-api tests pipeline_client functions scripts
python -m isort --check-only shared smartervote_mcp services/races-api tests pipeline_client functions scripts
```

## Step 4 — Races API tests

```bash
cd services/races-api && PYTHONPATH=../.. python -m pytest test_races_api.py -v
cd services/races-api && PYTHONPATH=../.. python -m pytest ../../tests/test_races_api_admin.py -v
```

## Step 5 — Frontend (TypeScript check, lint, build, unit tests)

```bash
cd web && npm ci && npm run check && npm run lint && npm run build && npm run test:unit -- --run
```

## Step 6 — Terraform validate

```bash
cd infra && terraform fmt -check -recursive && terraform init -backend=false && terraform validate
```

After running all steps, produce a summary table:

| Step                          | Status  | Failures |
| ----------------------------- | ------- | -------- |
| Secret/Terraform artifact scan | ✅ / ❌ | ...      |
| Python pipeline tests         | ✅ / ❌ | ...      |
| Python formatting             | ✅ / ❌ | ...      |
| Races API tests               | ✅ / ❌ | ...      |
| Frontend (check+lint+build+test) | ✅ / ❌ | ...   |
| Terraform validate            | ✅ / ❌ | ...      |

If any step fails, show the relevant error output and suggest a fix.
