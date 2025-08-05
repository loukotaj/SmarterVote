"""
SmarterVote Pipeline Application

This package contains the corpus-first AI pipeline for processing electoral race data.
"""

from .__main__ import CorpusFirstPipeline
from .schema import *

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
