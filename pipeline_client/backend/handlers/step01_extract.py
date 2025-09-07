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
        if not raw_content:
            error_msg = f"Step01ExtractHandler: Missing 'raw_content' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Import storage functions
        from pipeline_client.backend.storage import load_content_from_references, save_content_collection

        # Check if raw_content is a reference collection or direct content
        if isinstance(raw_content, dict) and raw_content.get("type") == "content_collection_refs":
            logger.info(f"Loading content from {len(raw_content.get('references', []))} references")
            actual_content = load_content_from_references(raw_content["references"])
        elif isinstance(raw_content, list):
            logger.info(f"Using direct content with {len(raw_content)} items")
            actual_content = raw_content
        else:
            error_msg = f"Step01ExtractHandler: Invalid 'raw_content' format in payload."
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not actual_content:
            error_msg = f"Step01ExtractHandler: No content available after loading references."
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Initializing ContentExtractor for {len(actual_content)} items")
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
            result = await service.extract_content(actual_content)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Content extraction completed in {duration_ms}ms")

            # Save extracted content to storage and return references
            race_id = payload.get("race_id", "unknown")

            output = []
            for item in result:
                if hasattr(item, "model_dump"):
                    output.append(item.model_dump(mode="json", by_alias=True, exclude_none=True))
                elif hasattr(item, "json"):
                    output.append(json.loads(item.json(by_alias=True, exclude_none=True)))
                else:
                    output.append(to_jsonable(item))

            # Save content to storage and get references
            logger.info(f"Saving {len(output)} extracted content items to storage")
            references = save_content_collection(race_id, output, "processed_content", "extracted")
            logger.debug(f"Extracted content saved, returning {len(references)} references")

            return {"type": "content_collection_refs", "references": references, "count": len(references), "race_id": race_id}
        except Exception as e:
            error_msg = f"Step01ExtractHandler: Error extracting content: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
