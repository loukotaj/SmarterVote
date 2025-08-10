"""
Publication types and configuration for SmarterVote race publishing.

This module contains enums, dataclasses, and configuration structures
used throughout the race publishing system.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


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
    """Configuration for race publishing operations."""

    # Default publication targets
    default_targets: List[PublicationTarget]

    # Local file publishing configuration
    local_output_dir: str = "data/published"
    pretty_json: bool = True

    # Cloud storage configuration
    cloud_bucket: Optional[str] = None
    cloud_prefix: str = "races"

    # Database configuration
    database_url: Optional[str] = None
    database_table: str = "races"

    # Webhook configuration
    webhook_urls: List[str] = None
    webhook_timeout: int = 30

    # Notification configuration
    enable_notifications: bool = True
    notification_endpoints: List[str] = None