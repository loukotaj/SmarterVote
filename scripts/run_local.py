"""
Local development script for processing a single race outside of the cloud environment.

This script is useful for testing and development purposes.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Add the pipeline app to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import CorpusFirstPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Run the pipeline locally for a single race."""
    if len(sys.argv) < 2:
        print("Usage: python run_local.py <race_id> [--full-models]")
        print("Example: python run_local.py mo-senate-2024")
        print("Example: python run_local.py mo-senate-2024 --full-models  # Use full models instead of mini")
        sys.exit(1)

    race_id = sys.argv[1]
    # Default to cheap mode (mini models), allow --full-models to override
    cheap_mode = not ("--full-models" in sys.argv or "--full" in sys.argv)

    logger.info(f"🗳️  Running local Corpus-First pipeline for race: {race_id}")
    if cheap_mode:
        logger.info("💰 Using cheap mode (mini models)")
    else:
        logger.info("🚀 Using full models")

    # Initialize and run pipeline
    pipeline = CorpusFirstPipeline(cheap_mode=cheap_mode)
    success = await pipeline.process_race(race_id)

    if success:
        logger.info("Local pipeline completed successfully")
        print(f"✅ Successfully processed race: {race_id}")
        print(f"🌐 Result should be in data/published/{race_id}.json")
    else:
        logger.error("Local pipeline failed")
        print(f"❌ Failed to process race: {race_id}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
