"""
AI Provider Registry for SmarterVote Pipeline

Centralized provider management with easy model switching and registration.
"""

from .anthropic_provider import AnthropicProvider
from .base import AIProvider, ModelConfig, ModelTier, ProviderRegistry, SummaryOutput, TaskType
from .openai_provider import OpenAIProvider
from .xai_provider import XAIProvider

# Initialize global registry
registry = ProviderRegistry()

# Register default providers
registry.register_provider("openai", OpenAIProvider())
registry.register_provider("anthropic", AnthropicProvider())
registry.register_provider("xai", XAIProvider())


# Export convenience functions
def get_provider(name: str) -> AIProvider:
    """Get a registered provider by name."""
    return registry.get_provider(name)


def list_providers() -> list[str]:
    """List all registered provider names."""
    return registry.list_providers()


def get_enabled_models(task_type: TaskType = None) -> list[ModelConfig]:
    """Get all enabled models, optionally filtered by task type."""
    return registry.get_enabled_models(task_type)


__all__ = [
    "AIProvider",
    "ModelConfig",
    "ProviderRegistry",
    "TaskType",
    "ModelTier",
    "SummaryOutput",
    "registry",
    "get_provider",
    "list_providers",
    "get_enabled_models",
]
