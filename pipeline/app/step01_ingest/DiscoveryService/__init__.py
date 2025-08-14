"""
Discovery Service for SmarterVote Pipeline

This module provides a unified interface for discovering sources about electoral races.
"""

from .source_discovery_engine import SourceDiscoveryEngine

__all__ = ["SourceDiscoveryEngine"]
