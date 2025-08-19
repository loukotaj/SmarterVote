# SmarterVote Testing Guide

## Overview

SmarterVote employs a comprehensive, multi-layered testing strategy designed around the corpus-first AI pipeline architecture. Tests are organized to ensure reliability while minimizing external dependencies during development.

## Testing Architecture

### Test Categories & Markers

The project uses pytest markers to categorize tests by their requirements and execution characteristics:

| Marker | Purpose | Example Use |
|--------|---------|-------------|
| `@pytest.mark.unit` | Fast, isolated unit tests | Testing data models, utility functions |
| `@pytest.mark.integration` | Cross-component integration | Testing service communication |
| `@pytest.mark.llm_api` | Tests requiring LLM APIs | AI summarization, consensus |
| `@pytest.mark.external_api` | Tests requiring external APIs | Google Search, web scraping |
| `@pytest.mark.network` | Tests requiring network calls | HTTP requests, webhooks |
| `@pytest.mark.cloud` | Tests requiring cloud services | Pub/Sub, Cloud Storage |
| `@pytest.mark.slow` | Long-running tests | End-to-end pipeline runs |
| `@pytest.mark.e2e` | Complete system tests | Full race processing |

### Test Structure

Tests follow a **colocated pattern** for maximum maintainability:

```
pipeline/app/step01_ingest/
├── ContentFetcher/
│   ├── web_content_fetcher.py   # Implementation
│   └── test_content_fetcher.py  # Unit tests
└── constants.py

pipeline/app/step02_corpus/
├── vector_database_manager.py  # Implementation
└── test_service.py             # Unit tests

pipeline/app/step03_summarise/
├── llm_summarization_engine.py # Implementation
├── consensus_arbitration_engine.py
└── test_service.py

pipeline/app/step04_publish/
├── race_publishing_engine.py   # Implementation
└── test_service.py             # Unit tests

services/enqueue-api/
├── main.py                     # FastAPI application
├── test_enqueue_api.py         # Service tests
└── conftest.py                 # Test configuration

tests/                          # Integration tests
├── conftest.py
├── test_run_steps.py
├── test_step_registry_storage.py
├── test_step_orchestrator.py
├── test_step01_metadata_integration.py
└── test_storage_integration.py
```

## Test Execution

### PowerShell Commands (Recommended)

```powershell
# Fast unit tests only (skip external dependencies)
python -m pytest -m "not external_api and not llm_api and not cloud" -v

# All tests (may require API keys)
python -m pytest -v

# Specific test categories
python -m pytest pipeline/ -v                    # Pipeline tests only
python -m pytest services/ -v                    # Service tests only
python -m pytest tests/ -v                       # Integration tests only

# With coverage reporting
python -m pytest --cov=pipeline --cov=services --cov-report=html -v

# Skip expensive tests in CI/local development
$env:SKIP_LLM_APIS="true"
$env:SKIP_EXTERNAL_APIS="true"
python -m pytest -v
```

### VS Code Tasks

The project includes predefined VS Code tasks for common testing workflows:

- **Run All Tests**: `Ctrl+Shift+P` → "Tasks: Run Task" → "Run All Tests"
- **Run Pipeline Tests**: Focused on pipeline components
- **Run Service Tests**: FastAPI service endpoints
- **Run Integration Tests**: Cross-component integration
- **Run Tests with Coverage**: Generates HTML coverage reports

### Web Frontend Testing

```powershell
cd web
npm run test        # Vitest unit tests
npm run test:e2e    # Playwright integration tests (future)
npm run check       # Svelte type checking
```

## Test Configuration

### Environment-Based Skipping

Tests automatically skip based on environment variables:

```powershell
# Skip expensive/external tests during development
$env:SKIP_LLM_APIS="true"          # Skip OpenAI, Anthropic, XAI tests
$env:SKIP_EXTERNAL_APIS="true"     # Skip Google Search, external APIs
$env:SKIP_NETWORK_CALLS="true"     # Skip HTTP requests
$env:SKIP_CLOUD_SERVICES="true"    # Skip Pub/Sub, Cloud Storage
```

### Command-Line Options

```powershell
# Alternative to environment variables
python -m pytest --skip-external --skip-llm --skip-network --skip-cloud -v
```

### Configuration Files

- **`pytest.ini`**: Main pytest configuration with markers and options
- **`conftest.py`**: Global fixtures and test setup
- **Service-specific `conftest.py`**: FastAPI test clients and mocks

## Key Testing Patterns

### 1. Pipeline Step Testing

Each pipeline step follows a consistent testing pattern:

```python
class TestStepService:
    @pytest.fixture
    def service(self):
        return StepService()

    @pytest.mark.asyncio
    async def test_core_functionality(self, service):
        # Test with mocked dependencies
        pass

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_with_real_apis(self, service):
        # Integration test with real APIs
        pass
```

### 2. FastAPI Service Testing

```python
@pytest.fixture
def client():
    # Mock external dependencies
    with patch("main.external_service") as mock_service:
        mock_service.return_value = test_data
        yield TestClient(app)

def test_endpoint(client):
    response = client.get("/endpoint")
    assert response.status_code == 200
```

### 3. Multi-LLM Testing

Tests for the 3-model consensus system:

```python
@pytest.fixture
def mock_all_llm_providers():
    return {
        "openai": mock_openai_provider,
        "anthropic": mock_anthropic_provider,
        "xai": mock_xai_provider
    }

@pytest.mark.llm_api
async def test_triangulation_consensus(mock_providers):
    # Test 2-of-3 consensus logic
    pass
```

### 4. Pydantic Model Validation

```python
def test_schema_validation():
    # Test RaceJSON schema compliance
    race_data = {...}
    race = RaceJSON(**race_data)
    assert race.id == expected_id
```

## Test Data Management

### Mock Data Strategy

- **Synthetic Test Data**: Generated test races, candidates, and content
- **Fixture-Based**: Reusable test data via pytest fixtures
- **Deterministic**: Consistent results across test runs

### ChromaDB Testing

```python
@pytest.fixture
def temp_vector_db():
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = ElectionVectorDatabaseManager()
        manager.config["persist_directory"] = temp_dir
        yield manager
```

## Quality Gates

### Coverage Requirements

- **Pipeline Core**: >90% line coverage
- **Services**: >85% line coverage
- **Critical Paths**: 100% coverage (schema validation, consensus logic)

### Performance Benchmarks

- **Unit Tests**: <100ms per test
- **Integration Tests**: <5s per test
- **End-to-End**: <60s full pipeline

### Code Quality Checks

Tests include automated code quality validation:

- **Syntax Validation**: AST parsing for all Python files
- **Import Analysis**: Detect circular imports, missing dependencies
- **Schema Compliance**: Pydantic model validation
- **API Contract Testing**: Service endpoint compliance

## Debugging Test Failures

### Common Issues

1. **Import Errors**: Check `sys.path` setup in test files
2. **Mock Failures**: Verify patch targets match actual module structure
3. **Async Test Issues**: Ensure `@pytest.mark.asyncio` on async tests
4. **External API Failures**: Use appropriate skip markers

### Debug Tools

```powershell
# Verbose output with full tracebacks
python -m pytest -v --tb=long

# Stop on first failure
python -m pytest -x

# Run specific test with debugging
python -m pytest path/to/test.py::test_function -v -s
```

### Log Analysis

Tests use structured logging for debugging:

```python
import logging
logger = logging.getLogger(__name__)

# Enable debug logging in tests
logging.basicConfig(level=logging.DEBUG)
```

## Continuous Integration

### GitHub Actions Integration

The testing strategy supports CI/CD with environment-based skipping:

```yaml
# .github/workflows/test.yml
env:
  SKIP_LLM_APIS: "true"
  SKIP_EXTERNAL_APIS: "true"

steps:
  - run: python -m pytest -v
```

### Pre-commit Hooks

Quality gates run before commits:

- **Test Execution**: Fast unit tests only
- **Code Formatting**: Black, isort
- **Type Checking**: mypy validation
- **Linting**: Comprehensive code analysis

## Future Enhancements

### Planned Improvements

1. **Property-Based Testing**: Hypothesis integration for edge case discovery
2. **Visual Regression**: Playwright tests for web frontend
3. **Load Testing**: Performance testing for high-volume scenarios
4. **Contract Testing**: API contract validation between services
5. **Mutation Testing**: Code quality assessment via mutation testing

### Test Automation Roadmap

- **Q1**: Complete web frontend test coverage
- **Q2**: Performance benchmarking automation
- **Q3**: Contract testing implementation
- **Q4**: Advanced property-based testing

## Best Practices

### Writing Effective Tests

1. **Test Isolation**: Each test should be independent
2. **Clear Naming**: Test names should describe expected behavior
3. **Minimal Setup**: Use fixtures for common test data
4. **Fast Feedback**: Prefer unit tests over integration tests
5. **Realistic Mocking**: Mock external services, not business logic

### Maintaining Test Quality

1. **Regular Review**: Update tests when implementation changes
2. **Coverage Monitoring**: Track and improve test coverage
3. **Performance Tracking**: Monitor test execution time
4. **Documentation**: Keep test documentation current

This testing guide ensures SmarterVote maintains high quality while supporting rapid development and reliable deployments.
