import logging
import time
import json
from typing import Any, Dict
from pipeline.app.schema import RaceJSON
from pipeline.app.step01_ingest.DiscoveryService.source_discovery_engine import SourceDiscoveryEngine
from pipeline_client.backend.handlers.utils import to_jsonable

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
            error_msg = ("Step01DiscoveryHandler: Missing 'race_json' in payload. "
                         "This step requires output from the metadata service.")
            logger.error(error_msg)
            raise ValueError(error_msg)
        try:
            if isinstance(race_json_payload, RaceJSON):
                race_json = race_json_payload
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
