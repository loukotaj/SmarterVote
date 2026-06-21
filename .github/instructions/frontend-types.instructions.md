---
applyTo: "web/src/lib/types.ts"
---

# Frontend Type Sync Rules

`web/src/lib/types.ts` is the TypeScript mirror of `shared/models.py`. These two files must stay in sync — type mismatches will silently break at runtime.

## Sync Checklist

When modifying this file, also update `shared/models.py` (and vice versa):

- **Enums**: Every `export const enum` or `export type` union here maps to a `class MyEnum(str, Enum)` in Python
- **Interfaces**: Every `interface` maps to a Pydantic `BaseModel`
- **Optional fields**: `field?: Type` ↔ `field: Optional[Type] = None`
- **Canonical issues**: `CanonicalIssue` enum values must exactly match `shared/models.py` (12 issues, exact strings)

## Canonical Issues (current)

```
Healthcare | Economy | Climate/Energy | Abortion & Reproductive Health | Immigration
Firearms & Second Amendment | Foreign Policy | Civil Rights & Equality | Education
Tech & AI | Election Policy | Local Issues
```

Do not add, rename, or remove canonical issue values without updating both files and `pipeline_client/agent/prompts.py`.

## Validation

After changes, run:

```bash
cd web && npm run check   # TypeScript type errors
PYTHONPATH=. python -m pytest tests/test_pipeline.py -v   # Python model validation
```
