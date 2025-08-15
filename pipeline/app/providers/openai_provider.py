"""
OpenAI provider implementation.
"""

import json
import logging
import os
from typing import Any, Dict, List

try:
    import openai
except ImportError:
    openai = None

from ..utils.prompt_loader import load_prompt
from .base import AIProvider, ModelConfig, ModelTier, SummaryOutput, TaskType
from .constants import ALLOWED_CHAT_KWARGS

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    """OpenAI provider for GPT models."""

    def __init__(self, client: Any | None = None):
        super().__init__("openai")
        self.client = client
        if not self.client:
            self._setup_client()
        self._register_models()

    def _setup_client(self):
        """Initialize OpenAI client."""
        if not openai:
            logger.warning("OpenAI library not installed")
            return

        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = openai.AsyncOpenAI(api_key=api_key)
        else:
            logger.warning("OPENAI_API_KEY not found")

    def _register_models(self):
        """Register available OpenAI models."""
        # Mini models for cheap mode
        self.register_model(
            ModelConfig(
                provider="openai",
                model_id="gpt-4o-mini",
                tier=ModelTier.MINI,
                tasks=[TaskType.SUMMARIZE, TaskType.ARBITRATE, TaskType.EXTRACT, TaskType.DISCOVER],
                max_tokens=16384,
                cost_per_1k_tokens=0.00015,
            )
        )

        # Premium models for full mode
        self.register_model(
            ModelConfig(
                provider="openai",
                model_id="gpt-4o",
                tier=ModelTier.PREMIUM,
                tasks=[TaskType.SUMMARIZE, TaskType.ARBITRATE, TaskType.EXTRACT],
                max_tokens=128000,
                cost_per_1k_tokens=0.03,
            )
        )

    def is_available(self) -> bool:
        """Check if OpenAI is available."""
        if not self.client:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self._setup_client()
        return self.client is not None

    async def generate(self, prompt: str, model_config: ModelConfig, **kwargs) -> str:
        """Generate text using OpenAI."""
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")
        params = {
            "model": model_config.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": model_config.max_tokens,
            "temperature": model_config.temperature,
        }

        # Only pass through recognized OpenAI Chat Completions params; drop unknowns/None.
        safe_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_CHAT_KWARGS and v is not None}
        params.update(safe_kwargs)
        logger.debug(
            "openai.request",
            extra={"model": model_config.model_id, "kwargs": list(kwargs.keys())},
        )

        try:
            response = await self.client.chat.completions.create(**params)
            logger.debug("openai.response", extra={"model": model_config.model_id})
            return response.choices[0].message.content
        except Exception:
            logger.exception("openai.error", extra={"model": model_config.model_id})
            raise

    async def generate_summary(
        self, prompt: str, model_config: ModelConfig, context_sources: List[str] = None, **kwargs
    ) -> SummaryOutput:
        """Generate a structured summary with confidence and sources."""
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")

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
            "openai.request",
            extra={"model": model_config.model_id, "kwargs": list(kwargs.keys())},
        )

        try:
            response = await self.client.chat.completions.create(**params)
            logger.debug("openai.response", extra={"model": model_config.model_id})
            response_text = response.choices[0].message.content

            # Try to parse JSON response
            try:
                parsed = json.loads(response_text)
                return SummaryOutput(
                    content=parsed.get("content", response_text),
                    confidence=parsed.get("confidence", "unknown"),
                    sources=parsed.get("sources_used", []),
                    model_provider=self.name,
                    model_id=model_config.model_id,
                    reasoning=parsed.get("reasoning"),
                )
            except json.JSONDecodeError:
                # Fallback if model doesn't return valid JSON
                logger.warning(f"OpenAI model {model_config.model_id} returned non-JSON response")
                return SummaryOutput(
                    content=response_text,
                    confidence="unknown",
                    sources=context_sources or [],
                    model_provider=self.name,
                    model_id=model_config.model_id,
                    reasoning="Model did not provide confidence assessment",
                )

        except Exception:
            logger.exception("openai.error", extra={"model": model_config.model_id})
            raise
