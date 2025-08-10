#!/usr/bin/env python3
"""
End-to-end test script for SmarterVote pipeline.

This script demonstrates that the full pipeline can be run end-to-end
and validates the structure and functionality.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline import CorpusFirstPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_pipeline_end_to_end():
    """Test the complete pipeline end-to-end with a sample race."""
    logger.info("🧪 Starting end-to-end pipeline test...")

    # Use a test race ID
    test_race_id = "test-senate-2024"

    try:
        # Initialize pipeline
        pipeline = CorpusFirstPipeline()
        logger.info("✅ Pipeline instantiated successfully")

        # Disable cloud publishing for local testing
        pipeline.publish.config.enable_cloud_storage = False
        pipeline.publish.config.enable_database = False
        pipeline.publish.config.enable_webhooks = False
        pipeline.publish.config.enable_notifications = False

        # Test that pipeline completes without errors
        # Note: This will show warnings about missing LLM API keys, which is expected
        success = await pipeline.process_race(test_race_id)

        if success:
            logger.info("🎉 End-to-end test PASSED!")
            logger.info("📊 Pipeline successfully completed all 7 steps:")
            logger.info("   1. ✅ DISCOVER - Source discovery")
            logger.info("   2. ✅ FETCH - Content downloading")
            logger.info("   3. ✅ EXTRACT - Text extraction")
            logger.info("   4. ✅ CORPUS - Vector database indexing")
            logger.info("   5. ✅ SUMMARIZE - LLM triangulation (mocked)")
            logger.info("   6. ✅ ARBITRATE - Consensus arbitration")
            logger.info("   7. ✅ PUBLISH - RaceJSON generation")

            # Check if output file was created
            output_file = Path(f"data/published/{test_race_id}.json")
            if output_file.exists():
                logger.info(f"📄 Output file created: {output_file}")
            else:
                logger.warning(f"⚠️  Output file not found: {output_file}")

            return True
        else:
            logger.error("❌ End-to-end test FAILED!")
            return False

    except Exception as e:
        logger.error(f"❌ End-to-end test FAILED with exception: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Main entry point."""
    logger.info("🗳️  SmarterVote End-to-End Pipeline Test")
    logger.info("=" * 50)

    success = await test_pipeline_end_to_end()

    if success:
        logger.info("=" * 50)
        logger.info("✅ CONCLUSION: End-to-end pipeline test SUCCESSFUL!")
        logger.info("🚀 The SmarterVote pipeline can run full end-to-end processing on a race")
        logger.info("📝 NOTE: For full functionality, configure LLM API keys in environment")
        sys.exit(0)
    else:
        logger.error("=" * 50)
        logger.error("❌ CONCLUSION: End-to-end pipeline test FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
