"""Tests for the RaceMetadataService (fetch+extract, strict→fallback)."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from pipeline.app.schema import ConfidenceLevel, RaceMetadata
from pipeline.app.step01_metadata.race_metadata_service import RaceMetadataService
from shared.models import DiscoveredCandidate
from shared.state_constants import PRIMARY_DATE_BY_STATE, STATE_NAME


class TestRaceMetadataService:
    """Tests for the RaceMetadataService."""

    @pytest.fixture
    def race_metadata_service(self):
        """Create a RaceMetadataService instance for testing."""
        with patch("pipeline.app.step01_metadata.race_metadata_service.SearchUtils"), patch(
            "pipeline.app.step01_metadata.race_metadata_service.WebContentFetcher"
        ), patch("pipeline.app.step01_metadata.race_metadata_service.ContentExtractor"):
            service = RaceMetadataService()
            service.search_utils = AsyncMock()
            return service

    # ---------- parse / slug ----------

    def test_parse_race_id_standard_format(self, race_metadata_service):
        state, office, year, district, kind = race_metadata_service._parse_race_id("mo-senate-2024", trace_id="t")
        assert state == "MO"
        assert office == "senate"
        assert year == 2024
        assert district is None
        assert kind is None

    def test_parse_race_id_with_district(self, race_metadata_service):
        state, office, year, district, kind = race_metadata_service._parse_race_id("ny-house-03-2024", trace_id="t")
        assert state == "NY"
        assert office == "house"
        assert year == 2024
        assert district == "03"
        assert kind is None

    def test_parse_race_id_at_large_district(self, race_metadata_service):
        state, office, year, district, kind = race_metadata_service._parse_race_id("vt-house-al-2024", trace_id="t")
        assert state == "VT"
        assert office == "house"
        assert year == 2024
        assert district == "AL"
        assert kind is None

    def test_parse_race_id_primary(self, race_metadata_service):
        state, office, year, district, kind = race_metadata_service._parse_race_id("ga-senate-2026-primary", trace_id="t")
        assert state == "GA"
        assert office == "senate"
        assert year == 2026
        assert district is None
        assert kind == "primary"

    def test_parse_race_id_special_election(self, race_metadata_service):
        state, office, year, district, kind = race_metadata_service._parse_race_id("ny-house-03-2025-special", trace_id="t")
        assert state == "NY"
        assert office == "house"
        assert year == 2025
        assert district == "03"
        assert kind == "special"

    def test_parse_race_id_runoff(self, race_metadata_service):
        state, office, year, district, kind = race_metadata_service._parse_race_id(
            "tx-railroad-commissioner-2026-runoff", trace_id="t"
        )
        assert state == "TX"
        assert office == "railroad-commissioner"
        assert year == 2026
        assert district is None
        assert kind == "runoff"

    def test_parse_race_id_invalid_format(self, race_metadata_service):
        with pytest.raises(ValueError, match="Invalid race_id format"):
            race_metadata_service._parse_race_id("invalid-format", trace_id="t")

    def test_parse_race_id_invalid_state(self, race_metadata_service):
        with pytest.raises(ValueError, match="Invalid state code"):
            race_metadata_service._parse_race_id("zz-senate-2024", trace_id="t")

    def test_parse_race_id_invalid_year(self, race_metadata_service):
        with pytest.raises(ValueError, match="Invalid year"):
            race_metadata_service._parse_race_id("mo-senate-2019", trace_id="t")
        with pytest.raises(ValueError, match="Invalid year"):
            race_metadata_service._parse_race_id("mo-senate-2029", trace_id="t")

    # ---------- trust / normalize ----------

    def test_is_trusted_source_trusted_domains(self, race_metadata_service):
        assert race_metadata_service._is_trusted_source("https://ballotpedia.org/candidate")
        assert race_metadata_service._is_trusted_source("https://en.wikipedia.org/wiki/candidate")
        assert race_metadata_service._is_trusted_source("https://www.fec.gov/candidate")
        assert race_metadata_service._is_trusted_source("https://vote411.org/candidate")

    def test_is_trusted_source_prevents_domain_spoofing(self, race_metadata_service):
        assert not race_metadata_service._is_trusted_source("https://fec.gov.evil.com/candidate")
        assert not race_metadata_service._is_trusted_source("https://ballotpedia.org.malicious.com/candidate")
        assert not race_metadata_service._is_trusted_source("https://notballotpedia.org/candidate")

    def test_is_trusted_source_untrusted_domains(self, race_metadata_service):
        assert not race_metadata_service._is_trusted_source("https://example.com/candidate")
        assert not race_metadata_service._is_trusted_source("https://untrusted.org/candidate")

    def test_is_trusted_source_invalid_url(self, race_metadata_service):
        assert not race_metadata_service._is_trusted_source("not-a-url")
        assert not race_metadata_service._is_trusted_source("")

    def test_normalize_source_url(self, race_metadata_service):
        assert race_metadata_service._normalize_source_url("  HTTPS://EXAMPLE.COM/PATH  ") == "https://example.com/path"
        url_with_params = "https://example.com/page?utm_source=test&fbclid=123&id=real"
        assert race_metadata_service._normalize_source_url(url_with_params) == url_with_params

    # ---------- merge / dedupe ----------

    def test_merge_and_deduplicate_candidates_new_candidate(self, race_metadata_service):
        candidates = [DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"])]
        result = race_metadata_service._merge_and_deduplicate_structured_candidates(candidates, trace_id="t")
        assert len(result) == 1
        assert result[0].name == "John Doe"

    def test_merge_and_deduplicate_candidates_duplicate_prevention(self, race_metadata_service):
        candidates = [
            DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"]),
            DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://fec.gov/john"]),
        ]
        result = race_metadata_service._merge_and_deduplicate_structured_candidates(candidates, trace_id="t")
        assert len(result) == 1
        assert len(result[0].sources) == 2

    def test_merge_and_deduplicate_candidates_source_deduplication(self, race_metadata_service):
        candidates = [
            DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"]),
            DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"]),
        ]
        result = race_metadata_service._merge_and_deduplicate_structured_candidates(candidates, trace_id="t")
        assert len(result) == 1
        assert len(result[0].sources) == 1

    # ---------- confidence ----------

    def test_calculate_confidence_high(self, race_metadata_service):
        candidates = [
            DiscoveredCandidate(
                name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john", "https://fec.gov/john"]
            ),
            DiscoveredCandidate(name="Jane Smith", party="Republican", sources=["https://wikipedia.org/jane"]),
        ]
        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=False, trace_id="t")
        assert confidence == ConfidenceLevel.HIGH

    def test_calculate_confidence_high_with_gov_source(self, race_metadata_service):
        candidates = [
            DiscoveredCandidate(
                name="John Doe",
                party="Democratic",
                sources=["https://johnforcongress.gov/about", "https://ballotpedia.org/john"],
            )
        ]
        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=False, trace_id="t")
        assert confidence == ConfidenceLevel.HIGH

    def test_calculate_confidence_medium(self, race_metadata_service):
        candidates = [DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"])]
        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=False, trace_id="t")
        assert confidence == ConfidenceLevel.MEDIUM

    def test_calculate_confidence_medium_with_primary_date(self, race_metadata_service):
        candidates = [DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://example.com/john"])]
        confidence = race_metadata_service._calculate_confidence(candidates, have_primary_date=True, trace_id="t")
        assert confidence == ConfidenceLevel.MEDIUM

    def test_calculate_confidence_low(self, race_metadata_service):
        confidence = race_metadata_service._calculate_confidence([], have_primary_date=False, trace_id="t")
        assert confidence == ConfidenceLevel.LOW

    # ---------- office info / party mapping ----------

    def test_get_office_info_federal_senate(self, race_metadata_service):
        info = race_metadata_service._get_office_info("senate", trace_id="t")
        assert info["full_name"] == "U.S. Senate"
        assert info["race_type"] == "federal"
        assert info["term_years"] == 6

    def test_get_office_info_federal_house(self, race_metadata_service):
        info = race_metadata_service._get_office_info("house", trace_id="t")
        assert info["full_name"] == "U.S. House of Representatives"
        assert info["race_type"] == "federal"
        assert info["term_years"] == 2

    def test_get_office_info_state_governor(self, race_metadata_service):
        info = race_metadata_service._get_office_info("governor", trace_id="t")
        assert info["full_name"] == "Governor"
        assert info["race_type"] == "state"
        assert info["term_years"] == 4

    def test_get_office_info_unknown_office(self, race_metadata_service):
        info = race_metadata_service._get_office_info("mayor", trace_id="t")
        assert info["full_name"] == "Mayor"
        assert info["race_type"] == "unknown"

    def test_party_mapping_npp(self, race_metadata_service):
        assert race_metadata_service._normalize_party_name("NPP") == "No Party Preference"

    def test_party_mapping_standard_parties(self, race_metadata_service):
        assert race_metadata_service._normalize_party_name("D") == "Democratic"
        assert race_metadata_service._normalize_party_name("R") == "Republican"
        assert race_metadata_service._normalize_party_name("I") == "Independent"

    def test_party_mapping_unknown(self, race_metadata_service):
        assert race_metadata_service._normalize_party_name("XYZ") == "Xyz"
        assert race_metadata_service._normalize_party_name("libertarian") == "Libertarian"

    # ---------- end-to-end (mocked) ----------

    @pytest.mark.asyncio
    async def test_extract_race_metadata_basic_strict_success(self, race_metadata_service):
        """Strict path returns candidates; fallback is not invoked."""
        candidate = DiscoveredCandidate(name="John Doe", party="Democratic", sources=["https://ballotpedia.org/john"])
        with patch.object(race_metadata_service, "_discover_with_fetch_and_extract", side_effect=[[candidate]]) as spy:
            md = await race_metadata_service.extract_race_metadata("mo-senate-2024")
            assert isinstance(md, RaceMetadata)
            assert md.race_id == "mo-senate-2024"
            assert md.state == "MO"
            assert "John Doe" in md.discovered_candidates
            # Only one call (strict=True)
            spy.assert_called_once()
            args, kwargs = spy.call_args
            assert kwargs.get("strict") is True

    @pytest.mark.asyncio
    async def test_extract_race_metadata_fallback_triggered(self, race_metadata_service):
        """Strict returns none; fallback returns candidates."""
        candidate = DiscoveredCandidate(name="Jane Smith", party="Republican", sources=["https://wikipedia.org/jane"])
        with patch.object(
            race_metadata_service,
            "_discover_with_fetch_and_extract",
            side_effect=[[], [candidate]],
        ) as spy:
            md = await race_metadata_service.extract_race_metadata("ny-house-03-2025-special")
            assert isinstance(md, RaceMetadata)
            assert md.state == "NY"
            assert "Jane Smith" in md.discovered_candidates
            # Called twice: strict then fallback
            assert spy.call_count == 2
            assert spy.call_args_list[0].kwargs.get("strict") is True
            assert spy.call_args_list[1].kwargs.get("strict") is False

    @pytest.mark.asyncio
    async def test_extract_race_metadata_handles_errors(self, race_metadata_service):
        """If discovery blows up, we still get fallback metadata."""
        with patch.object(race_metadata_service, "_discover_with_fetch_and_extract", side_effect=Exception("boom")):
            md = await race_metadata_service.extract_race_metadata("mo-senate-2024")
            assert isinstance(md, RaceMetadata)
            assert md.confidence == ConfidenceLevel.LOW
            assert len(md.discovered_candidates) == 0

    # ---------- misc ----------

    def test_district_normalization(self, race_metadata_service):
        state, office, year, district, kind = race_metadata_service._parse_race_id("vt-house-al-2024", trace_id="t")
        assert district == "AL"
        state, office, year, district, kind = race_metadata_service._parse_race_id("ny-house-3-2024", trace_id="t")
        assert district == "03"
