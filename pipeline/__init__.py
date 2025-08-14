"""
SmarterVote Pipeline Package

Contains the corpus-first AI pipeline for electoral race analysis.
"""

try:  # pragma: no cover - wrapper for optional heavy deps
    from .app import CorpusFirstPipeline  # type: ignore
except Exception:  # noqa: BLE001 - avoid hard dependency during tests
    CorpusFirstPipeline = None  # type: ignore

__version__ = "1.0.0"
__all__ = ["CorpusFirstPipeline"]
