"""
Extract Service for SmarterVote Pipeline

This module provides a unified interface for extracting text content from various formats.
"""

try:  # pragma: no cover - optional heavy deps
    from .content_extractor import ContentExtractor
    # Main service class for backwards compatibility
    ExtractService = ContentExtractor
    __all__ = ["ExtractService", "ContentExtractor"]
except Exception:  # noqa: BLE001 - missing optional dependencies
    # If dependencies like BeautifulSoup or pandas aren't installed, allow the
    # package to be imported but omit the exports. Tests can skip accordingly.
    __all__: list[str] = []
