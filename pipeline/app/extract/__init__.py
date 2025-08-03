"""
Extract Service for SmarterVote Pipeline

This module provides a unified interface for extracting text content from various formats.
"""

from .content_extractor import ContentExtractor

# Main service class for backwards compatibility
ExtractService = ContentExtractor

__all__ = ["ExtractService", "ContentExtractor"]
