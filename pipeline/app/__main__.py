"""
SmarterVote Pipeline Entry Point - Corpus-First Design v1.2

8-Step Workflow:
0. METADATA EXTRACTION - Parse race details for optimized discovery
1. DISCOVER - Seed URLs + Google dorks + Fresh issue search for 11 canonical issues
2. FETCH - Download raw bytes
3. EXTRACT - HTML/PDF → plain text
4. BUILD CORPUS - Index in ChromaDB
5. RAG + 3-MODEL SUMMARY - GPT-4o, Claude 3.5, grok-3 triangulation
6. ARBITRATE - 2-of-3 consensus with confidence scoring
7. PUBLISH - RaceJSON v0.2 output
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .arbitrate import ArbitrationService
from .corpus import CorpusService
from .discover import DiscoveryService
from .extract import ExtractService
from .fetch import FetchService
from .metadata import RaceMetadataService
from .providers import list_providers, registry
from .publish import PublishService
from .schema import ProcessingJob, ProcessingStatus
from .summarise import SummarizeService

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Log environment setup
try:
    # Check if key environment variables are loaded
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    xai_key = os.getenv("XAI_API_KEY")

    if openai_key:
        logger.info("✅ OPENAI_API_KEY loaded")
    else:
        logger.warning("⚠️ OPENAI_API_KEY not found")

    if anthropic_key:
        logger.info("✅ ANTHROPIC_API_KEY loaded")
    else:
        logger.warning("⚠️ ANTHROPIC_API_KEY not found")

    if xai_key:
        logger.info("✅ XAI_API_KEY loaded")
    else:
        logger.warning("⚠️ XAI_API_KEY not found")

except Exception as e:
    logger.error(f"❌ Error checking environment variables: {e}")


class CorpusFirstPipeline:
    """Corpus-First Pipeline Orchestrator for SmarterVote."""

    def __init__(self, cheap_mode: bool = True):
        self.cheap_mode = cheap_mode

        # Log available providers and models
        providers = list_providers()
        logger.info(f"🤖 Available AI providers: {', '.join(providers)}")

        # Initialize services with provider registry
        self.metadata = RaceMetadataService()
        self.discovery = DiscoveryService()
        self.fetch = FetchService()
        self.extract = ExtractService()
        self.corpus = CorpusService()
        self.summarize = SummarizeService(cheap_mode=cheap_mode)
        self.arbitrate = ArbitrationService(cheap_mode=cheap_mode)
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
            started_at=datetime.utcnow(),
        )

        try:
            # Step 0: EXTRACT RACE METADATA - High-level race details for optimization
            logger.info(f"📋 Step 0: EXTRACT RACE METADATA - Analyzing race structure for {race_id}")
            race_metadata = await self.metadata.extract_race_metadata(race_id)
            job.step_metadata = True
            logger.info(f"✅ Extracted metadata: {race_metadata.full_office_name} in {race_metadata.jurisdiction}")
            logger.info(f"🎯 Priority issues: {', '.join(race_metadata.major_issues[:3])}")

            # Step 1: DISCOVER - Seed URLs + Google dorks + Fresh issue search
            logger.info(f"📡 Step 1: DISCOVER - Finding sources and fresh issues for {race_id}")
            sources = await self.discovery.discover_all_sources(race_id, race_metadata)
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
            logger.info("📄 Step 3: EXTRACT - Converting to plain text")
            extracted_content = await self.extract.extract_content(raw_content)
            job.step_extract = True
            logger.info(f"✅ Extracted text from {len(extracted_content)} items")

            # Step 4: BUILD CORPUS - Index in ChromaDB
            logger.info("🗂️  Step 4: BUILD CORPUS - Indexing in ChromaDB")
            await self.corpus.build_corpus(race_id, extracted_content)
            job.step_corpus = True
            logger.info(f"✅ Built corpus for {race_id}")

            # Step 5: RAG + 3-MODEL SUMMARY - Provider-based triangulation
            logger.info("🤖 Step 5: RAG + 3-MODEL SUMMARY - Provider-based triangulation")
            # Retrieve relevant content from corpus for summarization
            corpus_content = await self.corpus.search_content(race_id)
            all_summaries = await self.summarize.generate_summaries(race_id, corpus_content)
            job.step_rag_summary = True

            # Log summary counts
            race_count = len(all_summaries.get("race_summaries", []))
            candidate_count = len(all_summaries.get("candidate_summaries", []))
            issue_count = len(all_summaries.get("issue_summaries", []))
            logger.info(f"✅ Generated summaries: {race_count} race, {candidate_count} candidate, {issue_count} issue")

            # Step 6: ARBITRATE - Provider-based consensus scoring
            logger.info("⚖️  Step 6: ARBITRATE - Provider-based consensus scoring")
            arbitrated_data = await self.arbitrate.arbitrate_summaries(all_summaries)
            job.step_arbitrate = True
            logger.info("✅ Arbitration complete")

            # Step 7: PUBLISH - RaceJSON v0.2 → /out/{race}.json
            logger.info("📤 Step 7: PUBLISH - Creating RaceJSON v0.2")
            race_json = await self.publish.create_race_json(race_id, arbitrated_data, race_metadata)
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
        logger.error("Usage: python -m app <race_slug> [--full-models]")
        logger.error("Example: python -m app mo-senate-2024")
        logger.error("Example: python -m app mo-senate-2024 --full-models")
        sys.exit(1)

    race_id = sys.argv[1]
    # Default to cheap mode (mini models), allow flags to override to full models
    cheap_mode = not (
        "--full-models" in sys.argv
        or "--full" in sys.argv
        or os.getenv("SMARTERVOTE_CHEAP_MODE", "").lower() in ["false", "0", "no"]
    )

    logger.info(f"🗳️  SmarterVote Corpus-First Pipeline v1.2")
    logger.info(f"🎯 Processing race: {race_id}")
    if cheap_mode:
        logger.info("💰 Using cheap mode (mini models)")
    else:
        logger.info("🚀 Using full models")

    pipeline = CorpusFirstPipeline(cheap_mode=cheap_mode)
    success = await pipeline.process_race(race_id)

    if success:
        logger.info("🏆 Pipeline completed successfully")
        logger.info("🌐 Result will be available at smarter.vote/{race_id}")
        sys.exit(0)
    else:
        logger.error("💥 Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
