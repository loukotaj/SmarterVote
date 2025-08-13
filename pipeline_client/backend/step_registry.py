import datetime
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Protocol, runtime_checkable

# Provider plumbing
from pipeline.app.providers.base import ModelConfig, ModelTier, ProviderRegistry, TaskType

# Use the LLM-first service
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
    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        ...


def _build_provider_registry(logger: logging.Logger) -> Optional[ProviderRegistry]:
    """
    Try to build a ProviderRegistry with OpenAI gpt-4o-mini registered
    for extraction/JSON tasks. If anything is missing (provider class,
    API key, etc.), return a registry with no providers and log a warning.
    """
    registry = ProviderRegistry()

    # If something upstream already created/primed a registry and put it in env,
    # you could look it up here. For now we build locally.
    openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or os.getenv("OPENAI_KEY")
    if not openai_api_key:
        logger.warning("Provider setup: OPENAI_API_KEY not set; LLM calls will be skipped.")
        return registry  # empty registry is fine; service handles gracefully

    # Try to import a concrete OpenAI provider implementation.
    # Adjust the import path to wherever your OpenAI provider lives.
    try:
        from pipeline.app.providers.openai_provider import OpenAIProvider  # noqa: F401
    except Exception as e:
        logger.warning(f"Provider setup: Could not import OpenAIProvider: {e}. LLM calls will be skipped.")
        return registry

    try:
        # Instantiate provider
        provider = OpenAIProvider()

        # Register the provider
        registry.register_provider("openai", provider)

        logger.info("Provider setup: OpenAI gpt-4o-mini registered for TaskType.EXTRACT.")
        return registry

    except Exception as e:
        logger.warning(f"Provider setup: Failed to initialize/register OpenAI provider: {e}")
        return registry


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

        # Build provider registry (OpenAI gpt-4o-mini), if possible
        providers = _build_provider_registry(logger)

        try:
            service = self.service_cls(providers=providers)
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
