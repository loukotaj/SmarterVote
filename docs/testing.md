# Testing Guide

## Test Structure

Tests are now organized adjacent to the code they test, making them easier to find and maintain.

### Directory Structure
```
pipeline/app/
├── discover/
│   ├── source_discovery_engine.py
│   └── test_service.py          # ← Unit tests here
├── fetch/
│   ├── web_content_fetcher.py
│   └── test_service.py          # ← Unit tests here
└── extract/
    ├── content_extractor.py
    └── test_service.py          # ← Unit tests here

services/
├── enqueue-api/
│   ├── main.py
│   └── test_main.py             # ← API tests here
└── races-api/
    ├── main.py
    └── test_main.py             # ← API tests here

web/src/routes/test/
└── race.test.js                 # ← Frontend tests here

tests/
├── conftest.py                  # ← Shared test configuration
└── test_integration.py          # ← Integration tests
```

## Running Tests

### All Tests
```bash
python -m pytest
```

### By Component
```bash
python -m pytest pipeline/          # All pipeline unit tests
python -m pytest services/          # All service tests
python -m pytest tests/             # Integration tests only
npm test                            # Frontend tests
```

### By Module
```bash
python -m pytest pipeline/app/discover/    # Discover service tests
python -m pytest services/enqueue-api/     # Enqueue API tests
```

## Test Types

- **Unit Tests**: Adjacent to source code, test individual components
- **Integration Tests**: In `tests/` directory, test component interactions
- **Frontend Tests**: In web directory, test UI components and pages

## Benefits

- **Proximity**: Tests are right next to the code they test
- **Discoverability**: Easy to find relevant tests when modifying code
- **Maintainability**: When you change code, tests are immediately visible
- **Consistency**: Same pattern across all components

tests/
├── conftest.py                      # ← Test configuration
└── pipeline/
    └── test_pipeline.py             # ← Integration tests
```

## Running Tests

```bash
# All tests
python -m pytest

# Specific component tests
python -m pytest pipeline/app/discover/    # Discovery service tests
python -m pytest services/enqueue-api/     # Enqueue API tests
python -m pytest tests/                    # Integration tests only

# Web tests
npm test                                    # From web/ directory
```

## Benefits

- **Simple imports**: No complex path manipulation needed
- **Clear relationships**: Tests are obviously related to what they test
- **Easy maintenance**: When you modify code, tests are right there
- **Better discovery**: Developers can find tests immediately
