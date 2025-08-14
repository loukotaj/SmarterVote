"""
SmarterVote Pipeline Application

This package contains the corpus-first AI pipeline for processing electoral race data.
The pipeline follows a 4-step process: INGEST → CORPUS → SUMMARIZE → PUBLISH
"""

from .__main__ import CorpusFirstPipeline
from .schema import *

__version__ = "1.1.0"
__all__ = [
    "CorpusFirstPipeline",
    "RaceJSON",
    "CanonicalIssue",
    "ConfidenceLevel",
    "ProcessingStatus",
    "Source",
    "ExtractedContent",
    "Summary",
    "LLMResponse",
    "ArbitrationResult",
    "ProcessingJob",
]
