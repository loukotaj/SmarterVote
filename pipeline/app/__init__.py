"""
SmarterVote Pipeline Application

This package contains the corpus-first AI pipeline for processing electoral race data.
The pipeline follows a 4-step process: INGEST → CORPUS → SUMMARIZE → PUBLISH
"""

# Legacy pipeline entry point has been removed.
# Use the pipeline client in ``pipeline_client/backend`` for execution.
CorpusFirstPipeline = None  # type: ignore

from .schema import *  # noqa: F401,F403

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
