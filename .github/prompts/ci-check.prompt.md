---
mode: agent
description: Run the full CI check suite (Python tests, frontend check+build+test, Terraform validate) and report any failures.
---

Run the full SmarterVote CI suite. Execute each step and report failures clearly.

## Step 1 — Python pipeline tests

```bash
PYTHONPATH=. python -m pytest tests/test_pipeline.py -v
```

## Step 2 — Races-API tests

```bash
cd services/races-api && PYTHONPATH=../.. python -m pytest test_races_api.py -v
```

## Step 3 — Frontend (TypeScript check, build, unit tests)

```bash
cd web && npm ci && npm run check && npm run build && npm run test:unit -- --run
```

## Step 4 — Terraform validate

```bash
cd infra && terraform fmt -check -recursive && terraform validate
```

After running all steps, produce a summary table:

| Step | Status | Failures |
|------|--------|----------|
| Python pipeline tests | ✅ / ❌ | ... |
| Races-API tests | ✅ / ❌ | ... |
| Frontend (check+build+test) | ✅ / ❌ | ... |
| Terraform validate | ✅ / ❌ | ... |

If any step fails, show the relevant error output and suggest a fix.
