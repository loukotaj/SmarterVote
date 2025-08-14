"""
Ingest Service for SmarterVote Pipeline

This module provides a unified interface for ingesting data into the pipeline.
"""

try:  # pragma: no cover - this import requires many optional deps
    from .ingest_service import IngestService
    __all__ = ["IngestService"]
except Exception:  # noqa: BLE001
    __all__: list[str] = []
