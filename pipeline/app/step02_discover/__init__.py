"""
Discovery Service for SmarterVote Pipeline

This module provides a unified interface for discovering data sources about electoral races.
"""

from .source_discovery_engine import SourceDiscoveryEngine

# Main service class for backwards compatibility
DiscoveryService = SourceDiscoveryEngine

__all__ = ["DiscoveryService", "SourceDiscoveryEngine"]
