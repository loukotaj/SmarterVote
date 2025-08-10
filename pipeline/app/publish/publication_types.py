"""
Publication types and configuration for SmarterVote Pipeline.

This module contains the core types, enums, and configuration classes
used by the race publishing engine.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict


class PublicationTarget(str, Enum):
    """Available publication targets for race data."""

    LOCAL_FILE = "local_file"
    CLOUD_STORAGE = "cloud_storage"
    DATABASE = "database"
    WEBHOOK = "webhook"
    PUBSUB = "pubsub"
    API_ENDPOINT = "api_endpoint"


@dataclass
class PublicationResult:
    """Result of a publication operation."""

    target: PublicationTarget
    success: bool
    timestamp: datetime
    message: str
    metadata: Dict[str, Any] = None


@dataclass
class PublicationConfig:
    """Configuration for publication operations."""

    output_directory: Path
    enable_cloud_storage: bool = True
    enable_database: bool = True
    enable_webhooks: bool = True
    enable_notifications: bool = True
    version_control: bool = True
    compression: bool = False
    encryption: bool = False
    retention_days: int = 365