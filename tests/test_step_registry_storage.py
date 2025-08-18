import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from pipeline_client.backend.storage_backend import LocalStorageBackend
from shared.models import ExtractedContent, Source, SourceType

step_registry = pytest.importorskip("pipeline_client.backend.step_registry")
Step01ExtractHandler = step_registry.Step01ExtractHandler
Step01FetchHandler = step_registry.Step01FetchHandler


class DummyFetcher:
    async def fetch_content(self, sources):  # pragma: no cover - used in tests
        checksum = hashlib.sha256(b"hello").hexdigest()
        return [
            {
                "source": sources[0],
                "content": "hello",
                "content_bytes": b"hello",
                "mime_type": "text/plain",
                "content_type": "text/plain",
                "content_checksum": checksum,
            }
        ]


class DummyExtractor:
    async def extract_content(self, raw_content):  # pragma: no cover - used in tests
        text = "hello extracted"
        checksum = hashlib.sha256(text.encode()).hexdigest()
        src = raw_content[0]["source"]
        return [
            ExtractedContent(
                source=src,
                text=text,
                metadata={"content_checksum": checksum},
                extraction_timestamp=datetime.utcnow(),
                word_count=2,
            )
        ]


@pytest.mark.asyncio
async def test_fetch_handler_saves_raw_content(tmp_path):
    storage = LocalStorageBackend(tmp_path)
    handler = Step01FetchHandler(storage)
    handler.service_cls = DummyFetcher
    src = Source(url="http://example.com", type=SourceType.WEBSITE, last_accessed=datetime.utcnow())
    payload = {"race_id": "r1", "sources": [src]}
    result = await handler.handle(payload, {})
    uri = result[0]["raw_uri"]
    assert Path(uri).exists()


@pytest.mark.asyncio
async def test_extract_handler_saves_text(tmp_path):
    storage = LocalStorageBackend(tmp_path)
    handler = Step01ExtractHandler(storage)
    handler.service_cls = DummyExtractor
    src = Source(url="http://example.com", type=SourceType.WEBSITE, last_accessed=datetime.utcnow())
    raw_item = {
        "source": src,
        "content": "hello",
        "content_bytes": b"hello",
        "content_checksum": hashlib.sha256(b"hello").hexdigest(),
        "mime_type": "text/plain",
        "content_type": "text/plain",
    }
    payload = {"race_id": "r1", "raw_content": [raw_item]}
    result = await handler.handle(payload, {})
    uri = result[0]["extracted_uri"]
    assert Path(uri).exists()
