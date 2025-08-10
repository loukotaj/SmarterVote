"""
Base classes for AI provider abstraction.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of AI tasks in the pipeline."""

    SUMMARIZE = "summarize"
    ARBITRATE = "arbitrate"
    EXTRACT = "extract"
    DISCOVER = "discover"


class ModelTier(Enum):
    """Model performance/cost tiers."""

    MINI = "mini"  # Cheap, fast models
    STANDARD = "standard"  # Balanced models
    PREMIUM = "premium"  # Best quality models


@dataclass
class ModelConfig:
    """Configuration for a specific model."""

    provider: str
    model_id: str
    tier: ModelTier
    tasks: List[TaskType]
    max_tokens: int = 4096
    temperature: float = 0.1
    enabled: bool = True
    cost_per_1k_tokens: float = 0.0


@dataclass
class SummaryOutput:
    """Standard output format for summaries with confidence and sources."""

    content: str
    confidence: str  # "high", "medium", "low", "unknown"
    sources: List[str]  # List of source URLs/references used
    model_provider: str
    model_id: str
    reasoning: Optional[str] = None  # Why this confidence level


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, name: str):
        self.name = name
        self._models: Dict[str, ModelConfig] = {}

    @abstractmethod
    async def generate(self, prompt: str, model_config: ModelConfig, **kwargs) -> str:
        """Generate text using the specified model."""
        pass

    @abstractmethod
    async def generate_summary(
        self, prompt: str, model_config: ModelConfig, context_sources: List[str] = None, **kwargs
    ) -> SummaryOutput:
        """Generate a structured summary with confidence and sources."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is properly configured and available."""
        pass

    def register_model(self, model_config: ModelConfig) -> None:
        """Register a model configuration with this provider."""
        self._models[model_config.model_id] = model_config
        logger.info(f"Registered model {model_config.model_id} for provider {self.name}")

    def get_models(self, task_type: TaskType = None, tier: ModelTier = None) -> List[ModelConfig]:
        """Get models for this provider, optionally filtered."""
        models = list(self._models.values())

        if task_type:
            models = [m for m in models if task_type in m.tasks]
        if tier:
            models = [m for m in models if m.tier == tier]

        return [m for m in models if m.enabled]


class ProviderRegistry:
    """Central registry for AI providers and models."""

    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}
        self._cheap_mode = os.getenv("SMARTERVOTE_CHEAP_MODE", "true").lower() in ["true", "1", "yes"]

    def register_provider(self, name: str, provider: AIProvider) -> None:
        """Register an AI provider."""
        self._providers[name] = provider
        logger.info(f"Registered provider: {name}")

    def get_provider(self, name: str) -> AIProvider:
        """Get a provider by name."""
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not found. Available: {list(self._providers.keys())}")
        return self._providers[name]

    def list_providers(self) -> List[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def get_enabled_models(self, task_type: TaskType = None) -> List[ModelConfig]:
        """Get all enabled models across providers."""
        models = []

        # Determine which tier to use
        target_tier = ModelTier.MINI if self._cheap_mode else ModelTier.PREMIUM

        for provider in self._providers.values():
            if not provider.is_available():
                continue

            provider_models = provider.get_models(task_type, target_tier)
            models.extend(provider_models)

        return models

    def get_triangulation_models(self, task_type: TaskType) -> List[tuple[AIProvider, ModelConfig]]:
        """Get 3 models for triangulation, preferring different providers."""
        models = self.get_enabled_models(task_type)

        if len(models) < 3:
            logger.warning(f"Only {len(models)} models available for {task_type}, need 3 for triangulation")

        # Prefer models from different providers
        selected = []
        used_providers = set()

        # First pass: one model per provider
        for model in models:
            if model.provider not in used_providers:
                provider = self.get_provider(model.provider)
                selected.append((provider, model))
                used_providers.add(model.provider)
                if len(selected) >= 3:
                    break

        # Second pass: fill remaining slots if needed
        for model in models:
            if len(selected) >= 3:
                break
            if not any(m.model_id == model.model_id for _, m in selected):
                provider = self.get_provider(model.provider)
                selected.append((provider, model))

        return selected[:3]
