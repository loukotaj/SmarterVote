# Testing Guide

## Test Structure

Tests are now organized adjacent to the code they test, making them easier to find and maintain.

### Directory Structure
```
pipeline/app/
├── discover/
│   ├── source_discovery_engine.py
│   └── test_service.py          # ✅ Unit tests
├── fetch/
│   ├── web_content_fetcher.py
│   └── test_service.py          # ✅ Unit tests
├── extract/
│   ├── content_extractor.py
│   └── test_service.py          # ✅ Unit tests
├── corpus/
│   ├── vector_database_manager.py
│   └── test_service.py          # ❌ Missing - needs implementation
├── summarise/
│   ├── llm_summarization_engine.py
│   └── test_service.py          # ❌ Missing - needs implementation
├── arbitrate/
│   ├── consensus_arbitration_engine.py
│   └── test_service.py          # ❌ Missing - needs implementation
└── publish/
    ├── race_publishing_engine.py
    └── test_service.py          # ❌ Missing - needs implementation

services/
├── enqueue-api/
│   ├── main.py
│   └── test_enqueue_api.py      # ✅ API tests
└── races-api/
    ├── main.py
    └── test_races_api.py        # ✅ API tests

tests/
├── conftest.py                  # ✅ Shared test configuration
└── test_integration.py          # ✅ Integration tests
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

## Test Coverage Status

### Current Test Coverage
- ✅ **Discovery Service**: Unit tests implemented
- ✅ **Fetch Service**: Unit tests implemented
- ✅ **Extract Service**: Unit tests implemented
- ✅ **Enqueue API**: API tests implemented
- ✅ **Races API**: API tests implemented
- ✅ **Integration Tests**: Core workflow tests implemented

### Missing Test Coverage (High Priority)
- ❌ **Corpus Service**: Vector database operations testing needed
- ❌ **Summarize Service**: LLM integration testing needed
- ❌ **Arbitration Service**: Consensus logic testing needed
- ❌ **Publish Service**: Output validation testing needed
- ❌ **Web Frontend**: Component and page testing needed

## Test Types

- **Unit Tests**: Adjacent to source code, test individual components
- **Integration Tests**: In `tests/` directory, test component interactions
- **API Tests**: Test REST endpoints and request/response handling
- **Frontend Tests**: Test UI components and user interactions (to be implemented)
