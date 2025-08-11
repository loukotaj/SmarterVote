#!/usr/bin/env python3
"""
Manual test script to demonstrate the new meta data engine features:
1. DiscoveredCandidate structured data
2. Race type detection from slugs
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from shared.models import DiscoveredCandidate, RaceMetadata
from pydantic import HttpUrl
from datetime import datetime
import re


def test_discovered_candidate_model():
    """Test the new DiscoveredCandidate model."""
    print("=== Testing DiscoveredCandidate Model ===")
    
    # Create candidates with different levels of information
    candidates = [
        DiscoveredCandidate(
            name="John Smith",
            party="Democratic", 
            incumbent=True,
            sources=[HttpUrl("https://ballotpedia.org/john-smith")]
        ),
        DiscoveredCandidate(
            name="Jane Doe",
            party="Republican",
            incumbent=False,
            sources=[
                HttpUrl("https://ballotpedia.org/jane-doe"),
                HttpUrl("https://wikipedia.org/jane-doe")
            ]
        ),
        DiscoveredCandidate(
            name="Bob Wilson"  # Only name, other fields default
        )
    ]
    
    for i, candidate in enumerate(candidates, 1):
        print(f"Candidate {i}:")
        print(f"  Name: {candidate.name}")
        print(f"  Party: {candidate.party}")
        print(f"  Incumbent: {candidate.incumbent}")
        print(f"  Sources: {len(candidate.sources)} sources")
        for source in candidate.sources:
            print(f"    - {source}")
        print()


def test_race_metadata_with_structured_candidates():
    """Test RaceMetadata with both old and new candidate fields."""
    print("=== Testing RaceMetadata with Structured Candidates ===")
    
    # Prepare both old format (strings) and new format (structured)
    discovered_candidates = ["John Smith", "Jane Doe", "Bob Wilson"]
    discovered_candidate_details = [
        DiscoveredCandidate(
            name="John Smith",
            party="Democratic",
            incumbent=True,
            sources=[HttpUrl("https://ballotpedia.org/john-smith")]
        ),
        DiscoveredCandidate(
            name="Jane Doe", 
            party="Republican",
            incumbent=False,
            sources=[HttpUrl("https://wikipedia.org/jane-doe")]
        ),
        DiscoveredCandidate(
            name="Bob Wilson",
            party="Independent",
            incumbent=False,
            sources=[HttpUrl("https://example.com/bob-wilson")]
        )
    ]
    
    metadata = RaceMetadata(
        race_id="mo-senate-2024",
        state="MO",
        office_type="senate",
        year=2024,
        full_office_name="U.S. Senate",
        jurisdiction="MO",
        election_date=datetime(2024, 11, 5),
        race_type="federal",
        discovered_candidates=discovered_candidates,
        discovered_candidate_details=discovered_candidate_details
    )
    
    print(f"Race ID: {metadata.race_id}")
    print(f"Office: {metadata.full_office_name}")
    print(f"Jurisdiction: {metadata.jurisdiction}")
    print(f"Race Type: {metadata.race_type}")
    print()
    
    print("Backward Compatible Format (strings):")
    for name in metadata.discovered_candidates:
        print(f"  - {name}")
    print()
    
    print("New Structured Format:")
    for candidate in metadata.discovered_candidate_details:
        party_str = f" ({candidate.party})" if candidate.party else ""
        incumbent_str = " [INCUMBENT]" if candidate.incumbent else ""
        print(f"  - {candidate.name}{party_str}{incumbent_str}")
        print(f"    Sources: {len(candidate.sources)}")
    print()


def test_enhanced_race_id_parsing():
    """Test the new enhanced race ID parsing with race types."""
    print("=== Testing Enhanced Race ID Parsing ===")
    
    # Regex pattern from the implementation
    slug_pattern = re.compile(
        r"^(?P<state>[a-z]{2})-(?P<office>[\w-]+?)(?:-(?P<district>\d{1,2}))?-(?P<year>\d{4})(?:-(?P<type>primary|special|runoff))?$",
        re.IGNORECASE
    )
    
    test_cases = [
        ("mo-senate-2024", "Standard Senate race"),
        ("ny-house-03-2024", "House race with district"),
        ("ga-senate-2026-primary", "Primary election"),
        ("ny-house-03-2025-special", "Special election with district"),
        ("tx-railroad-commissioner-2026-runoff", "Runoff with complex office name"),
        ("ca-governor-2024", "Governor race"),
        ("fl-attorney-general-2024", "State office with hyphenated name")
    ]
    
    for race_id, description in test_cases:
        match = slug_pattern.match(race_id.lower())
        if match:
            state = match.group('state').upper()
            office = match.group('office')
            year = match.group('year')
            district = match.group('district')
            race_type = match.group('type')
            
            # Determine race type flags
            is_primary = race_type == 'primary'
            is_special = race_type == 'special'
            is_runoff = race_type == 'runoff'
            
            print(f"{race_id} ({description}):")
            print(f"  State: {state}")
            print(f"  Office: {office}")
            print(f"  Year: {year}")
            print(f"  District: {district or 'N/A'}")
            print(f"  Primary: {is_primary}")
            print(f"  Special: {is_special}")
            print(f"  Runoff: {is_runoff}")
            print()
        else:
            print(f"{race_id}: FAILED TO PARSE")
            print()


def test_race_metadata_with_race_types():
    """Test RaceMetadata with different race type flags."""
    print("=== Testing RaceMetadata with Race Type Flags ===")
    
    test_cases = [
        {
            "race_id": "ga-senate-2026-primary",
            "is_primary": True,
            "is_special_election": False,
            "is_runoff": False,
            "description": "Primary Election"
        },
        {
            "race_id": "ny-house-03-2025-special", 
            "is_primary": False,
            "is_special_election": True,
            "is_runoff": False,
            "description": "Special Election"
        },
        {
            "race_id": "tx-railroad-commissioner-2026-runoff",
            "is_primary": False,
            "is_special_election": False,
            "is_runoff": True,
            "description": "Runoff Election"
        }
    ]
    
    for case in test_cases:
        # Parse the race ID properly to get the year using the same logic as our regex
        import re
        slug_pattern = re.compile(
            r"^(?P<state>[a-z]{2})-(?P<office>[\w-]+?)(?:-(?P<district>\d{1,2}))?-(?P<year>\d{4})(?:-(?P<type>primary|special|runoff))?$",
            re.IGNORECASE
        )
        match = slug_pattern.match(case["race_id"].lower())
        if match:
            year = int(match.group('year'))
        else:
            year = 2024  # fallback
            
        metadata = RaceMetadata(
            race_id=case["race_id"],
            state=case["race_id"].split("-")[0].upper(),
            office_type=case["race_id"].split("-")[1],
            year=year,
            full_office_name="Test Office",
            jurisdiction="TEST",
            election_date=datetime(2024, 11, 5),
            race_type="test",
            is_primary=case["is_primary"],
            is_special_election=case["is_special_election"],
            is_runoff=case["is_runoff"]
        )
        
        print(f"{case['description']} ({case['race_id']}):")
        print(f"  Primary: {metadata.is_primary}")
        print(f"  Special: {metadata.is_special_election}")
        print(f"  Runoff: {metadata.is_runoff}")
        print()


if __name__ == "__main__":
    print("Meta Data Engine Upgrades - Manual Testing\n")
    
    test_discovered_candidate_model()
    test_race_metadata_with_structured_candidates()
    test_enhanced_race_id_parsing()
    test_race_metadata_with_race_types()
    
    print("✅ All manual tests completed successfully!")