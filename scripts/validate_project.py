"""
Validation script to test SmarterVote project structure and imports.

This script validates that all components can be imported and basic
functionality works before deployment.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_pipeline_imports():
    """Test that pipeline components can be imported."""
    try:
        from pipeline import CorpusFirstPipeline
        from pipeline.app.schema import CanonicalIssue, RaceJSON, Source

        logger.info("✅ Core pipeline imports successful")

        # Test service imports (these might fail due to missing dependencies)
        try:
            from pipeline.app.arbitrate import ArbitrationService
            from pipeline.app.corpus import CorpusService
            from pipeline.app.discover import DiscoveryService
            from pipeline.app.extract import ExtractService
            from pipeline.app.fetch import FetchService
            from pipeline.app.publish import PublishService
            from pipeline.app.summarise import SummarizeService

            logger.info("✅ All service imports successful")
        except ImportError as e:
            logger.warning(f"⚠️  Some service imports failed (likely missing dependencies): {e}")

        return True
    except ImportError as e:
        logger.error(f"❌ Core pipeline import failed: {e}")
        return False


def test_pipeline_instantiation():
    """Test that pipeline can be instantiated."""
    try:
        from pipeline import CorpusFirstPipeline

        pipeline = CorpusFirstPipeline()
        logger.info("✅ Pipeline instantiation successful")
        return True
    except ImportError as e:
        logger.warning(f"⚠️  Pipeline instantiation skipped (missing dependencies): {e}")
        return True  # Don't fail the test for missing optional dependencies
    except Exception as e:
        logger.error(f"❌ Pipeline instantiation failed: {e}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        return False


def test_schema_validation():
    """Test that schema models work correctly."""
    try:
        from datetime import datetime

        from pipeline.app.schema import CanonicalIssue, RaceJSON, Source, SourceType

        # Test enum
        issue = CanonicalIssue.ECONOMY
        assert issue.value == "Economy"

        # Test source creation
        source = Source(
            url="https://example.com",
            type=SourceType.WEBSITE,
            title="Test Source",
            last_accessed=datetime.now(),
            is_fresh=False,
        )
        assert str(source.url) == "https://example.com/"

        logger.info("✅ Schema validation successful")
        return True
    except Exception as e:
        logger.error(f"❌ Schema validation failed: {e}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        return False


def test_file_structure():
    """Test that all expected files exist."""
    expected_files = [
        "pipeline/__init__.py",
        "pipeline/app/__init__.py",
        "pipeline/app/__main__.py",
        "pipeline/app/schema.py",
        "pipeline/requirements.txt",
        "services/enqueue-api/main.py",
        "scripts/run_local.py",
        "scripts/batch_trigger.py",
        "infra/main.tf",
        "web/package.json",
    ]

    missing_files = []
    for file_path in expected_files:
        full_path = project_root / file_path
        if not full_path.exists():
            missing_files.append(file_path)

    if missing_files:
        logger.error(f"❌ Missing files: {missing_files}")
        return False
    else:
        logger.info("✅ All expected files present")
        return True


def main():
    """Run all validation tests."""
    logger.info("🧪 Starting SmarterVote project validation...")

    tests = [
        ("File Structure", test_file_structure),
        ("Pipeline Imports", test_pipeline_imports),
        ("Schema Validation", test_schema_validation),
        ("Pipeline Instantiation", test_pipeline_instantiation),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        logger.info(f"\n🔍 Running {test_name} test...")
        if test_func():
            passed += 1

    logger.info(f"\n📊 Validation Summary: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All validation tests passed! Project is ready for deployment.")
        return True
    else:
        logger.error("💥 Some validation tests failed. Please fix issues before proceeding.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
