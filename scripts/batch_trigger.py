"""
Batch trigger script for processing multiple races.

This script can be used to trigger processing for multiple races at once,
either locally or by calling the enqueue API.
"""

import asyncio
import aiohttp
import logging
from typing import List
import argparse


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BatchTrigger:
    """Service for triggering batch race processing."""
    
    def __init__(self, api_url: str = "http://localhost:8080"):
        self.api_url = api_url
    
    async def trigger_races(self, race_ids: List[str]) -> None:
        """
        Trigger processing for multiple races.
        
        Args:
            race_ids: List of race IDs to process
        """
        logger.info(f"Triggering processing for {len(race_ids)} races")
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for race_id in race_ids:
                task = self._trigger_single_race(session, race_id)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Report results
            success_count = 0
            error_count = 0
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to trigger {race_ids[i]}: {result}")
                    error_count += 1
                else:
                    logger.info(f"Successfully triggered {race_ids[i]}")
                    success_count += 1
            
            logger.info(f"Batch trigger completed: {success_count} success, {error_count} errors")
    
    async def _trigger_single_race(self, session: aiohttp.ClientSession, race_id: str) -> bool:
        """Trigger processing for a single race."""
        payload = {
            "race_id": race_id,
            "priority": 1
        }
        
        async with session.post(f"{self.api_url}/process", json=payload) as response:
            if response.status == 200:
                return True
            else:
                error_text = await response.text()
                raise Exception(f"API returned {response.status}: {error_text}")


async def main():
    """Main entry point for batch trigger script."""
    parser = argparse.ArgumentParser(description="Batch trigger race processing")
    parser.add_argument("race_ids", nargs="+", help="Race IDs to process")
    parser.add_argument("--api-url", default="http://localhost:8080", 
                       help="API URL for enqueue service")
    
    args = parser.parse_args()
    
    trigger = BatchTrigger(api_url=args.api_url)
    await trigger.trigger_races(args.race_ids)


if __name__ == "__main__":
    asyncio.run(main())
