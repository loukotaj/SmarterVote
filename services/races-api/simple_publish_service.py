"""
Simple publish service for races API.
This avoids importing the full pipeline while providing the needed functionality.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path for shared imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.models import RaceJSON


class SimplePublishService:
    """Simple service for reading published race data without pipeline dependencies."""

    def __init__(self, data_directory: str = "data/published/"):
        self.data_directory = Path(data_directory)
        if not self.data_directory.exists():
            self.data_directory.mkdir(parents=True, exist_ok=True)

    def get_published_races(self) -> List[str]:
        """List available race IDs from published JSON files."""
        race_ids = []
        if self.data_directory.exists():
            for file_path in self.data_directory.glob("*.json"):
                # Extract race ID from filename (remove .json extension)
                race_id = file_path.stem
                race_ids.append(race_id)
        return sorted(race_ids)

    def get_race_data(self, race_id: str) -> Optional[Dict]:
        """Retrieve race data by ID."""
        file_path = self.data_directory / f"{race_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, IOError):
            return None

    def get_race(self, race_id: str) -> Optional[RaceJSON]:
        """Retrieve race data as RaceJSON model."""
        data = self.get_race_data(race_id)
        if not data:
            return None

        try:
            return RaceJSON(**data)
        except Exception:
            return None
