"""
Local development script for processing a single race outside of the cloud environment.

This script is useful for testing and development purposes.
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add the pipeline app to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))

from pipeline.app import Pipeline


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Run the pipeline locally for a single race."""
    if len(sys.argv) < 2:
        print("Usage: python run_local.py <race_id>")
        sys.exit(1)
    
    race_id = sys.argv[1]
    logger.info(f"Running local pipeline for race: {race_id}")
    
    # Initialize and run pipeline
    pipeline = Pipeline()
    success = await pipeline.process_race(race_id)
    
    if success:
        logger.info("Local pipeline completed successfully")
        print(f"✅ Successfully processed race: {race_id}")
    else:
        logger.error("Local pipeline failed")
        print(f"❌ Failed to process race: {race_id}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
