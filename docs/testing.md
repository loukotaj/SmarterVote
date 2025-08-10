# Testing Guide

## Structure

Tests live adjacent to the code they test (Python/services) and `tests/` for integrations.

```
pipeline/app/
├── discover/                 # unit tests adjacent
├── fetch/
├── extract/
├── corpus/
├── summarise/
├── arbitrate/
└── publish/

services/
├── enqueue-api/
└── races-api/

tests/                        # integration tests
```

## Commands

- All tests: `python -m pytest -v`
- Pipeline only: `python -m pytest pipeline/ -v`
- Services only: `python -m pytest services/ -v`
- Integration: `python -m pytest tests/ -v`
- Web: `cd web && npm run test`

## Coverage status
- Done: discover, fetch, extract, corpus, summarise, arbitrate, publish, enqueue-api, races-api, integration
- Missing: web

## Notes
- Prefer fast unit tests with mocks for external I/O
- Mark slow tests with `@pytest.mark.slow`
- Keep Python tests colocated (test_service.py) per module
