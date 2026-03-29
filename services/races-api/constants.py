import os
from pathlib import Path

# Resolve data dir relative to project root (two levels up from services/races-api/)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = os.getenv("DATA_DIR", str(_PROJECT_ROOT / "data" / "published"))
