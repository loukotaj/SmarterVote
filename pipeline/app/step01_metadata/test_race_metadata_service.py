"""Tests for the simplified RaceMetadataService."""

import pytest

from pipeline.app.step01_metadata.race_metadata_service import RaceMetadataService


class TestRaceMetadataService:
    @pytest.fixture
    def svc(self):
        return RaceMetadataService()

    def test_parse_race_id_standard_format(self, svc):
        state, office, year, district, kind = svc._parse_race_id("mo-senate-2024", trace_id="t")
        assert state == "MO"
        assert office == "senate"
        assert year == 2024
        assert district is None
        assert kind is None

    def test_parse_race_id_with_district(self, svc):
        state, office, year, district, kind = svc._parse_race_id("ny-house-03-2024", trace_id="t")
        assert state == "NY"
        assert office == "house"
        assert year == 2024
        assert district == "03"
        assert kind is None

    def test_parse_race_id_at_large_district(self, svc):
        state, office, year, district, kind = svc._parse_race_id("vt-house-al-2024", trace_id="t")
        assert district == "AL"

    def test_parse_race_id_primary(self, svc):
        state, office, year, district, kind = svc._parse_race_id("ga-senate-2026-primary", trace_id="t")
        assert kind == "primary"

    def test_parse_race_id_special_election(self, svc):
        state, office, year, district, kind = svc._parse_race_id("ny-house-03-2025-special", trace_id="t")
        assert kind == "special"

    def test_parse_race_id_runoff(self, svc):
        state, office, year, district, kind = svc._parse_race_id("tx-railroad-commissioner-2026-runoff", trace_id="t")
        assert kind == "runoff"

    def test_parse_race_id_invalid_format(self, svc):
        with pytest.raises(ValueError):
            svc._parse_race_id("invalid-format", trace_id="t")

    def test_district_normalization(self, svc):
        state, office, year, district, kind = svc._parse_race_id("ny-house-3-2024", trace_id="t")
        assert district == "03"
