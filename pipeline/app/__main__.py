"""
SmarterVote Pipeline Entry Point - Corpus-First Design v1.1

7-Step Workflow:
1. DISCOVER - Seed URLs + Google dorks + Fresh issue search for 11 canonical issues
2. FETCH - Download raw bytes
3. EXTRACT - HTML/PDF → plain text  
4. BUILD CORPUS - Index in ChromaDB
5. RAG + 3-MODEL SUMMARY - GPT-4o, Claude 3.5, Grok-4 triangulation
6. ARBITRATE - 2-of-3 consensus with confidence scoring
7. PUBLISH - RaceJSON v0.2 output
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional

from .schema import (
    RaceJSON, ProcessingJob, ProcessingStatus, 
    CanonicalIssue, ConfidenceLevel
)
from .discover import DiscoveryService
from .fetch import FetchService
from .extract import ExtractService
from .corpus import CorpusService
from .summarise import SummarizeService
from .arbitrate import ArbitrationService
from .publish import PublishService


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CorpusFirstPipeline:
    """Corpus-First Pipeline Orchestrator for SmarterVote."""
    
    def __init__(self):
        self.discovery = DiscoveryService()
        self.fetch = FetchService()
        self.extract = ExtractService()
        self.corpus = CorpusService()
        self.summarize = SummarizeService()
        self.arbitrate = ArbitrationService()
        self.publish = PublishService()
    
    async def process_race(self, race_id: str) -> bool:
        """
        Process a single race through the 7-step corpus-first pipeline.
        
        Args:
            race_id: Race slug like 'mo-senate-2024'
            
        Returns:
            bool: True if processing completed successfully
        """
        logger.info(f"🚀 Starting Corpus-First Pipeline for race: {race_id}")
        
        # Create processing job
        job = ProcessingJob(
            job_id=f"job_{race_id}_{int(datetime.utcnow().timestamp())}",
            race_id=race_id,
            status=ProcessingStatus.PROCESSING,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow()
        )
        
        try:
            # Step 1: DISCOVER - Seed URLs + Google dorks + Fresh issue search
            logger.info(f"📡 Step 1: DISCOVER - Finding sources and fresh issues for {race_id}")
            sources = await self.discovery.discover_all_sources(race_id)
            if not sources:
                logger.warning(f"No sources found for race {race_id}")
                return False
            job.step_discover = True
            logger.info(f"✅ Discovered {len(sources)} total sources (seed + fresh)")
            
            # Step 2: FETCH - Download raw bytes → /raw/{race}/
            logger.info(f"⬇️  Step 2: FETCH - Downloading {len(sources)} sources")
            raw_content = await self.fetch.fetch_content(sources)
            job.step_fetch = True
            logger.info(f"✅ Fetched {len(raw_content)} items")
            
            # Step 3: EXTRACT - HTML/PDF → plain text → /norm/{race}/
            logger.info(f"📄 Step 3: EXTRACT - Converting to plain text")
            extracted_content = await self.extract.extract_content(raw_content)
            job.step_extract = True
            logger.info(f"✅ Extracted text from {len(extracted_content)} items")
            
            # Step 4: BUILD CORPUS - Index in ChromaDB
            logger.info(f"🗂️  Step 4: BUILD CORPUS - Indexing in ChromaDB")
            await self.corpus.build_corpus(race_id, extracted_content)
            job.step_corpus = True
            logger.info(f"✅ Built corpus for {race_id}")
            
            # Step 5: RAG + 3-MODEL SUMMARY - Triangulation
            logger.info(f"🤖 Step 5: RAG + 3-MODEL SUMMARY - LLM Triangulation")
            # Retrieve relevant content from corpus for summarization
            corpus_content = await self.corpus.search_content(race_id)
            summaries = await self.summarize.generate_summaries(race_id, corpus_content)
            job.step_rag_summary = True
            logger.info(f"✅ Generated triangulated summaries")
            
            # Step 6: ARBITRATE - 2-of-3 consensus
            logger.info(f"⚖️  Step 6: ARBITRATE - Confidence scoring")
            arbitrated_data = await self.arbitrate.arbitrate_summaries(summaries)
            job.step_arbitrate = True
            logger.info(f"✅ Arbitration complete")
            
            # Step 7: PUBLISH - RaceJSON v0.2 → /out/{race}.json
            logger.info(f"📤 Step 7: PUBLISH - Creating RaceJSON v0.2")
            race_json = await self.publish.create_race_json(race_id, arbitrated_data)
            success = await self.publish.publish_race(race_json)
            job.step_publish = True
            
            if success:
                job.status = ProcessingStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                logger.info(f"🎉 Pipeline completed successfully for {race_id}")
                logger.info(f"📊 Published RaceJSON v0.2 to gs://sv-data/out/{race_id}.json")
                return True
            else:
                raise Exception("Publishing failed")
                
        except Exception as e:
            logger.error(f"❌ Pipeline failed for race {race_id}: {str(e)}")
            job.status = ProcessingStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            return False


async def main():
    """Main entry point for the corpus-first pipeline."""
    if len(sys.argv) < 2:
        logger.error("Usage: python -m app <race_slug>")
        logger.error("Example: python -m app mo-senate-2024")
        sys.exit(1)
    
    race_id = sys.argv[1]
    logger.info(f"🗳️  SmarterVote Corpus-First Pipeline v1.1")
    logger.info(f"🎯 Processing race: {race_id}")
    
    pipeline = CorpusFirstPipeline()
    success = await pipeline.process_race(race_id)
    
    if success:
        logger.info("🏆 Pipeline completed successfully")
        logger.info(f"🌐 Result will be available at smarter.vote/{race_id}")
        sys.exit(0)
    else:
        logger.error("💥 Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
