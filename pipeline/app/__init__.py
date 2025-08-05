"""
SmarterVote Pipeline Application

This package contains the corpus-first AI pipeline for processing electoral race data.
"""

from .schema import *
from .__main__ import CorpusFirstPipeline

__version__ = "1.0.0"
__all__ = [
    "CorpusFirstPipeline",
    "RaceJSON",
    "CanonicalIssue",
    "Source",
    "ExtractedContent",
    "Summary",
    "LLMResponse",
    "ArbitrationResult",
]
