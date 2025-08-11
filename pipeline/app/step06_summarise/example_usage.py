#!/usr/bin/env python3
"""
Example usage of the LLM Summarization Engine.

This script demonstrates how to use the LLMSummarizationEngine
for generating AI summaries with multiple LLM providers.

Usage:
    python example_usage.py

Note: Set environment variables OPENAI_API_KEY, ANTHROPIC_API_KEY,
and/or XAI_API_KEY before running this script.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the project paths for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from pipeline.app.summarise.llm_summarization_engine import LLMSummarizationEngine
    from shared import ExtractedContent, Source, SourceType
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("Make sure to install required dependencies and set PYTHONPATH correctly")
    sys.exit(1)


def create_sample_content() -> list:
    """Create sample extracted content for demonstration."""
    return [
        ExtractedContent(
            source=Source(
                url="https://example.com/candidate-website",
                type=SourceType.WEBSITE,
                title="Candidate Official Website",
                last_accessed=datetime.utcnow(),
            ),
            text="""
            Senator Jane Smith has served in the US Senate for 8 years,
            representing the state of California. She chairs the Healthcare
            Subcommittee and has authored three major pieces of healthcare
            legislation. On economic policy, she supports increased
            infrastructure spending and tax credits for renewable energy
            companies. Her voting record shows consistent support for
            environmental protection measures and consumer rights legislation.
            """,
            metadata={"word_count": 58},
            extraction_timestamp=datetime.utcnow(),
            word_count=58,
            language="en",
        ),
        ExtractedContent(
            source=Source(
                url="https://example.com/recent-interview",
                type=SourceType.NEWS,
                title="Recent Interview - Policy Platform",
                last_accessed=datetime.utcnow(),
            ),
            text="""
            In a recent interview, Senator Smith outlined her key priorities
            for the upcoming term. She emphasized the need for comprehensive
            healthcare reform, including expanding Medicare eligibility
            and reducing prescription drug costs. On climate change, she supports
            the Green New Deal and has proposed legislation for carbon pricing.
            She also advocates for campaign finance reform and increased
            federal funding for education and scientific research.
            """,
            metadata={"word_count": 65},
            extraction_timestamp=datetime.utcnow(),
            word_count=65,
            language="en",
        ),
        ExtractedContent(
            source=Source(
                url="https://example.com/voting-record",
                type=SourceType.GOVERNMENT,
                title="Official Voting Record",
                last_accessed=datetime.utcnow(),
            ),
            text="""
            Voting Record Analysis: Senator Smith voted YES on the
            Infrastructure Investment Act (2022), YES on the Climate Action
            Bill (2023), YES on the Healthcare Accessibility Act (2021),
            and NO on the Corporate Tax Reduction Act (2022). She has a 95%
            attendance rate for committee hearings and has sponsored or
            co-sponsored 47 bills in the current session.
            """,
            metadata={"word_count": 56},
            extraction_timestamp=datetime.utcnow(),
            word_count=56,
            language="en",
        ),
    ]


async def demonstrate_basic_usage():
    """Demonstrate basic usage of the LLM Summarization Engine."""
    logger.info("=== LLM Summarization Engine Demo ===")

    async with LLMSummarizationEngine(cheap_mode=True) as engine:
        # Validate configuration
        validation = engine.validate_configuration()
        logger.info(f"Configuration validation: {validation}")

        if not validation["valid"]:
            logger.error("Configuration is not valid. Check your API keys.")
            for error in validation["errors"]:
                logger.error(f"  Error: {error}")
            return

        if validation["warnings"]:
            for warning in validation["warnings"]:
                logger.warning(f"  Warning: {warning}")

        # Create sample content
        content = create_sample_content()
        logger.info(f"Created {len(content)} sample content items")

        # Generate summaries
        logger.info("Generating summaries...")
        summaries = await engine.generate_summaries(
            race_id="example-senate-race-2024",
            content=content,
            task_type="candidate_summary",
        )

        logger.info(f"Generated {len(summaries)} summaries")

        # Display results
        for i, summary in enumerate(summaries, 1):
            logger.info(f"\n--- Summary {i} ({summary.model}) ---")
            logger.info(f"Confidence: {summary.confidence}")
            logger.info(f"Tokens used: {summary.tokens_used}")
            logger.info(f"Content preview: {summary.content[:200]}...")

        # Demonstrate triangulation
        if len(summaries) >= 2:
            triangulation = engine.triangulate_summaries(summaries)
            logger.info("\n--- Triangulation Results ---")
            logger.info(f"Consensus confidence: {triangulation['consensus_confidence']}")
            logger.info(f"Consensus method: {triangulation['consensus_method']}")
            logger.info(f"Models used: {triangulation['models_used']}")
            logger.info(f"Total tokens: {triangulation['total_tokens_used']}")

        # Show API statistics
        stats = engine.get_api_statistics()
        logger.info("\n--- API Usage Statistics ---")
        logger.info(f"Total calls: {stats['total_calls']}")
        logger.info(f"Successful calls: {stats['successful_calls']}")
        logger.info(f"Failed calls: {stats['failed_calls']}")
        logger.info(f"Total tokens used: {stats['total_tokens']}")


async def demonstrate_error_handling():
    """Demonstrate error handling scenarios."""
    logger.info("\n=== Error Handling Demo ===")

    # Test with invalid API key
    test_env = os.environ.copy()
    test_env["OPENAI_API_KEY"] = "invalid-key-123"

    with_invalid_key = LLMSummarizationEngine(cheap_mode=True)
    # In a real scenario, this would fail with invalid credentials
    # but our demo will just show the configuration

    validation = with_invalid_key.validate_configuration()
    logger.info(f"Configuration with invalid key: {validation}")


def main():
    """Main demonstration function."""
    # Check for API keys
    api_keys = {
        "OpenAI": os.getenv("OPENAI_API_KEY"),
        "Anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "xAI": os.getenv("XAI_API_KEY"),
    }

    available_keys = [provider for provider, key in api_keys.items() if key]

    if not available_keys:
        logger.warning("No API keys found in environment variables.")
        logger.warning("Set OPENAI_API_KEY, ANTHROPIC_API_KEY, and/or XAI_API_KEY " "to run with real APIs.")
        logger.info("Proceeding with configuration demo only...")
    else:
        logger.info(f"Found API keys for: {', '.join(available_keys)}")

    # Run the demonstration
    asyncio.run(demonstrate_basic_usage())
    asyncio.run(demonstrate_error_handling())

    logger.info("\n=== Demo Complete ===")


if __name__ == "__main__":
    main()
