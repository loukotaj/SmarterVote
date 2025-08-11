"""
Utility functions for scaffolding RaceJSON from RaceMetadata.
"""

from datetime import datetime, timezone

from shared.models import RaceJSON, RaceMetadata
from shared.state_constants import STATE_NAME


def scaffold_racejson_from_meta(meta: RaceMetadata) -> RaceJSON:
    """
    Create a scaffolded RaceJSON object from RaceMetadata.

    Args:
        meta: RaceMetadata object with race information

    Returns:
        RaceJSON object with basic fields populated
    """
    state_name = STATE_NAME.get(meta.state, meta.state)
    title = f"{state_name} {meta.full_office_name} — {meta.year}"

    return RaceJSON(
        id=meta.race_id,
        election_date=meta.election_date,
        candidates=[],  # downstream will map DiscoveredCandidate -> canonical Candidate
        updated_utc=datetime.now(tz=timezone.utc),
        title=title,
        office=meta.full_office_name,
        jurisdiction=meta.jurisdiction,
        race_metadata=meta,
    )
