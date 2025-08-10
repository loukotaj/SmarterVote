# LLM Summarization Engine

This module implements the core AI-powered summarization engine for SmarterVote's multi-LLM consensus system. It provides robust integration with three major LLM providers for generating high-quality political content summaries.

## Features

### Multi-Provider Support
**Cheap Mode (Mini Models - Default)**:
- **OpenAI GPT-4o-mini**: Cost-effective reasoning and analysis
- **Anthropic Claude 3 Haiku**: Fast and efficient perspective analysis
- **xAI Grok**: Budget-friendly context analysis

**Standard Mode (Premium)**:
- **OpenAI GPT-4o**: Advanced reasoning and analysis
- **Anthropic Claude 3.5**: Balanced perspective and critical evaluation
- **xAI Grok**: Real-time context and trend detection

### Mode Configuration
```python
# Cheap mode (default) - Uses mini models for cost efficiency
engine = LLMSummarizationEngine()

# Standard mode - Uses full models for premium quality
engine = LLMSummarizationEngine(cheap_mode=False)
```

Command line usage:
```bash
# Cheap mode (default)
python scripts/run_local.py mo-senate-2024

# Standard mode with full models
python scripts/run_local.py mo-senate-2024 --full-models
```

### Core Capabilities
- ✅ **Async/Await Architecture**: Non-blocking concurrent API calls
- ✅ **Automatic Configuration**: Environment-based API key loading
- ✅ **Robust Error Handling**: Custom exceptions with retry logic
- ✅ **Rate Limiting**: Exponential backoff with retry-after header support
- ✅ **Token Tracking**: Detailed usage statistics and cost monitoring
- ✅ **Quality Assessment**: Intelligent confidence scoring based on content analysis
- ✅ **Triangulation**: 2-of-3 consensus algorithm for bias reduction

## Quick Start

### Environment Setup
```bash
# Set API keys in your environment
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
export XAI_API_KEY="your-xai-key"
```

### Basic Usage
```python
from pipeline.app.summarise.llm_summarization_engine import LLMSummarizationEngine

async def example():
    async with LLMSummarizationEngine() as engine:
        # Validate configuration
        validation = engine.validate_configuration()
        if not validation["valid"]:
            print("Configuration issues:", validation["errors"])
            return

        # Generate summaries
        summaries = await engine.generate_summaries(
            race_id="example-race-2024",
            content=extracted_content_list,
            task_type="candidate_summary"
        )

        # Triangulate for consensus
        if len(summaries) >= 2:
            consensus = engine.triangulate_summaries(summaries)
            print(f"Consensus confidence: {consensus['consensus_confidence']}")
```

## API Reference

### LLMSummarizationEngine

#### Constructor
```python
engine = LLMSummarizationEngine(cheap_mode=True)  # Default: uses mini models
```
Automatically loads API keys from environment variables and configures providers.
By default, uses cost-effective mini models. Set `cheap_mode=False` for premium models.

#### Key Methods

##### `generate_summaries(race_id, content, task_type="general_summary")`
Generate summaries from all enabled LLM providers.

**Parameters:**
- `race_id` (str): Unique identifier for the electoral race
- `content` (List[ExtractedContent]): Source content to summarize
- `task_type` (str): Template type ("candidate_summary", "issue_stance", "general_summary")

**Returns:** `List[Summary]` - Summaries from each successful provider

##### `triangulate_summaries(summaries)`
Analyze multiple summaries to determine consensus confidence.

**Parameters:**
- `summaries` (List[Summary]): Summaries to triangulate

**Returns:** `Dict` - Consensus analysis with confidence level and method

##### `validate_configuration()`
Check current setup and identify potential issues.

**Returns:** `Dict` - Validation status with errors/warnings

##### `get_api_statistics()`
Retrieve detailed usage statistics.

**Returns:** `Dict` - API call counts, token usage, and error rates

## Confidence Levels

The engine assesses summary quality using linguistic indicators:

- **HIGH**: Strong evidence indicators, verified sources, comprehensive analysis
- **MEDIUM**: Moderate confidence signals, qualified statements, reasonable length
- **LOW**: Uncertainty indicators, short content, placeholder text
- **UNKNOWN**: Insufficient content or empty responses

## Error Handling

### Custom Exceptions

#### `LLMAPIError`
Base exception for all LLM API errors.
```python
try:
    result = await engine._call_openai_api(config, prompt)
except LLMAPIError as e:
    print(f"Provider: {e.provider}, Status: {e.status_code}")
```

#### `RateLimitError`
Specific handling for rate limiting scenarios.
```python
except RateLimitError as e:
    print(f"Rate limited, retry after: {e.retry_after}s")
```

### Retry Logic
- **3 automatic retries** with exponential backoff
- **Respects rate limit headers** from API responses
- **Graceful degradation** when providers fail

## Testing

Run the comprehensive test suite:
```bash
cd pipeline
python -m pytest app/summarise/test_service.py -v
```

### Test Coverage
- ✅ Configuration validation (API keys, provider setup)
- ✅ Content preparation and truncation
- ✅ Confidence assessment algorithms
- ✅ API call success/failure scenarios
- ✅ Rate limiting and retry logic
- ✅ Statistics tracking accuracy
- ✅ Triangulation consensus algorithms
- ✅ Async context manager lifecycle
- ✅ Error handling and custom exceptions

## Example Usage

See `example_usage.py` for a complete demonstration including:
- Configuration validation
- Sample content creation
- Summary generation workflow
- Triangulation and consensus analysis
- Statistics and monitoring

## Integration with SmarterVote Pipeline

This engine integrates with the broader SmarterVote pipeline:

1. **Input**: Receives `ExtractedContent` from the Extract step
2. **Processing**: Generates summaries using multiple LLMs
3. **Output**: Produces `Summary` objects for the Arbitrate step
4. **Consensus**: Supports 2-of-3 triangulation for bias reduction

## Production Considerations

### Resource Management
- Uses async context manager for proper cleanup
- HTTP client connection pooling and timeout handling
- Memory-efficient content chunking for large datasets

### Monitoring
- Detailed logging at DEBUG/INFO/WARNING levels
- API usage statistics for cost tracking
- Error rate monitoring per provider

### Scalability
- Concurrent API calls to multiple providers
- Configurable timeout and retry parameters
- Graceful handling of provider unavailability

## Configuration

### Environment Variables
All configuration is handled through environment variables as defined in `.env.example`:

```bash
# Required for each provider you want to enable
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
XAI_API_KEY=your_xai_key

# Optional: Logging configuration
LOG_LEVEL=INFO
```

### Provider Models
- **OpenAI**: `gpt-4o`
- **Anthropic**: `claude-3-5-sonnet-20241022`
- **xAI**: `grok-beta`

All models use low temperature (0.1) for consistent, factual responses.
