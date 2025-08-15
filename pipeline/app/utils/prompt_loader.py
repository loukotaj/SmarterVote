"""Utility functions for loading prompt templates from disk."""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a prompt template by name."""
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")
