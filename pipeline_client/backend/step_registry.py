import base64
import json
import logging
import time
from datetime import date, datetime
from typing import Any, Dict, Protocol, runtime_checkable

from pipeline.app.providers import registry
from pipeline.app.schema import RaceJSON, Source
from pipeline.app.step01_ingest.ContentExtractor.content_extractor import ContentExtractor
from pipeline.app.step01_ingest.ContentFetcher import WebContentFetcher
from pipeline.app.step01_ingest.DiscoveryService.source_discovery_engine import SourceDiscoveryEngine
from pipeline.app.step01_ingest.MetaDataService.race_metadata_service import (
    RaceMetadataService,
)


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
class StepHandler(Protocol):
    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any: ...


class Step01MetadataHandler:
    def __init__(self) -> None:
        # Swap to the LLM-first service class
        self.service_cls = RaceMetadataService

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")

        race_id = payload.get("race_id")
        if not race_id:
            error_msg = f"Step01MetadataHandler: Missing 'race_id' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Initializing RaceMetadataService for race_id='{race_id}'")

        try:
            service = self.service_cls(providers=registry)
            logger.debug("RaceMetadataService instantiated successfully")
        except Exception as e:
            error_msg = f"Step01MetadataHandler: Failed to instantiate RaceMetadataService: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            logger.info(f"Extracting race metadata for race_id='{race_id}'")
            t0 = time.perf_counter()

            result = await service.extract_race_metadata(race_id)

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
            return output

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
                race_json = RaceJSON.model_validate(race_json_payload)
            else:
                race_json = RaceJSON.parse_obj(race_json_payload)  # type: ignore[arg-type]
        except Exception as e:
            error_msg = f"Step01DiscoveryHandler: Invalid race_json provided: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Initializing SourceDiscoveryEngine for race_id='{race_id}'")

        try:
            service = self.service_cls()
            logger.debug("SourceDiscoveryEngine instantiated successfully")
        except Exception as e:
            error_msg = f"Step01DiscoveryHandler: Failed to instantiate SourceDiscoveryEngine: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            logger.info(f"Discovering sources for race_id='{race_id}'")
            t0 = time.perf_counter()

            result = await service.discover_all_sources(race_id, race_json)

            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Source discovery completed in {duration_ms}ms")

            output = []
            for item in result:
                if hasattr(item, "model_dump"):
                    output.append(item.model_dump(mode="json", by_alias=True, exclude_none=True))
                else:
                    output.append(to_jsonable(item))

            logger.debug(f"Discovery conversion completed, items: {len(output)}")
            return output
        except Exception as e:
            error_msg = f"Step01DiscoveryHandler: Error discovering sources for race_id='{race_id}': {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)


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

        sources: list[Source] = []
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



REGISTRY: Dict[str, StepHandler] = {
    "step01a_metadata": Step01MetadataHandler(),
    "step01b_discovery": Step01DiscoveryHandler(),
    "step01c_fetch": Step01FetchHandler(),
    "step01d_extract": Step01ExtractHandler(),
}


def get_handler(step: str) -> StepHandler:
    try:
        return REGISTRY[step]
    except KeyError:
        raise KeyError(
            f"PipelineClient: Unknown step '{step}'. Registered steps: {list(REGISTRY.keys())}.\nCheck your request and step_registry.py."
        )
