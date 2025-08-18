import logging
import json
import time
from typing import Any, Dict
from pipeline.app.step01_ingest.RelevanceCheck import AIRelevanceFilter
from pipeline_client.backend.handlers.utils import to_jsonable

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
