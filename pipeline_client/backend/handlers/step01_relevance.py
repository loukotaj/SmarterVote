import hashlib
import json
import logging
import time
from typing import Any, Dict, List

from pipeline.app.schema import RaceJSON
from pipeline.app.step01_ingest.RelevanceCheck import AIRelevanceFilter
from pipeline_client.backend.handlers.utils import to_jsonable
from shared.models import ExtractedContent, Source


class Step01RelevanceHandler:
    def __init__(self, storage_backend) -> None:
        self.filter_cls = AIRelevanceFilter
        self.storage_backend = storage_backend

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")
        processed = payload.get("processed_content") or payload.get("raw_content")
        race_id = payload.get("race_id")
        race_json_payload = payload.get("race_json")
        if not processed or not isinstance(processed, list):
            error_msg = "Step01RelevanceHandler: Missing 'processed_content' in payload.\n" f"Payload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        if not race_id:
            error_msg = "Step01RelevanceHandler: Missing 'race_id' in payload.\n" f"Payload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        if not race_json_payload:
            error_msg = "Step01RelevanceHandler: Missing 'race_json' in payload."
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            if isinstance(race_json_payload, RaceJSON):
                race_json = race_json_payload
            elif hasattr(RaceJSON, "model_validate"):
                race_json = RaceJSON.model_validate(race_json_payload)
            else:
                race_json = RaceJSON.parse_obj(race_json_payload)  # type: ignore[arg-type]
        except Exception as e:  # noqa: BLE001
            error_msg = f"Step01RelevanceHandler: Invalid race_json provided: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        race_name = race_json.race_metadata.full_office_name if race_json.race_metadata else race_id
        candidates = [c.name for c in race_json.candidates]

        docs: List[ExtractedContent] = []
        for item in processed:
            try:
                if isinstance(item, ExtractedContent):
                    docs.append(item)
                elif hasattr(ExtractedContent, "model_validate"):
                    docs.append(ExtractedContent.model_validate(item))
                else:
                    docs.append(ExtractedContent.parse_obj(item))  # type: ignore[arg-type]
            except Exception as e:  # noqa: BLE001
                logger.warning("Step01RelevanceHandler: Invalid content skipped: %s", e)

        logger.info(f"Initializing AIRelevanceFilter for {len(docs)} items")
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
            result = await filter_service.filter_content(docs, race_name, candidates)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Relevance filtering completed in {duration_ms}ms")
            output = []
            for i, item in enumerate(result):
                try:
                    uri = self.storage_backend.save_web_content(
                        race_id,
                        _filename_from_source(item.source),
                        item.text,
                        content_type="text/plain",
                        kind="relevant",
                    )
                    item.metadata["storage_uri"] = uri
                    if hasattr(item, "model_dump"):
                        output.append(item.model_dump(mode="json", by_alias=True, exclude_none=True))
                    elif hasattr(item, "json"):
                        output.append(json.loads(item.json(by_alias=True, exclude_none=True)))
                    else:
                        output.append(to_jsonable(item))
                except Exception as e:
                    logger.error(f"Error saving item {i+1}: {e}")
            logger.debug(f"Relevance filter conversion completed, items: {len(output)}")
            logger.info("Relevance filtering completed")
            return output
        except Exception as e:
            error_msg = f"Step01RelevanceHandler: Error filtering relevance: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)


def _filename_from_source(source: Source) -> str:
    url = str(source.url)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.txt"
