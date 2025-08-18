import logging
import time
import json
from typing import Any, Dict
from pipeline.app.schema import Source
from pipeline.app.step01_ingest.ContentFetcher import WebContentFetcher
from pipeline_client.backend.handlers.utils import to_jsonable

class Step01FetchHandler:
    def __init__(self) -> None:
        self.service_cls = WebContentFetcher

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")
        sources_payload = payload.get("sources")
        if not sources_payload or not isinstance(sources_payload, list):
            error_msg = f"Step01FetchHandler: Missing 'sources' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        sources = []
        for src in sources_payload:
            try:
                if isinstance(src, Source):
                    sources.append(src)
                elif hasattr(Source, "model_validate"):
                    sources.append(Source.model_validate(src))
                else:
                    sources.append(Source.parse_obj(src))  # type: ignore[arg-type]
            except Exception as e:
                logger.warning(f"Step01FetchHandler: Invalid source skipped: {e}")
        logger.info(f"Initializing WebContentFetcher for {len(sources)} sources")
        try:
            service = self.service_cls()
            logger.debug("WebContentFetcher instantiated successfully")
        except Exception as e:
            error_msg = f"Step01FetchHandler: Failed to instantiate WebContentFetcher: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        try:
            logger.info("Fetching content for sources")
            t0 = time.perf_counter()
            result = await service.fetch_content(sources)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Content fetch completed in {duration_ms}ms")
            output = []
            for item in result:
                src = item.get("source")
                if hasattr(src, "model_dump"):
                    item["source"] = src.model_dump(mode="json", by_alias=True, exclude_none=True)
                output.append(to_jsonable(item))
            logger.debug(f"Fetch conversion completed, items: {len(output)}")
            return output
        except Exception as e:
            error_msg = f"Step01FetchHandler: Error fetching content: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
