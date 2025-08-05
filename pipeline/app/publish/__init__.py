"""
Publish Service for SmarterVote Pipeline

This module provides a unified interface for publishing race analysis data.
"""

from .race_publishing_engine import (PublicationConfig, PublicationTarget,
                                     RacePublishingEngine)

# Main service class for backwards compatibility
PublishService = RacePublishingEngine

__all__ = [
    "PublishService",
    "RacePublishingEngine",
    "PublicationConfig",
    "PublicationTarget",
]
