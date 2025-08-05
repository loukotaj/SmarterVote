"""
Local development script for processing a single race outside of the cloud environment.

This script is useful for testing and development purposes.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the pipeline app to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import CorpusFirstPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Run the pipeline locally for a single race."""
    if len(sys.argv) < 2:
        print("Usage: python run_local.py <race_id>")
        print("Example: python run_local.py mo-senate-2024")
        sys.exit(1)

    race_id = sys.argv[1]
    logger.info(f"🗳️  Running local Corpus-First pipeline for race: {race_id}")

    # Initialize and run pipeline
    pipeline = CorpusFirstPipeline()
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
