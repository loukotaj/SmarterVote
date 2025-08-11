"""
Race Metadata Extraction Service for SmarterVote Pipeline

This module provides early extraction of high-level race details to optimize
subsequent discovery and search operations.
"""

from .race_metadata_service import RaceMetadataService

__all__ = ["RaceMetadataService"]
