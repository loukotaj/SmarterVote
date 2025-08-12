"""Tests for the RaceMetadataService."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlparse

import pytest

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.models import ConfidenceLevel, DiscoveredCandidate
from shared.state_constants import PRIMARY_DATE_BY_STATE, STATE_NAME

from pipeline.app.schema import RaceMetadata, Source, SourceType
from pipeline.app.step01_metadata.race_metadata_service import RaceMetadataService


class TestRaceMetadataService:
    """Tests for the RaceMetadataService."""

    @pytest.fixture
    def race_metadata_service(self):
        """Create a RaceMetadataService instance for testing."""
        with patch("pipeline.app.step01_metadata.race_metadata_service.SearchUtils"):
            service = RaceMetadataService()
            service.search_utils = AsyncMock()
            return service

    def test_parse_race_id_standard_format(self, race_metadata_service):
        """Test parsing standard race ID format."""
        state, office, year, district, kind = race_metadata_service._parse_race_id("mo-senate-2024")

        assert state == "MO"
        assert office == "senate"
        assert year == 2024
        assert district is None
        assert kind is None

    def test_parse_race_id_with_district(self, race_metadata_service):
        """Test parsing race ID with district."""
        state, office, year, district, kind = race_metadata_service._parse_race_id("ny-house-03-2024")

        assert state == "NY"
        assert office == "house"
        assert year == 2024
        assert district == "03"
        assert kind is None

    def test_parse_race_id_at_large_district(self, race_metadata_service):
        """Test parsing race ID with at-large district."""
        state, office, year, district, kind = race_metadata_service._parse_race_id("vt-house-al-2024")

        assert state == "VT"
        assert office == "house"
        assert year == 2024
        assert district == "AL"
        assert kind is None

    def test_parse_race_id_primary(self, race_metadata_service):
        """Test parsing race ID with primary suffix."""
        state, office, year, district, kind = race_metadata_service._parse_race_id("ga-senate-2026-primary")

        assert state == "GA"
        assert office == "senate"
        assert year == 2026
        assert district is None
        assert kind == "primary"

    def test_parse_race_id_special_election(self, race_metadata_service):
        """Test parsing race ID for special election."""
        state, office, year, district, kind = race_metadata_service._parse_race_id("ny-house-03-2025-special")

        assert state == "NY"
        assert office == "house"
        assert year == 2025
        assert district == "03"
        assert kind == "special"

    def test_parse_race_id_runoff(self, race_metadata_service):
        """Test parsing race ID for runoff."""
        state, office, year, district, kind = race_metadata_service._parse_race_id("tx-railroad-commissioner-2026-runoff")

        assert state == "TX"
        assert office == "railroad-commissioner"
        assert year == 2026
        assert district is None
        assert kind == "runoff"

    def test_parse_race_id_invalid_format(self, race_metadata_service):
        """Test parsing invalid race ID format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid race_id format"):
            race_metadata_service._parse_race_id("invalid-format")

    def test_parse_race_id_invalid_state(self, race_metadata_service):
        """Test parsing race ID with invalid state code raises ValueError."""
        with pytest.raises(ValueError, match="Invalid state code"):
            race_metadata_service._parse_race_id("zz-senate-2024")

    def test_parse_race_id_invalid_year(self, race_metadata_service):
        """Test parsing race ID with invalid year raises ValueError."""
        with pytest.raises(ValueError, match="Invalid year"):
            race_metadata_service._parse_race_id("mo-senate-2019")  # Too old

        with pytest.raises(ValueError, match="Invalid year"):
            race_metadata_service._parse_race_id("mo-senate-2029")  # Too far in future

    def test_is_trusted_source_trusted_domains(self, race_metadata_service):
        """Test trusted source validation for known domains."""
        assert race_metadata_service._is_trusted_source("https://ballotpedia.org/candidate")
        assert race_metadata_service._is_trusted_source("https://en.wikipedia.org/wiki/candidate")
        assert race_metadata_service._is_trusted_source("https://www.fec.gov/candidate")
        assert race_metadata_service._is_trusted_source("https://vote411.org/candidate")

    def test_is_trusted_source_prevents_domain_spoofing(self, race_metadata_service):
        """Test trusted source validation prevents domain spoofing attacks."""
        # These should NOT be trusted (domain spoofing attempts)
        assert not race_metadata_service._is_trusted_source("https://fec.gov.evil.com/candidate")
        assert not race_metadata_service._is_trusted_source("https://ballotpedia.org.malicious.com/candidate")
        assert not race_metadata_service._is_trusted_source("https://notballotpedia.org/candidate")

    def test_is_trusted_source_untrusted_domains(self, race_metadata_service):
        """Test trusted source validation for untrusted domains."""
        assert not race_metadata_service._is_trusted_source("https://example.com/candidate")
        assert not race_metadata_service._is_trusted_source("https://untrusted.org/candidate")

    def test_is_trusted_source_invalid_url(self, race_metadata_service):
        """Test trusted source validation with invalid URL."""
        assert not race_metadata_service._is_trusted_source("not-a-url")
        assert not race_metadata_service._is_trusted_source("")

    def test_normalize_source_url(self, race_metadata_service):
        """Test URL normalization."""
        # Test basic normalization
        assert race_metadata_service._normalize_source_url("  HTTPS://EXAMPLE.COM/PATH  ") == "https://example.com/path"

        # Test parameter removal
        url_with_params = "https://example.com/page?utm_source=test&fbclid=123&id=real"
        normalized = race_metadata_service._normalize_source_url(url_with_params)
        assert "utm_source" not in normalized
        assert "fbclid" not in normalized
        assert "id=real" in normalized  # Should keep non-tracking params

    def test_merge_candidates_new_candidate(self, race_metadata_service):
        """Test merging candidates when candidate is new."""
        existing_candidates = []
        new_candidate = DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"])

        race_metadata_service._merge_candidates(existing_candidates, new_candidate)

        assert len(existing_candidates) == 1
        assert existing_candidates[0].name == "John Doe"

    def test_merge_candidates_duplicate_prevention(self, race_metadata_service):
        """Test merging candidates prevents duplicates."""
        existing_candidate = DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"])
        existing_candidates = [existing_candidate]

        # Try to add the same candidate
        new_candidate = DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://fec.gov/john"])

        race_metadata_service._merge_candidates(existing_candidates, new_candidate)

        # Should still be only one candidate but with merged sources
        assert len(existing_candidates) == 1
        assert len(existing_candidates[0].sources) == 2

    def test_merge_candidates_source_deduplication(self, race_metadata_service):
        """Test that source deduplication works efficiently."""
        existing_candidate = DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"])
        existing_candidates = [existing_candidate]

        # Add the same source again
        new_candidate = DiscoveredCandidate(
            name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"]  # Duplicate
        )

        race_metadata_service._merge_candidates(existing_candidates, new_candidate)

        # Should still be only one source
        assert len(existing_candidates[0].sources) == 1

    def test_calculate_confidence_high(self, race_metadata_service):
        """Test confidence calculation for HIGH confidence scenario."""
        candidates = [
            DiscoveredCandidate(
                name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john", "https://fec.gov/john"]
            ),
            DiscoveredCandidate(name="Jane Smith", party="Republican", sources=["https://wikipedia.org/jane"]),
        ]

        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=False)
        assert confidence == ConfidenceLevel.HIGH

    def test_calculate_confidence_high_with_gov_source(self, race_metadata_service):
        """Test confidence calculation gets HIGH with .gov source + trusted source."""
        candidates = [
            DiscoveredCandidate(
                name="John Doe",
                party="Democratic",
                sources=["https://johnforcongress.gov/about", "https://ballotpedia.org/john"],
            )
        ]

        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=False)
        assert confidence == ConfidenceLevel.HIGH

    def test_calculate_confidence_medium(self, race_metadata_service):
        """Test confidence calculation for MEDIUM confidence scenario."""
        candidates = [DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"])]

        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=False)
        assert confidence == ConfidenceLevel.MEDIUM

    def test_calculate_confidence_medium_with_primary_date(self, race_metadata_service):
        """Test confidence calculation gets MEDIUM with primary date but no trusted sources."""
        candidates = [DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://example.com/john"])]

        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=True)
        assert confidence == ConfidenceLevel.MEDIUM

    def test_calculate_confidence_low(self, race_metadata_service):
        """Test confidence calculation for LOW confidence scenario."""
        candidates = []

        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=False)
        assert confidence == ConfidenceLevel.LOW

    def test_get_office_info_federal_senate(self, race_metadata_service):
        """Test office info extraction for federal senate race."""
        info = race_metadata_service._get_office_info("senate", None)

        assert info["office_type"] == "senate"
        assert info["office_level"] == "federal"
        assert info["is_federal"] is True
        assert info["is_state"] is False
        assert info["is_local"] is False

    def test_get_office_info_federal_house(self, race_metadata_service):
        """Test office info extraction for federal house race."""
        info = race_metadata_service._get_office_info("house", "03")

        assert info["office_type"] == "house"
        assert info["office_level"] == "federal"
        assert info["district"] == "03"
        assert info["is_federal"] is True

    def test_get_office_info_state_governor(self, race_metadata_service):
        """Test office info extraction for state governor race."""
        info = race_metadata_service._get_office_info("governor", None)

        assert info["office_type"] == "governor"
        assert info["office_level"] == "state"
        assert info["is_state"] is True
        assert info["is_federal"] is False

    def test_get_office_info_local_mayor(self, race_metadata_service):
        """Test office info extraction for local mayor race."""
        info = race_metadata_service._get_office_info("mayor", None)

        assert info["office_type"] == "mayor"
        assert info["office_level"] == "local"
        assert info["is_local"] is True

    def test_party_mapping_npp(self, race_metadata_service):
        """Test NPP party mapping to 'No Party Preference'."""
        mapped = race_metadata_service._map_party_name("NPP")
        assert mapped == "No Party Preference"

    def test_party_mapping_standard_parties(self, race_metadata_service):
        """Test standard party name mappings."""
        assert race_metadata_service._map_party_name("D") == "Democratic"
        assert race_metadata_service._map_party_name("R") == "Republican"
        assert race_metadata_service._map_party_name("I") == "Independent"

    def test_party_mapping_unknown(self, race_metadata_service):
        """Test unknown party mapping."""
        assert race_metadata_service._map_party_name("XYZ") == "XYZ"

    @pytest.mark.asyncio
    async def test_extract_race_metadata_basic(self, race_metadata_service):
        """Test basic race metadata extraction."""
        # Mock search results
        race_metadata_service.search_utils.search_general.return_value = [
            Source(
                url="https://ballotpedia.org/mo-senate-2024",
                type=SourceType.WEBSITE,
                title="Missouri Senate Election 2024",
                last_accessed=datetime.utcnow(),
            )
        ]

        # Mock candidate extraction
        with patch.object(race_metadata_service, "_extract_candidates_from_content") as mock_extract:
            mock_extract.return_value = [
                DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"])
            ]

            metadata = await race_metadata_service.extract_race_metadata("mo-senate-2024")

            assert isinstance(metadata, RaceMetadata)
            assert metadata.race_id == "mo-senate-2024"
            assert metadata.state == "MO"
            assert metadata.office_type == "senate"
            assert metadata.year == 2024
            assert len(metadata.candidates) == 1
            assert metadata.confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW]

    @pytest.mark.asyncio
    async def test_extract_race_metadata_handles_errors(self, race_metadata_service):
        """Test race metadata extraction handles errors gracefully."""
        # Mock search to raise an exception
        race_metadata_service.search_utils.search_general.side_effect = Exception("Search failed")

        metadata = await race_metadata_service.extract_race_metadata("mo-senate-2024")

        # Should still return valid metadata with low confidence
        assert isinstance(metadata, RaceMetadata)
        assert metadata.confidence == ConfidenceLevel.LOW
        assert len(metadata.candidates) == 0

    def test_district_normalization(self, race_metadata_service):
        """Test district normalization for at-large districts."""
        # Test lowercase 'al' gets normalized to uppercase 'AL'
        state, office, year, district, kind = race_metadata_service._parse_race_id("vt-house-al-2024")
        assert district == "AL"

        # Test numeric districts get zero-padded
        state, office, year, district, kind = race_metadata_service._parse_race_id("ny-house-3-2024")
        assert district == "03"
