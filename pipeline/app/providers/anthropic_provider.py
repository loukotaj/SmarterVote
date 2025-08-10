"""
Anthropic provider implementation.
"""

import json
import logging
import os
from typing import Any, Dict, List

try:
    import anthropic
except ImportError:
    anthropic = None

from .base import AIProvider, ModelConfig, ModelTier, SummaryOutput, TaskType

logger = logging.getLogger(__name__)


class AnthropicProvider(AIProvider):
    """Anthropic provider for Claude models."""

    def __init__(self):
        super().__init__("anthropic")
        self.client = None
        self._setup_client()
        self._register_models()

    def _setup_client(self):
        """Initialize Anthropic client."""
        if not anthropic:
            logger.warning("Anthropic library not installed")
            return

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            self.client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            logger.warning("ANTHROPIC_API_KEY not found")

    def _register_models(self):
        """Register available Anthropic models."""
        # Mini models for cheap mode
        self.register_model(
            ModelConfig(
                provider="anthropic",
                model_id="claude-3-haiku-20240307",
                tier=ModelTier.MINI,
                tasks=[TaskType.SUMMARIZE, TaskType.ARBITRATE, TaskType.EXTRACT],
                max_tokens=4096,
                cost_per_1k_tokens=0.00025,
            )
        )

        # Premium models for full mode
        self.register_model(
            ModelConfig(
                provider="anthropic",
                model_id="claude-3-5-sonnet-20241022",
                tier=ModelTier.PREMIUM,
                tasks=[TaskType.SUMMARIZE, TaskType.ARBITRATE, TaskType.EXTRACT],
                max_tokens=8192,
                cost_per_1k_tokens=0.003,
            )
        )

    def is_available(self) -> bool:
        """Check if Anthropic is available."""
        return self.client is not None

    async def generate(self, prompt: str, model_config: ModelConfig, **kwargs) -> str:
        """Generate text using Anthropic."""
        if not self.client:
            raise RuntimeError("Anthropic client not initialized")

        try:
            response = await self.client.messages.create(
                model=model_config.model_id,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic generation failed: {e}")
            raise

    async def generate_summary(
        self, prompt: str, model_config: ModelConfig, context_sources: List[str] = None, **kwargs
    ) -> SummaryOutput:
        """Generate a structured summary with confidence and sources."""
        if not self.client:
            raise RuntimeError("Anthropic client not initialized")

        # Enhanced prompt that requests structured output with confidence and sources
        enhanced_prompt = f"""
{prompt}

IMPORTANT: Your response must be in the following JSON format:
{{
    "content": "Your main analysis/summary here",
    "confidence": "high|medium|low",
    "sources_used": ["list", "of", "source", "URLs", "or", "references"],
    "reasoning": "Brief explanation of why you assigned this confidence level"
}}

Confidence guidelines:
- HIGH: Multiple reliable sources confirm the same information
- MEDIUM: Some sources available but may conflict or be incomplete
- LOW: Limited or questionable source material
- UNKNOWN: No relevant sources found

Available sources to reference: {context_sources or []}
"""

        try:
            response = await self.client.messages.create(
                model=model_config.model_id,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
                messages=[{"role": "user", "content": enhanced_prompt}],
                **kwargs,
            )

            response_text = response.content[0].text

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
                logger.warning(f"Anthropic model {model_config.model_id} returned non-JSON response")
                return SummaryOutput(
                    content=response_text,
                    confidence="unknown",
                    sources=context_sources or [],
                    model_provider=self.name,
                    model_id=model_config.model_id,
                    reasoning="Model did not provide confidence assessment",
                )

        except Exception as e:
            logger.error(f"Anthropic summary generation failed: {e}")
            raise
