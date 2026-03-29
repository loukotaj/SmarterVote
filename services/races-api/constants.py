import os
from pathlib import Path


def _default_data_dir() -> str:
    # In the repo: file lives at services/races-api/constants.py → parents[2] = project root
    # In Docker:   file lives at /app/constants.py → parents[2] raises IndexError;
    #              DATA_DIR env var is always set in the Dockerfile so this fallback is fine.
    try:
        project_root = Path(__file__).resolve().parents[2]
        return str(project_root / "data" / "published")
    except IndexError:
        return "/app/data/published"


DEFAULT_DATA_DIR = os.getenv("DATA_DIR", _default_data_dir())
