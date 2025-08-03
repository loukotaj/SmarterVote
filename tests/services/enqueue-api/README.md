# Enqueue API Tests

This directory contains comprehensive tests for the SmarterVote enqueue API service.

## Setup

Install test dependencies:
```bash
pip install -r test-requirements.txt
```

## Running Tests

From the service directory:
```bash
cd services/enqueue-api
python -m pytest ../../tests/services/enqueue-api/ -v
```

From the repository root:
```bash
python -m pytest tests/services/enqueue-api/ -v
```

With coverage:
```bash
python -m pytest tests/services/enqueue-api/ --cov=services.enqueue-api --cov-report=html
```

## Test Coverage

The tests cover:

- **Health Checks**: Root endpoint and detailed health checks with Pub/Sub status
- **Race Processing**: Success cases, validation, error handling
- **Pub/Sub Integration**: Mocked publisher with various failure scenarios
- **Request Validation**: Missing fields, invalid data, edge cases
- **Message Serialization**: Complex metadata, datetime handling
- **Job ID Generation**: Uniqueness and format validation
- **Error Handling**: Network failures, timeouts, validation errors
- **CORS Configuration**: Cross-origin request handling
- **Metrics Endpoint**: Basic metrics collection

## Test Structure

- `conftest.py`: Shared test configuration and fixtures
- `test_main.py`: Main test suite for all API endpoints
- `test-requirements.txt`: Test-specific dependencies

## Mocking

Tests use comprehensive mocking for:
- Google Cloud Pub/Sub client and operations
- Environment variables for different test scenarios
- Network failures and timeout conditions
