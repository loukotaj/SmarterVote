import json
import logging
import time
from datetime import date, datetime
from typing import Any, Dict, Protocol, runtime_checkable

# Use the LLM-first service
from pipeline.app.StepMetaDataService.race_metadata_service import RaceMetadataService

# Shared provider registry
from pipeline.app.providers import registry
from pipeline.app.schema import RaceJSON
from pipeline.app.step01_ingest import IngestService


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
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


class Step02IngestHandler:
    def __init__(self) -> None:
        self.service_cls = IngestService

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")

        race_id = payload.get("race_id")
        if not race_id:
            error_msg = f"Step02IngestHandler: Missing 'race_id' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        race_json_payload = payload.get("race_json")
        race_json: RaceJSON | None = None
        if race_json_payload:
            try:
                if isinstance(race_json_payload, RaceJSON):
                    race_json = race_json_payload
                elif hasattr(RaceJSON, "model_validate"):
                    race_json = RaceJSON.model_validate(race_json_payload)
                else:
                    race_json = RaceJSON.parse_obj(race_json_payload)  # type: ignore[arg-type]
            except Exception as e:
                logger.warning(f"Step02IngestHandler: Invalid race_json provided: {e}")
                race_json = None

        logger.info(f"Initializing IngestService for race_id='{race_id}'")

        try:
            service = self.service_cls()
            logger.debug("IngestService instantiated successfully")
        except Exception as e:
            error_msg = f"Step02IngestHandler: Failed to instantiate IngestService: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            logger.info(f"Running ingest for race_id='{race_id}'")
            t0 = time.perf_counter()

            result = await service.ingest(race_id, race_json=race_json)

            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Ingest completed in {duration_ms}ms")

            output = []
            for item in result:
                if hasattr(item, "model_dump"):
                    output.append(item.model_dump(mode="json", by_alias=True, exclude_none=True))
                elif hasattr(item, "json"):
                    output.append(json.loads(item.json(by_alias=True, exclude_none=True)))
                else:
                    output.append(to_jsonable(item))

            logger.debug(f"Ingest conversion completed, items: {len(output)}")
            return output
        except Exception as e:
            error_msg = f"Step02IngestHandler: Error running ingest(race_id='{race_id}'): {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)


REGISTRY: Dict[str, StepHandler] = {
    "step01_metadata": Step01MetadataHandler(),
    "step02_ingest": Step02IngestHandler(),
}


def get_handler(step: str) -> StepHandler:
    try:
        return REGISTRY[step]
    except KeyError:
        raise KeyError(
            f"PipelineClient: Unknown step '{step}'. Registered steps: {list(REGISTRY.keys())}.\nCheck your request and step_registry.py."
        )
