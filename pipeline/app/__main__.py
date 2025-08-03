"""
SmarterVote Pipeline Entry Point

This module serves as the main entry point for the SmarterVote data processing pipeline.
It orchestrates the entire workflow from discovery to publication.
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional

from .schema import Race, ProcessingJob, ProcessingStatus
from .discover import DiscoveryService
from .fetch import FetchService
from .extract import ExtractService
from .corpus import CorpusService
from .summarise import SummarizeService
from .arbitrate import ArbitrateService
from .publish import PublishService


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Pipeline:
    """Main pipeline orchestrator."""
    
    def __init__(self):
        self.discovery = DiscoveryService()
        self.fetch = FetchService()
        self.extract = ExtractService()
        self.corpus = CorpusService()
        self.summarize = SummarizeService()
        self.arbitrate = ArbitrateService()
        self.publish = PublishService()
    
    async def process_race(self, race_id: str) -> bool:
        """
        Process a single race through the entire pipeline.
        
        Args:
            race_id: Unique identifier for the race to process
            
        Returns:
            bool: True if processing completed successfully
        """
        logger.info(f"Starting pipeline for race: {race_id}")
        
        try:
            # Create processing job
            job = ProcessingJob(
                job_id=f"job_{race_id}_{int(datetime.utcnow().timestamp())}",
                race_id=race_id,
                status=ProcessingStatus.PROCESSING,
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow()
            )
            
            # Step 1: Discover sources
            logger.info(f"Step 1: Discovering sources for race {race_id}")
            sources = await self.discovery.discover_sources(race_id)
            if not sources:
                logger.warning(f"No sources found for race {race_id}")
                return False
            
            # Step 2: Fetch content
            logger.info(f"Step 2: Fetching content from {len(sources)} sources")
            raw_content = await self.fetch.fetch_all(sources)
            
            # Step 3: Extract text
            logger.info(f"Step 3: Extracting text from {len(raw_content)} items")
            extracted_content = await self.extract.extract_all(raw_content)
            
            # Step 4: Build corpus
            logger.info(f"Step 4: Building vector corpus")
            await self.corpus.index_content(race_id, extracted_content)
            
            # Step 5: Generate summaries
            logger.info(f"Step 5: Generating AI summaries")
            summaries = await self.summarize.generate_summaries(race_id, extracted_content)
            
            # Step 6: Arbitrate confidence
            logger.info(f"Step 6: Arbitrating confidence scores")
            arbitrated_data = await self.arbitrate.process(summaries)
            
            # Step 7: Publish results
            logger.info(f"Step 7: Publishing race data")
            race_data = await self.publish.create_race_json(race_id, arbitrated_data)
            success = await self.publish.publish(race_data)
            
            if success:
                job.status = ProcessingStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                logger.info(f"Pipeline completed successfully for race {race_id}")
                return True
            else:
                raise Exception("Publishing failed")
                
        except Exception as e:
            logger.error(f"Pipeline failed for race {race_id}: {str(e)}")
            job.status = ProcessingStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            return False


async def main():
    """Main entry point for the pipeline."""
    if len(sys.argv) < 2:
        logger.error("Usage: python -m app <race_id>")
        sys.exit(1)
    
    race_id = sys.argv[1]
    logger.info(f"SmarterVote Pipeline starting for race: {race_id}")
    
    pipeline = Pipeline()
    success = await pipeline.process_race(race_id)
    
    if success:
        logger.info("Pipeline completed successfully")
        sys.exit(0)
    else:
        logger.error("Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
