"""
Discovery Service for SmarterVote Pipeline

This module provides a unified interface for discovering sources about electoral races.
"""

try:  # pragma: no cover - network-related deps may be missing
    from .source_discovery_engine import SourceDiscoveryEngine

    __all__ = ["SourceDiscoveryEngine"]
except Exception:  # noqa: BLE001
    __all__: list[str] = []
