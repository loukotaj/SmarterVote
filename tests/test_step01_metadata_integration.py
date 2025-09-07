"""
Integration test for step01_metadata that produces packaged output for step02 testing.

This test focuses on a single, powerful, flexible test of step01_metadata that:
1. Can accept custom input parameters (race_id, mock responses, etc.)
2. Runs the actual metadata extraction logic
3. Packages the output in a standardized format for easy use by step02 tests
4. Provides validation and debugging capabilities
"""

import pytest

# Skip this integration test in environments without the full metadata service
# TODO: Enable when full metadata service and external APIs are available
pytest.skip(
    "step01 metadata integration requires full service and external APIs",
    allow_module_level=True,
)

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.app.step01_ingest.MetaDataService.race_metadata_service import RaceMetadataService
from shared.models import ConfidenceLevel, DiscoveredCandidate, RaceMetadata


class Step01TestOutput:
    """Standardized output package for step01 tests."""

    def __init__(self, race_metadata: RaceMetadata, raw_input: Dict[str, Any], processing_info: Dict[str, Any]):
        self.race_metadata = race_metadata
        self.raw_input = raw_input
        self.processing_info = processing_info

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for easy inspection or JSON serialization."""
        return {
            "race_metadata": self.race_metadata.dict(),
            "raw_input": self.raw_input,
            "processing_info": self.processing_info,
        }

    def save_to_file(self, filepath: str):
        """Save the output package to a JSON file for debugging."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    def get_for_step02(self) -> RaceMetadata:
        """Get the RaceMetadata object ready for step02 input."""
        return self.race_metadata


class TestStep01Integration:
    """Integration test for step01_metadata extraction."""

    @pytest.fixture
    def mock_search_responses(self):
        """Default mock search responses for common test scenarios."""
        return {
            "ballotpedia_response": [
                {
                    "title": "2024 Missouri U.S. Senate election - Ballotpedia",
                    "url": "https://ballotpedia.org/Missouri_U.S._Senate_election",
                    "snippet": "Republican Josh Hawley (incumbent) vs Democrat Lucas Kunce running for Missouri Senate in 2024.",
                }
            ],
            "general_response": [
                {
                    "title": "Missouri Senate Race 2024 - Wikipedia",
                    "url": "https://en.wikipedia.org/wiki/2024_Missouri_Senate",
                    "snippet": "Josh Hawley seeks re-election as Republican incumbent against Democratic challenger Lucas Kunce.",
                }
            ],
        }

    @pytest.fixture
    def default_discovered_candidates(self):
        """Default discovered candidates for testing."""
        return [
            DiscoveredCandidate(
                name="Josh Hawley",
                party="Republican",
                incumbent=True,
                sources=["https://ballotpedia.org/Missouri_U.S._Senate_election"],
            ),
            DiscoveredCandidate(
                name="Lucas Kunce",
                party="Democratic",
                incumbent=False,
                sources=["https://ballotpedia.org/Missouri_U.S._Senate_election"],
            ),
        ]

    async def run_step01_test(
        self,
        race_id: str,
        mock_search_responses: Optional[Dict[str, Any]] = None,
        mock_discovered_candidates: Optional[List[DiscoveredCandidate]] = None,
        expected_confidence: Optional[ConfidenceLevel] = None,
        save_output_file: Optional[str] = None,
    ) -> Step01TestOutput:
        """
        Run a flexible step01 metadata extraction test.

        Args:
            race_id: The race identifier to test (e.g., "mo-senate-2024")
            mock_search_responses: Optional custom search responses
            mock_discovered_candidates: Optional custom candidate list
            expected_confidence: Expected confidence level for validation
            save_output_file: Optional file path to save test output

        Returns:
            Step01TestOutput: Packaged output ready for step02 testing
        """
        # Track processing info for debugging
        processing_info = {"start_time": datetime.utcnow(), "race_id": race_id, "mocked_components": [], "actual_calls": []}

        # Use provided mocks or defaults
        if mock_search_responses is None:
            mock_search_responses = {
                "ballotpedia_response": [{"title": f"Mock result for {race_id}", "url": "https://ballotpedia.org/test"}],
                "general_response": [{"title": f"Mock general result for {race_id}", "url": "https://wikipedia.org/test"}],
            }

        if mock_discovered_candidates is None:
            mock_discovered_candidates = [
                DiscoveredCandidate(name="Test Candidate 1", party="Republican", incumbent=True, sources=["test-source"]),
                DiscoveredCandidate(name="Test Candidate 2", party="Democratic", incumbent=False, sources=["test-source"]),
            ]

        # Set up the service with mocked dependencies
        with patch("pipeline.app.step01_metadata.race_metadata_service.SearchUtils") as mock_search_utils_class:
            # Create mock search utils instance
            mock_search_utils = AsyncMock()
            mock_search_utils_class.return_value = mock_search_utils

            # Mock the search method to return our test responses
            async def mock_search(*args, **kwargs):
                processing_info["actual_calls"].append({"method": "search", "args": args, "kwargs": kwargs})
                # Return first available response
                for response_key, response_data in mock_search_responses.items():
                    if response_data:
                        return response_data
                return []

            mock_search_utils.search = mock_search
            processing_info["mocked_components"].append("SearchUtils")

            # Create the service
            service = RaceMetadataService()

            # Mock the candidate discovery method to return our test candidates
            async def mock_discover_candidates(*args, **kwargs):
                processing_info["actual_calls"].append(
                    {"method": "_discover_candidates_via_reliable_sources", "args": args, "kwargs": kwargs}
                )
                return mock_discovered_candidates

            service._discover_candidates_via_reliable_sources = mock_discover_candidates
            processing_info["mocked_components"].append("_discover_candidates_via_reliable_sources")

            # Run the actual metadata extraction
            race_metadata = await service.extract_race_metadata(race_id)

            processing_info["end_time"] = datetime.utcnow()
            processing_info["processing_duration"] = (
                processing_info["end_time"] - processing_info["start_time"]
            ).total_seconds()

            # Validate results if expected confidence provided
            if expected_confidence:
                assert (
                    race_metadata.confidence == expected_confidence
                ), f"Expected confidence {expected_confidence}, got {race_metadata.confidence}"

            # Package the output
            raw_input = {
                "race_id": race_id,
                "mock_search_responses": mock_search_responses,
                "mock_discovered_candidates": [c.dict() for c in mock_discovered_candidates],
                "expected_confidence": expected_confidence.value if expected_confidence else None,
            }

            output = Step01TestOutput(race_metadata=race_metadata, raw_input=raw_input, processing_info=processing_info)

            # Save output file if requested
            if save_output_file:
                output.save_to_file(save_output_file)
                processing_info["saved_to"] = save_output_file

            return output

    @pytest.mark.asyncio
    async def test_mo_senate_2024_standard_case(self, mock_search_responses, default_discovered_candidates):
        """Test standard Missouri Senate 2024 race."""
        output = await self.run_step01_test(
            race_id="mo-senate-2024",
            mock_search_responses=mock_search_responses,
            mock_discovered_candidates=default_discovered_candidates,
            expected_confidence=ConfidenceLevel.MEDIUM,
        )

        # Validate core metadata
        metadata = output.race_metadata
        assert metadata.race_id == "mo-senate-2024"
        assert metadata.state == "MO"
        assert metadata.office_type == "senate"
        assert metadata.year == 2024
        assert metadata.full_office_name == "U.S. Senate"
        assert metadata.race_type == "federal"
        assert not metadata.is_primary
        assert not metadata.is_special_election

        # Validate candidates
        assert len(metadata.structured_candidates) == 2
        assert metadata.discovered_candidates == ["Josh Hawley", "Lucas Kunce"]
        assert metadata.incumbent_party == "Republican"

        # Validate search optimization hints
        assert "Healthcare" in metadata.major_issues
        assert "Economy" in metadata.major_issues
        assert "Missouri" in metadata.geographic_keywords

        print(f"✅ Test passed - Race metadata extracted with {metadata.confidence.value} confidence")
        print(f"   Found {len(metadata.structured_candidates)} candidates: {metadata.discovered_candidates}")

    @pytest.mark.asyncio
    async def test_basic_metadata_extraction(self):
        """Basic test without confidence expectations - just validate core functionality."""
        output = await self.run_step01_test(race_id="mo-senate-2024")

        metadata = output.race_metadata
        assert metadata.race_id == "mo-senate-2024"
        assert metadata.state == "MO"
        assert metadata.office_type == "senate"
        assert metadata.year == 2024
        assert metadata.full_office_name == "U.S. Senate"
        assert metadata.race_type == "federal"

        # Should have some candidates
        assert len(metadata.structured_candidates) >= 1
        assert len(metadata.discovered_candidates) >= 1

        print(
            f"✅ Basic test passed - Extracted {len(metadata.structured_candidates)} candidates with {metadata.confidence.value} confidence"
        )

    @pytest.mark.asyncio
    async def test_ny_house_03_2024_primary(self):
        """Test NY House District 3 primary race."""
        primary_candidates = [
            DiscoveredCandidate(name="Tom Suozzi", party="Democratic", incumbent=False, sources=["test"]),
            DiscoveredCandidate(name="Mike LaLota", party="Republican", incumbent=True, sources=["test"]),
        ]

        output = await self.run_step01_test(
            race_id="ny-house-03-2024-primary",
            mock_discovered_candidates=primary_candidates,
            expected_confidence=ConfidenceLevel.MEDIUM,
        )

        metadata = output.race_metadata
        assert metadata.race_id == "ny-house-03-2024-primary"
        assert metadata.state == "NY"
        assert metadata.office_type == "house"
        assert metadata.district == "03"
        assert metadata.is_primary == True
        assert metadata.full_office_name == "U.S. House of Representatives"
        assert metadata.race_type == "federal"

        print(f"✅ Primary test passed - {metadata.jurisdiction} with {len(metadata.structured_candidates)} candidates")

    @pytest.mark.asyncio
    async def test_custom_race_with_output_file(self, tmp_path):
        """Test with custom parameters and output file saving."""
        # Create custom test data
        custom_candidates = [
            DiscoveredCandidate(name="Custom Candidate A", party="Independent", incumbent=False, sources=["custom-source"]),
            DiscoveredCandidate(name="Custom Candidate B", party="Green", incumbent=False, sources=["custom-source"]),
        ]

        custom_search_responses = {
            "custom_response": [
                {"title": "Custom Test Result", "url": "https://example.com/custom", "snippet": "Custom test snippet"}
            ]
        }

        output_file = tmp_path / "test_output.json"

        output = await self.run_step01_test(
            race_id="ca-governor-2026",
            mock_search_responses=custom_search_responses,
            mock_discovered_candidates=custom_candidates,
            save_output_file=str(output_file),
        )

        # Validate output file was created
        assert output_file.exists()

        # Validate content
        with open(output_file) as f:
            saved_data = json.load(f)

        assert saved_data["race_metadata"]["race_id"] == "ca-governor-2026"
        assert saved_data["race_metadata"]["state"] == "CA"
        assert saved_data["race_metadata"]["office_type"] == "governor"
        assert len(saved_data["race_metadata"]["structured_candidates"]) == 2

        print(f"✅ Custom test passed - Output saved to {output_file}")
        print(f"   Processing took {output.processing_info['processing_duration']:.3f} seconds")

        # Return the output for potential use by step02 tests
        return output.get_for_step02()


# Utility function for step02 tests to easily get step01 output
async def get_step01_output_for_step02(
    race_id: str, custom_candidates: Optional[List[DiscoveredCandidate]] = None
) -> RaceMetadata:
    """
    Utility function for step02 tests to easily get step01 output.

    Args:
        race_id: Race identifier
        custom_candidates: Optional custom candidate list

    Returns:
        RaceMetadata ready for step02 input
    """
    test_instance = TestStep01Integration()
    output = await test_instance.run_step01_test(race_id=race_id, mock_discovered_candidates=custom_candidates)
    return output.get_for_step02()


if __name__ == "__main__":
    # Example usage for debugging
    import asyncio

    async def debug_run():
        test = TestStep01Integration()
        output = await test.run_step01_test(race_id="mo-senate-2024", save_output_file="debug_step01_output.json")
        print("Debug run completed. Check debug_step01_output.json for details.")
        return output

    asyncio.run(debug_run())
