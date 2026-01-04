"""
Local LLM provider implementation.

Supports OpenAI-compatible local inference servers like:
- Ollama (http://localhost:11434/v1)
- LM Studio (http://localhost:1234/v1)
- LocalAI, vLLM, text-generation-webui, etc.
"""

import json
import logging
import os
from typing import Any, List, Optional

try:
    import openai
except ImportError:
    openai = None

from ..utils.prompt_loader import load_prompt
from .base import AIProvider, ModelConfig, ModelTier, SummaryOutput, TaskType
from .constants import ALLOWED_CHAT_KWARGS

logger = logging.getLogger(__name__)


class LocalLLMProvider(AIProvider):
    """Local LLM provider using OpenAI-compatible API."""

    def __init__(self, client: Any | None = None):
        super().__init__("local")
        self.client = client
        self.base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
        self.model_name = os.getenv("LOCAL_LLM_MODEL", "llama3.2:3b")
        if not self.client:
            self._setup_client()
        self._register_models()

    def _setup_client(self):
        """Initialize OpenAI-compatible client for local server."""
        if not openai:
            logger.warning("OpenAI library not installed (needed for local LLM client)")
            return

        # Local servers typically don't need a real API key
        api_key = os.getenv("LOCAL_LLM_API_KEY", "local-llm")

        try:
            self.client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=self.base_url,
            )
            logger.info(f"🏠 Local LLM client initialized: {self.base_url}")
        except Exception as e:
            logger.warning(f"Failed to initialize local LLM client: {e}")

    def _register_models(self):
        """Register available local models."""
        # Register the configured local model for all task types
        # Local models are essentially "free" so we register them as MINI tier
        self.register_model(
            ModelConfig(
                provider="local",
                model_id=self.model_name,
                tier=ModelTier.MINI,
                tasks=[TaskType.SUMMARIZE, TaskType.ARBITRATE, TaskType.EXTRACT, TaskType.DISCOVER],
                max_tokens=4096,  # Conservative default, adjust based on your model
                temperature=0.1,
                cost_per_1k_tokens=0.0,  # Free!
            )
        )

        # Also register as STANDARD tier for when cheap_mode is disabled
        self.register_model(
            ModelConfig(
                provider="local",
                model_id=self.model_name,
                tier=ModelTier.STANDARD,
                tasks=[TaskType.SUMMARIZE, TaskType.ARBITRATE, TaskType.EXTRACT, TaskType.DISCOVER],
                max_tokens=4096,
                temperature=0.1,
                cost_per_1k_tokens=0.0,
            )
        )

    def is_available(self) -> bool:
        """Check if local LLM server is available."""
        if not self.client:
            return False

        # Check if LOCAL_LLM_ENABLED is set (opt-in)
        enabled = os.getenv("LOCAL_LLM_ENABLED", "false").lower() in ("true", "1", "yes")
        if not enabled:
            return False

        return True

    async def generate(self, prompt: str, model_config: ModelConfig, **kwargs) -> str:
        """Generate text using local LLM."""
        if not self.client:
            raise RuntimeError("Local LLM client not initialized")

        params = {
            "model": model_config.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": model_config.max_tokens,
            "temperature": model_config.temperature,
        }

        # Filter kwargs to only include supported params
        safe_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_CHAT_KWARGS and v is not None}
        params.update(safe_kwargs)

        logger.debug(
            "local_llm.request",
            extra={"model": model_config.model_id, "base_url": self.base_url},
        )

        try:
            response = await self.client.chat.completions.create(**params)
            logger.debug("local_llm.response", extra={"model": model_config.model_id})
            return response.choices[0].message.content
        except Exception as e:
            logger.exception("local_llm.error", extra={"model": model_config.model_id, "error": str(e)})
            raise

    async def generate_summary(
        self, prompt: str, model_config: ModelConfig, context_sources: Optional[List[str]] = None, **kwargs
    ) -> SummaryOutput:
        """Generate a structured summary with confidence and sources."""
        if not self.client:
            raise RuntimeError("Local LLM client not initialized")

        enhanced_prompt = load_prompt("summary_with_confidence").format(
            prompt=prompt,
            context_sources=context_sources or [],
        )

        params = {
            "model": model_config.model_id,
            "messages": [{"role": "user", "content": enhanced_prompt}],
            "max_tokens": model_config.max_tokens,
            "temperature": model_config.temperature,
        }
        safe_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_CHAT_KWARGS and v is not None}
        params.update(safe_kwargs)

        logger.debug(
            "local_llm.request",
            extra={"model": model_config.model_id, "base_url": self.base_url},
        )

        try:
            response = await self.client.chat.completions.create(**params)
            logger.debug("local_llm.response", extra={"model": model_config.model_id})
            response_text = response.choices[0].message.content

            # Try to parse JSON response
            try:
                parsed = json.loads(response_text)
                return SummaryOutput(
                    content=parsed.get("content", response_text),
                    confidence=parsed.get("confidence", "medium"),  # Default to medium for local
                    sources=parsed.get("sources_used", []),
                    model_provider=self.name,
                    model_id=model_config.model_id,
                    reasoning=parsed.get("reasoning"),
                )
            except json.JSONDecodeError:
                # Local models may not always return valid JSON
                logger.warning(f"Local LLM {model_config.model_id} returned non-JSON response")
                return SummaryOutput(
                    content=response_text,
                    confidence="medium",
                    sources=context_sources or [],
                    model_provider=self.name,
                    model_id=model_config.model_id,
                    reasoning="Local model response (non-JSON)",
                )

        except Exception as e:
            logger.exception("local_llm.error", extra={"model": model_config.model_id, "error": str(e)})
            raise
