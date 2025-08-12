import datetime
import logging
import time
from typing import Any, Dict, Protocol, runtime_checkable

from pipeline.app.step01_metadata.race_metadata_service import RaceMetadataService


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, datetime.date):
        return obj.isoformat()
    else:
        return obj


@runtime_checkable
class StepHandler(Protocol):
    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any: ...


class Step01MetadataHandler:
    def __init__(self) -> None:
        self.service_cls = RaceMetadataService

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")

        # No dynamic import error handling needed; import errors will be raised at module load time

        race_id = payload.get("race_id")
        if not race_id:
            error_msg = f"Step01MetadataHandler: Missing 'race_id' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Initializing RaceMetadataService for race_id='{race_id}'")

        try:
            service = self.service_cls()
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

            # Convert RaceMetadata (Pydantic) to dict for JSON serialization, including datetime fields
            if hasattr(result, "model_dump"):
                output = to_jsonable(result.model_dump())
            elif hasattr(result, "dict"):
                output = to_jsonable(result.dict())
            else:
                output = to_jsonable(dict(result))

            logger.debug(
                f"Metadata conversion completed, output keys: {list(output.keys()) if isinstance(output, dict) else 'non-dict result'}"
            )
            return output

        except Exception as e:
            error_msg = f"Step01MetadataHandler: Error running extract_race_metadata(race_id='{race_id}'): {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)


REGISTRY: Dict[str, StepHandler] = {
    "step01_metadata": Step01MetadataHandler(),
}


def get_handler(step: str) -> StepHandler:
    try:
        return REGISTRY[step]
    except KeyError:
        raise KeyError(
            f"PipelineClient: Unknown step '{step}'. Registered steps: {list(REGISTRY.keys())}.\nCheck your request and step_registry.py."
        )
