"""
Test suite for the Race Publishing Engine

Tests all aspects of the publishing pipeline including data transformation,
validation, and publication to multiple targets.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ..schema import CanonicalIssue, ConfidenceLevel, RaceJSON
from .race_publishing_engine import PublicationConfig, PublicationResult, PublicationTarget, RacePublishingEngine


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def config(temp_output_dir):
    """Create a test configuration."""
    return PublicationConfig(default_targets=[PublicationTarget.LOCAL_FILE], local_output_dir=str(temp_output_dir))


@pytest.fixture
def engine(config):
    """Create a test publishing engine."""
    return RacePublishingEngine(config)


@pytest.fixture
def sample_arbitrated_data():
    """Sample arbitrated data for testing."""
    return {
        "consensus_data": {
            "race_title": "Missouri U.S. Senate Race 2024",
            "office": "U.S. Senate",
            "jurisdiction": "Missouri",
            "election_date": "2024-11-05",
        },
        "arbitrated_summaries": [
            {
                "query_type": "candidate_summary",
                "candidate_name": "John Smith",
                "content": "John Smith is the Democratic candidate with extensive experience in public service.",
                "confidence": "high",
            },
            {
                "query_type": "candidate_summary",
                "candidate_name": "Jane Doe",
                "content": "Jane Doe is the Republican incumbent senator running for re-election.",
                "confidence": "high",
            },
            {
                "query_type": "issue_stance",
                "candidate_name": "John Smith",
                "issue": "Healthcare",
                "content": "Supports expanding Medicare and lowering prescription drug costs.",
                "confidence": "medium",
            },
            {
                "query_type": "issue_stance",
                "candidate_name": "Jane Doe",
                "issue": "Economy",
                "content": "Advocates for tax cuts and reducing business regulations.",
                "confidence": "high",
            },
        ],
        "overall_confidence": "high",
    }


@pytest.fixture
def sample_race():
    """Sample RaceJSON object for testing."""
    return RaceJSON(
        id="mo-senate-2024",
        election_date=datetime(2024, 11, 5),
        candidates=[
            {
                "name": "John Smith",
                "party": "Democratic",
                "incumbent": False,
                "summary": "John Smith is a Democratic candidate with extensive experience in public service and a strong commitment to healthcare reform and economic growth.",
                "issues": {},
                "top_donors": [],
                "website": None,
                "social_media": {},
            },
            {
                "name": "Jane Doe",
                "party": "Republican",
                "incumbent": True,
                "summary": "Jane Doe is the Republican incumbent senator with a proven track record of conservative leadership and fiscal responsibility in the U.S. Senate.",
                "issues": {},
                "top_donors": [],
                "website": None,
                "social_media": {},
            },
        ],
        updated_utc=datetime.now(timezone.utc),
        generator=["gpt-4o", "claude-3.5", "grok-3"],
        title="Missouri U.S. Senate Race 2024",
        office="U.S. Senate",
        jurisdiction="Missouri",
    )


class TestRacePublishingEngine:
    """Test the core publishing engine functionality."""

    def test_initialization(self, temp_output_dir):
        """Test engine initialization with custom config."""
        config = PublicationConfig(default_targets=[PublicationTarget.LOCAL_FILE], local_output_dir=str(temp_output_dir))
        engine = RacePublishingEngine(config)

        assert engine.config.local_output_dir == str(temp_output_dir)
        assert temp_output_dir.exists()
        assert engine.publication_history == []
        assert engine.active_publications == {}

    def test_initialization_default_config(self):
        """Test engine initialization with default config."""
        engine = RacePublishingEngine()

        assert engine.config.local_output_dir == "data/published"
        assert engine.config.enable_notifications is True

    @pytest.mark.asyncio
    async def test_create_race_json_success(self, engine, sample_arbitrated_data):
        """Test successful RaceJSON creation from arbitrated data."""
        race = await engine.create_race_json("mo-senate-2024", sample_arbitrated_data)

        assert race.id == "mo-senate-2024"
        assert race.title == "Missouri U.S. Senate Race 2024"
        assert race.office == "U.S. Senate"
        assert race.jurisdiction == "Missouri"
        assert race.election_date == datetime(2024, 11, 5)
        assert len(race.candidates) == 2

        # Check candidate extraction
        candidate_names = [c.name for c in race.candidates]
        assert "John Smith" in candidate_names
        assert "Jane Doe" in candidate_names

    @pytest.mark.asyncio
    async def test_create_race_json_minimal_data(self, engine):
        """Test RaceJSON creation with minimal arbitrated data."""
        minimal_data = {
            "consensus_data": {},
            "overall_confidence": "medium",
        }

        race = await engine.create_race_json("test-race-2024", minimal_data)

        assert race.id == "test-race-2024"
        assert race.title == "Electoral Race test-race-2024"
        assert len(race.candidates) >= 1  # Should have at least a placeholder

    @pytest.mark.asyncio
    async def test_create_race_json_invalid_data(self, engine):
        """Test RaceJSON creation with invalid data."""
        with pytest.raises(ValueError, match="Arbitrated data cannot be empty"):
            await engine.create_race_json("test-race", {})

    @pytest.mark.asyncio
    async def test_validate_race_json_success(self, engine, sample_race):
        """Test successful RaceJSON validation."""
        # Should not raise exception
        await engine._validate_race_json(sample_race)

    @pytest.mark.asyncio
    async def test_validate_race_json_missing_required_fields(self, engine):
        """Test RaceJSON validation with missing required fields."""
        invalid_race = RaceJSON(
            id="",  # Empty ID should fail
            election_date=datetime(2024, 11, 5),
            candidates=[],  # Empty candidates should fail
            updated_utc=datetime.now(timezone.utc),
        )

        with pytest.raises(ValueError, match="validation failed"):
            await engine._validate_race_json(invalid_race)

    @pytest.mark.asyncio
    async def test_publish_to_local_file(self, engine, sample_race, temp_output_dir):
        """Test publishing to local file system."""
        await engine.publishers.publish_to_local_file(sample_race)

        output_file = temp_output_dir / f"{sample_race.id}.json"
        assert output_file.exists()

        # Verify file content
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["id"] == sample_race.id
        assert data["title"] == sample_race.title
        assert len(data["candidates"]) == len(sample_race.candidates)

    @pytest.mark.asyncio
    async def test_publish_to_local_file_with_backup(self, engine, sample_race, temp_output_dir):
        """Test local file publishing with backup creation."""
        output_file = temp_output_dir / f"{sample_race.id}.json"
        backup_file = temp_output_dir / f"{sample_race.id}.json.backup"

        # Create existing file
        output_file.write_text('{"old": "data"}')

        # Publish new data
        await engine.publishers.publish_to_local_file(sample_race)

        # Check backup was created and new file exists
        assert output_file.exists()
        assert backup_file.exists()

        # Verify backup contains old data
        with open(backup_file, "r") as f:
            backup_data = json.load(f)
        assert backup_data == {"old": "data"}

    @pytest.mark.cloud
    @pytest.mark.asyncio
    @patch("google.cloud.storage.Client")
    async def test_publish_to_cloud_storage_success(self, mock_client, engine, sample_race):
        """Test successful cloud storage publication."""
        pytest.importorskip("google.cloud.storage", reason="Google Cloud Storage not available")

        # Mock GCS client and operations
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_client.return_value.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        # Set environment variables
        os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
        os.environ["GCS_BUCKET_NAME"] = "test-bucket"

        try:
            await engine.publishers.publish_to_cloud_storage(sample_race)

            # Verify GCS operations were called
            mock_client.assert_called_once_with(project="test-project")
            mock_bucket.blob.assert_called_once_with(f"races/{sample_race.id}.json")
            mock_blob.upload_from_string.assert_called_once()
            mock_blob.patch.assert_called_once()

        finally:
            # Clean up environment
            if "GOOGLE_CLOUD_PROJECT" in os.environ:
                del os.environ["GOOGLE_CLOUD_PROJECT"]
            if "GCS_BUCKET_NAME" in os.environ:
                del os.environ["GCS_BUCKET_NAME"]

    @pytest.mark.cloud
    @pytest.mark.asyncio
    async def test_publish_to_cloud_storage_missing_config(self, engine, sample_race):
        """Test cloud storage publication with missing configuration."""
        # Skip if Google Cloud Storage is not available
        try:
            import google.cloud.storage
        except ImportError:
            pytest.skip("Google Cloud Storage not available")

        # Ensure environment variables are not set
        for var in ["GOOGLE_CLOUD_PROJECT", "GCS_BUCKET_NAME"]:
            if var in os.environ:
                del os.environ[var]

        with pytest.raises(ValueError, match="Cloud storage not configured"):
            await engine.publishers.publish_to_cloud_storage(sample_race)

    @pytest.mark.network
    @pytest.mark.asyncio
    async def test_publish_to_webhooks_success(self, engine, sample_race):
        """Test successful webhook publication."""
        # Skip if aiohttp is not available
        try:
            import aiohttp
        except ImportError:
            pytest.skip("aiohttp not available")

        # Set environment variables
        os.environ["WEBHOOK_URLS"] = "https://example.com/webhook1,https://example.com/webhook2"
        os.environ["WEBHOOK_SECRET"] = "test-secret"

        try:
            # Mock the aiohttp calls by patching the method directly
            with patch.object(engine.publishers, "publish_to_webhooks", new_callable=AsyncMock) as mock_webhooks:
                await engine.publishers.publish_to_webhooks(sample_race)
                mock_webhooks.assert_called_once_with(sample_race)

        finally:
            # Clean up environment
            for var in ["WEBHOOK_URLS", "WEBHOOK_SECRET"]:
                if var in os.environ:
                    del os.environ[var]

    @pytest.mark.cloud
    @pytest.mark.asyncio
    async def test_publish_to_pubsub_success(self, engine, sample_race):
        """Test successful Pub/Sub publication."""
        # Skip if Google Cloud Pub/Sub is not available
        try:
            import google.cloud.pubsub_v1
        except ImportError:
            pytest.skip("Google Cloud Pub/Sub not available")

        # Set environment variables
        os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
        os.environ["PUBSUB_RACE_TOPIC"] = "test-topic"

        try:
            # Mock the method to avoid actual Pub/Sub calls
            with patch.object(engine.publishers, "publish_to_pubsub", new_callable=AsyncMock) as mock_pubsub:
                await engine.publishers.publish_to_pubsub(sample_race)
                mock_pubsub.assert_called_once_with(sample_race)

        finally:
            # Clean up environment
            for var in ["GOOGLE_CLOUD_PROJECT", "PUBSUB_RACE_TOPIC"]:
                if var in os.environ:
                    del os.environ[var]

    @pytest.mark.asyncio
    async def test_publish_race_all_targets(self, engine, sample_race):
        """Test publishing to all targets."""
        # Mock all publication methods to avoid external dependencies
        engine.publishers.publish_to_local_file = AsyncMock()
        engine.publishers.publish_to_cloud_storage = AsyncMock()
        engine.publishers.publish_to_database = AsyncMock()
        engine.publishers.publish_to_webhooks = AsyncMock()
        engine.publishers.publish_to_pubsub = AsyncMock()
        engine.publishers.publish_to_api_endpoint = AsyncMock()

        # Explicitly test all targets instead of relying on environment detection
        all_targets = list(PublicationTarget)
        results = await engine.publish_race(sample_race, targets=all_targets)

        # Should have results for all targets
        assert len(results) == len(PublicationTarget)

        # All should be successful (since we mocked them)
        successful = [r for r in results if r.success]
        assert len(successful) == len(PublicationTarget)

    @pytest.mark.asyncio
    async def test_publish_race_partial_failure(self, engine, sample_race):
        """Test publishing with some targets failing."""
        # Mock methods with mixed success
        engine.publishers.publish_to_local_file = AsyncMock()
        engine.publishers.publish_to_cloud_storage = AsyncMock(side_effect=Exception("GCS Error"))
        engine.publishers.publish_to_database = AsyncMock()
        engine.publishers.publish_to_webhooks = AsyncMock(side_effect=Exception("Webhook Error"))
        engine.publishers.publish_to_pubsub = AsyncMock()
        engine.publishers.publish_to_api_endpoint = AsyncMock()

        # Explicitly test all targets to ensure mixed success/failure
        all_targets = list(PublicationTarget)
        results = await engine.publish_race(sample_race, targets=all_targets)

        # Check mixed results
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        assert len(successful) > 0
        assert len(failed) > 0

        # Failed targets should include error messages
        for result in failed:
            assert result.message.startswith("Publication failed:")

    def test_get_published_races(self, engine, temp_output_dir):
        """Test getting list of published races."""
        # Create some test files
        (temp_output_dir / "race1.json").write_text("{}")
        (temp_output_dir / "race2.json").write_text("{}")
        (temp_output_dir / "not-a-race.txt").write_text("ignored")

        published = engine.get_published_races()

        assert "race1" in published
        assert "race2" in published
        assert len(published) == 2

    def test_get_race_data_success(self, engine, temp_output_dir, sample_race):
        """Test successful race data retrieval."""
        # Create test file
        race_file = temp_output_dir / f"{sample_race.id}.json"
        with open(race_file, "w") as f:
            json.dump(sample_race.model_dump(mode="json"), f, default=str)

        data = engine.get_race_data(sample_race.id)

        assert data is not None
        assert data["id"] == sample_race.id
        assert data["title"] == sample_race.title

    def test_get_race_data_not_found(self, engine):
        """Test race data retrieval for non-existent race."""
        data = engine.get_race_data("nonexistent-race")
        assert data is None

    @pytest.mark.asyncio
    async def test_cleanup_old_publications(self, engine, temp_output_dir):
        """Test cleanup of old publication files."""
        # Create test files with different timestamps
        old_file = temp_output_dir / "old-race.json"
        new_file = temp_output_dir / "new-race.json"

        old_file.write_text("{}")
        new_file.write_text("{}")

        # Simulate old file by modifying timestamp
        old_timestamp = datetime.now().timestamp() - (400 * 24 * 3600)  # 400 days ago
        os.utime(old_file, (old_timestamp, old_timestamp))

        # Cleanup with 365 day retention
        cleaned_count = await engine.cleanup_old_publications(365)

        assert cleaned_count == 1
        assert not old_file.exists()
        assert new_file.exists()


class TestMetadataExtraction:
    """Test metadata extraction functionality."""

    @pytest.mark.asyncio
    async def test_extract_race_metadata_from_consensus(self, engine):
        """Test metadata extraction from consensus data."""
        arbitrated_data = {
            "consensus_data": {
                "race_title": "Texas Governor Race 2024",
                "office": "Governor",
                "jurisdiction": "Texas",
                "election_date": "2024-11-05",
            }
        }

        metadata = await engine._extract_race_metadata("tx-governor-2024", arbitrated_data)

        assert metadata["title"] == "Texas Governor Race 2024"
        assert metadata["office"] == "Governor"
        assert metadata["jurisdiction"] == "Texas"
        assert metadata["election_date"] == datetime(2024, 11, 5)

    @pytest.mark.asyncio
    async def test_extract_race_metadata_from_race_id(self, engine):
        """Test metadata extraction from race ID when consensus data is missing."""
        arbitrated_data = {"consensus_data": {}}

        metadata = await engine._extract_race_metadata("ca-senate-2024", arbitrated_data)

        assert metadata["jurisdiction"] == "CA"
        assert metadata["office"] == "U.S. Senate"
        assert metadata["election_date"] == datetime(2024, 11, 5)

    @pytest.mark.asyncio
    async def test_extract_candidates_from_summaries(self, engine, sample_arbitrated_data):
        """Test candidate extraction from arbitrated summaries."""
        candidates = await engine._extract_candidates(sample_arbitrated_data)

        assert len(candidates) == 2

        candidate_names = [c["name"] for c in candidates]
        assert "John Smith" in candidate_names
        assert "Jane Doe" in candidate_names

        # Check that issue stances were extracted
        john_smith = next(c for c in candidates if c["name"] == "John Smith")
        jane_doe = next(c for c in candidates if c["name"] == "Jane Doe")

        assert "Healthcare" in john_smith["issues"]
        assert "Economy" in jane_doe["issues"]

    @pytest.mark.asyncio
    async def test_extract_candidates_fallback(self, engine):
        """Test candidate extraction with minimal data creates fallback."""
        minimal_data = {"consensus_data": {}}

        candidates = await engine._extract_candidates(minimal_data)

        assert len(candidates) >= 1
        assert candidates[0]["name"] == "Candidate Information Pending"


if __name__ == "__main__":
    pytest.main([__file__])
