"""
Race Metadata Extraction Service for SmarterVote Pipeline

This module provides early extraction of high-level race details to optimize
subsequent discovery and search operations.
"""

try:  # pragma: no cover - optional provider deps
    from .race_metadata_service import RaceMetadataService
    __all__ = ["RaceMetadataService"]
except Exception:  # noqa: BLE001
    __all__: list[str] = []
