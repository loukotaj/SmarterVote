import logging
import time
from typing import Any, Dict

from pipeline.app.providers import registry
from pipeline.app.step01_ingest.MetaDataService.race_metadata_service import RaceMetadataService


class Step01MetadataHandler:
    def __init__(self, storage_backend) -> None:
        self.service_cls = RaceMetadataService
        self.storage_backend = storage_backend

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        if not race_id:
            error_msg = f"Step01MetadataHandler: Missing 'race_id' in payload.\nPayload received: {payload}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.info(f"Initializing RaceMetadataService for race_id='{race_id}'")
        try:
            service = self.service_cls(storage_backend=self.storage_backend)
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
            race_json = result.model_dump(mode="json", by_alias=True, exclude_none=True)
            race_json_uri = getattr(service, "race_json_uri", None)
            if race_json_uri:
                logger.info(f"Race JSON saved to {race_json_uri}")
                return {"race_json": race_json, "race_json_uri": race_json_uri}
            return {"race_json": race_json}
        except Exception as e:
            error_msg = f"Step01MetadataHandler: Error running extract_race_metadata(race_id='{race_id}'): {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
