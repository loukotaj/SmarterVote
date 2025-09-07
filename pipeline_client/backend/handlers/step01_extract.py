import json
import logging
import time
from typing import Any, Dict

from pipeline.app.step01_ingest.ContentExtractor.content_extractor import ContentExtractor
from pipeline_client.backend.handlers.utils import to_jsonable


class Step01ExtractHandler:
    def __init__(self) -> None:
        self.service_cls = ContentExtractor

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")
        raw_content = payload.get("raw_content")
        if not raw_content or not isinstance(raw_content, list):
            error_msg = f"Step01ExtractHandler: Missing 'raw_content' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.info(f"Initializing ContentExtractor for {len(raw_content)} items")
        try:
            service = self.service_cls()
            logger.debug("ContentExtractor instantiated successfully")
        except Exception as e:
            error_msg = f"Step01ExtractHandler: Failed to instantiate ContentExtractor: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        try:
            logger.info("Extracting content")
            t0 = time.perf_counter()
            result = await service.extract_content(raw_content)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Content extraction completed in {duration_ms}ms")
            output = []
            for item in result:
                if hasattr(item, "model_dump"):
                    output.append(item.model_dump(mode="json", by_alias=True, exclude_none=True))
                elif hasattr(item, "json"):
                    output.append(json.loads(item.json(by_alias=True, exclude_none=True)))
                else:
                    output.append(to_jsonable(item))
            logger.debug(f"Extract conversion completed, items: {len(output)}")
            return output
        except Exception as e:
            error_msg = f"Step01ExtractHandler: Error extracting content: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
