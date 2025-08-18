"""
SmarterVote Pipeline Entry Point - Corpus-First Design v1.2

4-Step Workflow:
0. METADATA EXTRACTION - Parse race details for optimized discovery
1. INGEST - Discover, fetch, extract and filter sources
2. CORPUS - Index in ChromaDB
3. SUMMARIZE & ARBITRATE - Multi-LLM summaries with consensus scoring
4. PUBLISH - RaceJSON v0.2 output
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

from .providers import list_providers, registry
from .schema import ProcessingJob, ProcessingStatus
from .step01_ingest.ContentExtractor import ExtractService
from .step01_ingest.ContentFetcher import WebContentFetcher
from .step01_ingest.DiscoveryService import SourceDiscoveryEngine
from .step01_ingest.MetaDataService import RaceMetadataService
from .step01_ingest.RelevanceCheck.ai_relevance_filter import AIRelevanceFilter
from .step02_corpus import CorpusService
from .step03_summarise import ArbitrationService, SummarizeService
from .step04_publish import PublishService
from .utils.firestore_cache import FirestoreCache

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
        self.discovery = SourceDiscoveryEngine()
        self.fetch = WebContentFetcher()
        self.extract = ExtractService()
        self.relevance = AIRelevanceFilter()
        self.cache = FirestoreCache()
        self.corpus = CorpusService()
        self.summarize = SummarizeService(cheap_mode=cheap_mode)
        self.arbitrate = ArbitrationService(cheap_mode=cheap_mode)
        self.publish = PublishService()

    async def process_race(self, race_id: str) -> bool:
        """
        Process a single race through the 4-step corpus-first pipeline.

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
            race_json = await self.metadata.extract_race_metadata(race_id)
            job.step_metadata = True
            meta = race_json.race_metadata
            if meta:
                logger.info(f"✅ Extracted metadata: {meta.full_office_name} in {meta.jurisdiction}")
                logger.info(f"🎯 Priority issues: {', '.join(meta.major_issues[:3])}")

            # Step 1: INGEST - Discover sources
            logger.info(f"📡 Step 1: INGEST - Finding sources and fresh issues for {race_id}")
            sources = await self.discovery.discover_all_sources(race_id, race_json)
            if not sources:
                logger.warning(f"No sources found for race {race_id}")
                return False
            job.step_discover = True
            logger.info(f"✅ Discovered {len(sources)} total sources (seed + fresh)")

            # Step 1: INGEST - Download raw bytes → /raw/{race}/
            logger.info(f"⬇️  Step 1: INGEST - Downloading {len(sources)} sources")
            raw_content = await self.fetch.fetch_content(sources)
            job.step_fetch = True
            logger.info(f"✅ Fetched {len(raw_content)} items")

            # Step 1: INGEST - HTML/PDF → plain text → /norm/{race}/
            logger.info("📄 Step 1: INGEST - Converting to plain text")
            extracted_content = await self.extract.extract_content(raw_content)
            job.step_extract = True
            logger.info(f"✅ Extracted text from {len(extracted_content)} items")

            logger.info("🔎 AI relevance filtering")
            race_name = race_json.title or race_id
            candidate_names = [c.name for c in race_json.candidates]
            filtered_content = await self.relevance.filter_content(extracted_content, race_name, candidate_names)
            logger.info(f"✅ {len(filtered_content)}/{len(extracted_content)} items passed relevance filter")

            # Cache the filtered content to Firestore
            logger.info("💾 Caching filtered content to Firestore")
            cache_success = await self.cache.cache_content(race_id, filtered_content)
            if cache_success:
                logger.info("✅ Successfully cached filtered content")
            else:
                logger.warning("⚠️ Failed to cache filtered content")

            # Step 2: BUILD CORPUS - Index in ChromaDB
            logger.info("🗂️  Step 2: CORPUS - Indexing in ChromaDB")
            await self.corpus.build_corpus(race_id, filtered_content)
            job.step_corpus = True
            logger.info(f"✅ Built corpus for {race_id}")

            # Step 3: RAG + 3-MODEL SUMMARY - Provider-based triangulation
            logger.info("🤖 Step 3: SUMMARIZE - Provider-based triangulation")
            # Retrieve relevant content from corpus for summarization
            corpus_content = await self.corpus.search_content(race_id)
            all_summaries = await self.summarize.generate_summaries(race_id, corpus_content)
            job.step_rag_summary = True

            # Log summary counts
            race_count = len(all_summaries.get("race_summaries", []))
            candidate_count = len(all_summaries.get("candidate_summaries", []))
            issue_count = len(all_summaries.get("issue_summaries", []))
            logger.info(f"✅ Generated summaries: {race_count} race, {candidate_count} candidate, {issue_count} issue")

            # Step 3: ARBITRATE - Provider-based consensus scoring
            logger.info("⚖️  Step 3: ARBITRATE - Provider-based consensus scoring")
            arbitrated_data = await self.arbitrate.arbitrate_summaries(all_summaries)
            job.step_arbitrate = True
            logger.info("✅ Arbitration complete")

            # Step 4: PUBLISH - RaceJSON v0.2 → /out/{race}.json
            logger.info("📤 Step 4: PUBLISH - Creating RaceJSON v0.2")
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

        finally:
            # Clean up resources
            await self.cache.close()


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
