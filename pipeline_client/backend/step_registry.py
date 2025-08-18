class Step01RelevanceHandler:
    def __init__(self) -> None:
        self.filter_cls = AIRelevanceFilter

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")
        raw_content = payload.get("raw_content")
        race_name = payload.get("race_name")
        candidates = payload.get("candidates", [])
        if not raw_content or not isinstance(raw_content, list):
            error_msg = f"Step01RelevanceHandler: Missing 'raw_content' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        if not race_name:
            error_msg = f"Step01RelevanceHandler: Missing 'race_name' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.info(f"Initializing AIRelevanceFilter for {len(raw_content)} items")
        try:
            filter_service = self.filter_cls()
            logger.debug("AIRelevanceFilter instantiated successfully")
        except Exception as e:
            error_msg = f"Step01RelevanceHandler: Failed to instantiate AIRelevanceFilter: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        try:
            logger.info("Filtering content by relevance")
            t0 = time.perf_counter()
            result = await filter_service.filter_content(raw_content, race_name, candidates)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Relevance filtering completed in {duration_ms}ms")
            output = []
            for item in result:
                if hasattr(item, "model_dump"):
                    output.append(item.model_dump(mode="json", by_alias=True, exclude_none=True))
                elif hasattr(item, "json"):
                    output.append(json.loads(item.json(by_alias=True, exclude_none=True)))
                else:
                    output.append(to_jsonable(item))
            logger.debug(f"Relevance filter conversion completed, items: {len(output)}")
            return output
        except Exception as e:
            error_msg = f"Step01RelevanceHandler: Error filtering relevance: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
import base64
import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Protocol, runtime_checkable


from pipeline_client.backend.handlers.step01_metadata import Step01MetadataHandler
from pipeline_client.backend.handlers.step01_discovery import Step01DiscoveryHandler
from pipeline_client.backend.handlers.step01_fetch import Step01FetchHandler
from pipeline_client.backend.handlers.step01_extract import Step01ExtractHandler
from pipeline_client.backend.handlers.step01_relevance import Step01RelevanceHandler

from .settings import settings
from .storage_backend import GCPStorageBackend, LocalStorageBackend, StorageBackend


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, bytes):
        return base64.b64encode(obj).decode("utf-8")
    else:
        return obj


@runtime_checkable

            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Race metadata extraction completed in {duration_ms}ms")

            if hasattr(result, "model_dump"):
                output = result.model_dump(mode="json", by_alias=True, exclude_none=True)
            elif hasattr(result, "json"):
                output = json.loads(result.json(by_alias=True, exclude_none=True))
            else:
                output = to_jsonable(result)

            logger.debug(
                f"Metadata conversion completed, output keys: {list(output.keys()) if isinstance(output, dict) else 'non-dict result'}"
            )
            race_json_uri = self.storage_backend.save_race_json(race_id, output)
            logger.info(f"Race JSON saved to {race_json_uri}")
            return {"race_json": output, "race_json_uri": race_json_uri}

        except Exception as e:
            error_msg = f"Step01MetadataHandler: Error running extract_race_metadata(race_id='{race_id}'): {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)


class Step01DiscoveryHandler:
    def __init__(self) -> None:
        self.service_cls = SourceDiscoveryEngine

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")

        race_id = payload.get("race_id")
        if not race_id:
            error_msg = f"Step01DiscoveryHandler: Missing 'race_id' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        race_json_payload = payload.get("race_json")
        if not race_json_payload:
            error_msg = (
                "Step01DiscoveryHandler: Missing 'race_json' in payload. "
                "This step requires output from the metadata service."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            if isinstance(race_json_payload, RaceJSON):
                race_json: RaceJSON = race_json_payload
            elif hasattr(RaceJSON, "model_validate"):
