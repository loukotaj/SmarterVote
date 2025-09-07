from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from .settings import settings
from .storage_backend import GCPStorageBackend, LocalStorageBackend, StorageBackend


def new_artifact_id(step: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{step}-{uuid.uuid4().hex[:8]}"


def _get_backend() -> StorageBackend:
    if settings.storage_mode == "gcp":
        if not settings.gcs_bucket:
            raise ValueError("gcs_bucket must be configured for gcp storage mode")
        return GCPStorageBackend(
            bucket=settings.gcs_bucket,
            firestore_project=settings.firestore_project,
        )
    return LocalStorageBackend(settings.artifacts_dir)


_backend = _get_backend()


def save_artifact(artifact_id: str, data: Dict[str, Any]) -> str:
    return _backend.save_artifact(artifact_id, data)


def load_artifact(artifact_id: str) -> Dict[str, Any]:
    return _backend.load_artifact(artifact_id)


def list_artifacts() -> Dict[str, Any]:
    return _backend.list_artifacts()


def save_race_json(race_id: str, data: Dict[str, Any]) -> str:
    return _backend.save_race_json(race_id, data)


def save_web_content(
    race_id: str,
    filename: str,
    content: bytes | str,
    content_type: str | None = None,
) -> str:
    return _backend.save_web_content(race_id, filename, content, content_type)


def save_content_collection(
    race_id: str,
    content_collection: list,
    content_type: str,
    kind: str = "raw"
) -> list:
    """Save a collection of content items to storage and return references.
    
    Args:
        race_id: The race identifier
        content_collection: List of content items to save
        content_type: Type of content (e.g., 'raw_content', 'processed_content')
        kind: Storage kind/directory (raw, extracted, relevant)
    
    Returns:
        List of references to the saved content
    """
    references = []
    
    for i, item in enumerate(content_collection):
        # Generate a filename for this content item
        filename = f"{content_type}_{i:04d}.json"
        
        # Convert content to JSON string if it's not already
        if isinstance(item, str):
            content_str = item
        else:
            import json
            content_str = json.dumps(item, indent=2, default=str)
        
        # Save to storage
        uri = _backend.save_web_content(
            race_id=race_id,
            filename=filename,
            content=content_str,
            content_type="application/json",
            kind=kind
        )
        
        # Create reference object
        reference = {
            "type": "content_ref",
            "uri": uri,
            "filename": filename,
            "content_type": content_type,
            "kind": kind,
            "index": i
        }
        references.append(reference)
    
    return references


def load_content_from_references(references: list) -> list:
    """Load content from a list of references.
    
    Args:
        references: List of reference objects
    
    Returns:
        List of loaded content items
    """
    content_items = []
    
    for ref in references:
        if not isinstance(ref, dict) or ref.get("type") != "content_ref":
            # If it's not a reference, return as-is (backward compatibility)
            content_items.append(ref)
            continue
            
        # Load content from storage URI
        try:
            # For now, we'll use a simple file-based approach for local storage
            # In the future, this could be enhanced to handle different URI schemes
            uri = ref["uri"]
            if hasattr(_backend, 'artifacts_dir'):  # Local storage check
                from pathlib import Path
                content_path = Path(uri)
                if content_path.exists():
                    content_str = content_path.read_text()
                    
                    # Try to parse as JSON if it's that content type
                    if ref.get("content_type") == "application/json" or uri.endswith('.json'):
                        import json
                        content = json.loads(content_str)
                    else:
                        content = content_str
                    
                    content_items.append(content)
                else:
                    raise FileNotFoundError(f"Content file not found: {uri}")
            else:
                # For GCP storage, we need to handle GCS URIs
                if uri.startswith("gs://"):
                    # Parse GCS URI: gs://bucket/path
                    from urllib.parse import urlparse
                    parsed = urlparse(uri)
                    bucket_name = parsed.netloc
                    blob_path = parsed.path.lstrip('/')
                    
                    try:
                        # Get the blob from GCS
                        from google.cloud import storage
                        client = storage.Client()
                        bucket = client.bucket(bucket_name)
                        blob = bucket.blob(blob_path)
                        
                        content_str = blob.download_as_text()
                        
                        # Try to parse as JSON if it's that content type
                        if ref.get("content_type") == "application/json" or uri.endswith('.json'):
                            import json
                            content = json.loads(content_str)
                        else:
                            content = content_str
                        
                        content_items.append(content)
                    except Exception as e:
                        raise RuntimeError(f"Failed to load from GCS: {e}")
                else:
                    raise NotImplementedError(f"URI scheme not supported: {uri}")
                
        except Exception as e:
            # Log error and skip this item
            import logging
            logger = logging.getLogger("pipeline")
            logger.error(f"Failed to load content from reference {ref}: {e}")
            continue
    
    return content_items
