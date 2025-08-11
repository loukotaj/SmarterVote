"""
Tests for AI Enrichment functionality
"""

import pytest
from unittest.mock import patch
from datetime import datetime
import sys
from pathlib import Path

# Add the pipeline app to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock imports to avoid dependency issues
try:
    from pipeline.app.utils.ai_enrichment import ai_enrich, hash_claims, AIAnnotations
    from pipeline.app.schema import ExtractedContent, Source, SourceType

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Pipeline imports not available")
class TestAIEnrichment:
    """Test AI enrichment functionality."""

    def test_hash_claims_empty(self):
        """Test claim hashing with empty claims."""
        assert hash_claims([]) == ""

    def test_hash_claims_consistency(self):
        """Test that identical claims produce identical hashes."""
        claims1 = [{"normalized": "candidate supports healthcare reform"}, {"normalized": "opposes tax increases"}]
        claims2 = [{"normalized": "opposes tax increases"}, {"normalized": "candidate supports healthcare reform"}]

        hash1 = hash_claims(claims1)
        hash2 = hash_claims(claims2)

        # Should be the same due to sorting
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hash length

    def test_ai_enrich_basic(self):
        """Test basic AI enrichment functionality."""
        content_text = """
        John Smith supports healthcare reform and opposes higher taxes. 
        He believes in expanding access to affordable healthcare for all Americans.
        Smith has proposed a comprehensive plan to reduce healthcare costs.
        """

        annotations = ai_enrich(content_text)

        assert isinstance(annotations, AIAnnotations)
        assert annotations.usefulness.get("score", 0.0) > 0.0
        assert len(annotations.index_summary) > 0

    def test_ai_enrich_with_metadata(self):
        """Test AI enrichment with metadata context."""
        content_text = "Healthcare reform is essential for our state."
        metadata = {"race_id": "test-race-2024", "source_url": "https://example.com"}

        annotations = ai_enrich(content_text, metadata)

        assert isinstance(annotations, AIAnnotations)
        assert "Healthcare" in annotations.issues

    def test_usefulness_scoring(self):
        """Test usefulness scoring for different content qualities."""
        # Very short content
        short_content = "Yes."
        short_annotations = ai_enrich(short_content)

        # Substantial content with issues
        substantial_content = """
        Healthcare reform is a top priority for our campaign. We support expanding 
        Medicare coverage to include dental and vision care. Our plan will reduce 
        prescription drug costs by allowing Medicare to negotiate prices directly 
        with pharmaceutical companies.
        """
        substantial_annotations = ai_enrich(substantial_content)

        assert short_annotations.usefulness.get("score", 0.0) < substantial_annotations.usefulness.get("score", 0.0)

    def test_issue_detection(self):
        """Test issue detection functionality."""
        healthcare_text = "We need comprehensive healthcare reform and better medical insurance."
        annotations = ai_enrich(healthcare_text)
        assert "Healthcare" in annotations.issues

        economy_text = "Creating jobs and improving the economy is our priority."
        annotations = ai_enrich(economy_text)
        assert "Economy" in annotations.issues

    def test_enrichment_error_handling(self):
        """Test that enrichment handles errors gracefully."""
        # Test with problematic input
        annotations = ai_enrich("")
        assert isinstance(annotations, AIAnnotations)
        assert annotations.usefulness.get("score", 0.0) >= 0.0


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Pipeline imports not available")
class TestEnrichedVectorDatabase:
    """Test vector database with AI enrichment integration."""

    @pytest.fixture
    def sample_content(self):
        """Create sample extracted content for testing."""
        source = Source(
            url="https://example.com/candidate-page",
            type=SourceType.WEBSITE,
            title="Candidate Policy Page",
            last_accessed=datetime.utcnow(),
        )

        return ExtractedContent(
            source=source,
            text="""
            John Smith strongly supports comprehensive healthcare reform. He believes 
            every American deserves access to affordable healthcare. Smith opposes 
            raising taxes on middle-class families and supports targeted tax relief 
            for working families. His healthcare plan includes expanding Medicare 
            coverage and reducing prescription drug costs.
            """,
            extraction_timestamp=datetime.utcnow(),
            word_count=50,
            language="en",
        )

    def test_content_enrichment_integration(self, sample_content):
        """Test that content gets properly enriched."""
        # This would test the full integration but requires running pipeline
        # For now, just test that enrichment produces valid output
        annotations = ai_enrich(sample_content.text)

        assert isinstance(annotations, AIAnnotations)
        assert len(annotations.issues) > 0
        assert annotations.usefulness.get("score", 0.0) > 0.35  # Should pass usefulness threshold


# Minimal test that can run without full pipeline dependencies
class TestBasicFunctionality:
    """Basic tests that can run without full pipeline setup."""

    def test_imports_structure(self):
        """Test that the module structure is correct."""
        # This will pass if the files were created correctly
        import os

        # Check that ai_enrichment.py exists
        ai_enrichment_path = Path(__file__).parent.parent / "pipeline" / "app" / "utils" / "ai_enrichment.py"
        assert ai_enrichment_path.exists()

        # Check that models.py was updated
        models_path = Path(__file__).parent.parent / "shared" / "models.py"
        assert models_path.exists()

        # Check that AIAnnotations was added to models
        with open(models_path, "r") as f:
            content = f.read()
            assert "class AIAnnotations" in content

    def test_file_structure(self):
        """Verify the correct files were created and modified."""
        pipeline_root = Path(__file__).parent.parent / "pipeline"

        # Check key files exist
        assert (pipeline_root / "app" / "utils" / "ai_enrichment.py").exists()
        assert (pipeline_root / "app" / "schema.py").exists()
        assert (pipeline_root / "app" / "step05_corpus" / "election_vector_database_manager.py").exists()

    def test_ai_enrichment_functionality(self):
        """Test AI enrichment functionality by loading module directly."""
        import importlib.util
        import sys

        # Load the module directly to avoid import path issues
        ai_enrichment_path = Path(__file__).parent.parent / "pipeline" / "app" / "utils" / "ai_enrichment.py"
        spec = importlib.util.spec_from_file_location("ai_enrichment", ai_enrichment_path)
        ai_module = importlib.util.module_from_spec(spec)
        sys.modules["ai_enrichment_test"] = ai_module
        spec.loader.exec_module(ai_module)

        # Test hash_claims function
        empty_hash = ai_module.hash_claims([])
        assert empty_hash == ""

        # Test with actual claims
        claims = [{"normalized": "candidate supports healthcare reform"}, {"normalized": "opposes tax increases"}]
        hash_result = ai_module.hash_claims(claims)
        assert len(hash_result) == 32  # MD5 hash length

        # Test ai_enrich function
        content_text = """
        John Smith supports healthcare reform and opposes higher taxes. 
        He believes in expanding access to affordable healthcare for all Americans.
        """
        annotations = ai_module.ai_enrich(content_text)

        # Check basic structure
        assert hasattr(annotations, "usefulness")
        assert hasattr(annotations, "issues")
        assert hasattr(annotations, "index_summary")
        assert annotations.usefulness.get("score", 0.0) > 0.0

        # Test that healthcare was detected
        assert "Healthcare" in annotations.issues
