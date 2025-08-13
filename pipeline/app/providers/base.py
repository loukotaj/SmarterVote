"""
Base classes for AI provider abstraction, with optional per-task model pinning
and resilient JSON handling (code-fence stripping, balanced-fragment extraction,
and single-pass repair via the selected model).
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# --------------------------- Enums & Data Models ---------------------------


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
    cost_per_1k_tokens: float = 0.0  # For cheap-mode sorting
    # Optional hint: provider may support an explicit JSON mode (e.g., response_format)
    supports_json_mode: bool = False


@dataclass
class SummaryOutput:
    """Standard output format for summaries with confidence and sources."""

    content: str
    confidence: str  # "high", "medium", "low", "unknown"
    sources: List[str]  # List of source URLs/references used
    model_provider: str
    model_id: str
    reasoning: Optional[str] = None  # Why this confidence level


# ------------------------------ Provider API ------------------------------


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, name: str):
        self.name = name
        self._models: Dict[str, ModelConfig] = {}

    @abstractmethod
    async def generate(self, prompt: str, model_config: ModelConfig, **kwargs) -> str:
        """
        Generate text using the specified model.

        Providers MAY honor the following kwargs (best-effort):
          - temperature: float
          - max_tokens: int
          - response_format: dict
          - extra: dict      (provider-specific passthrough)

        Providers should enable native JSON output when `response_format` is supplied and the model supports it.
        """
        raise NotImplementedError

    @abstractmethod
    async def generate_summary(
        self,
        prompt: str,
        model_config: ModelConfig,
        context_sources: Optional[List[str]] = None,
        **kwargs,
    ) -> SummaryOutput:
        """Generate a structured summary with confidence and sources."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is properly configured and available."""
        raise NotImplementedError

    def register_model(self, model_config: ModelConfig) -> None:
        """Register a model configuration with this provider."""
        self._models[model_config.model_id] = model_config
        logger.info(f"Registered model {model_config.model_id} for provider {self.name}")

    def get_models(self, task_type: TaskType | None = None, tier: ModelTier | None = None) -> List[ModelConfig]:
        """Get models for this provider, optionally filtered by task and tier."""
        models = list(self._models.values())
        if task_type:
            models = [m for m in models if task_type in m.tasks]
        if tier:
            models = [m for m in models if m.tier == tier]
        return [m for m in models if m.enabled]


# ---------------------------- Registry & Routing ----------------------------


class ProviderRegistry:
    """Central registry for AI providers/models with pinning & selection."""

    def __init__(self) -> None:
        self._providers: Dict[str, AIProvider] = {}

        # Cheap mode influences tier order and in-tier sorting (by cost).
        self._cheap_mode = os.getenv("SMARTERVOTE_CHEAP_MODE", "true").lower() in ("true", "1", "yes")

        # ----- model pinning (env + programmatic) -----
        # Global preferred model "provider:model_id" or just "model_id" (provider inferred).
        self._preferred_global: Optional[Tuple[str, str]] = self._parse_provider_model(
            os.getenv("SMARTERVOTE_PREFERRED_MODEL")
        )
        # Per-task env overrides, e.g., SMARTERVOTE_PREFERRED_MODEL_EXTRACT="openai:gpt-4o-mini"
        self._preferred_models: Dict[TaskType, Tuple[str, str]] = {}
        for task in TaskType:
            env = os.getenv(f"SMARTERVOTE_PREFERRED_MODEL_{task.name}")
            parsed = self._parse_provider_model(env) if env else None
            if parsed:
                self._preferred_models[task] = parsed

    # ---------- registration / lookup ----------

    def register_provider(self, name: str, provider: AIProvider) -> None:
        self._providers[name] = provider
        logger.info(f"Registered provider: {name}")

    def get_provider(self, name: str) -> AIProvider:
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not found. Available: {list(self._providers.keys())}")
        return self._providers[name]

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())

    # ---------- model pinning API ----------

    def set_preferred_model(self, provider: str, model_id: str, task_type: Optional[TaskType] = None) -> None:
        """
        Pin a preferred model.
        - If task_type is None → sets global default for all tasks (unless a per-task pin exists).
        - If task_type is provided → sets preferred for that task.
        """
        tup = (provider, model_id)
        if task_type is None:
            self._preferred_global = tup
            logger.info(f"Set GLOBAL preferred model: {provider}:{model_id}")
        else:
            self._preferred_models[task_type] = tup
            logger.info(f"Set preferred model for {task_type.name}: {provider}:{model_id}")

    def clear_preferred_model(self, task_type: Optional[TaskType] = None) -> None:
        if task_type is None:
            self._preferred_global = None
            logger.info("Cleared GLOBAL preferred model")
        else:
            self._preferred_models.pop(task_type, None)
            logger.info(f"Cleared preferred model for {task_type.name}")

    # ---------- model selection ----------

    def _tier_preference(self) -> List[ModelTier]:
        return (
            [ModelTier.MINI, ModelTier.STANDARD, ModelTier.PREMIUM]
            if self._cheap_mode
            else [ModelTier.PREMIUM, ModelTier.STANDARD, ModelTier.MINI]
        )

    @staticmethod
    def _parse_provider_model(s: Optional[str]) -> Optional[Tuple[str, str]]:
        if not s:
            return None
        s = s.strip()
        if not s:
            return None
        if ":" in s:
            provider, model_id = s.split(":", 1)
            return provider.strip(), model_id.strip()
        # If only model_id provided, search across providers to find it.
        return ("*", s)

    def _resolve_preferred(self, task_type: TaskType) -> Optional[Tuple[str, str]]:
        return self._preferred_models.get(task_type) or self._preferred_global

    def _find_model_by_provider_and_id(
        self, provider_name: str, model_id: str, task_type: Optional[TaskType]
    ) -> Optional[Tuple[AIProvider, ModelConfig]]:
        """Find an exact provider:model match (and verify availability & task support)."""
        provider = self._providers.get(provider_name)
        if not provider or not provider.is_available():
            return None
        cfg = provider._models.get(model_id)
        if not cfg or not cfg.enabled:
            return None
        if task_type and task_type not in cfg.tasks:
            return None
        return provider, cfg

    def _find_model_by_id_any_provider(
        self, model_id: str, task_type: Optional[TaskType]
    ) -> Optional[Tuple[AIProvider, ModelConfig]]:
        """Search all providers for a model_id."""
        for provider in self._providers.values():
            if not provider.is_available():
                continue
            cfg = provider._models.get(model_id)
            if not cfg or not cfg.enabled:
                continue
            if task_type and task_type not in cfg.tasks:
                continue
            return provider, cfg
        return None

    def _sort_models_for_selection(self, models: List[ModelConfig]) -> List[ModelConfig]:
        # Cheap mode: prefer lowest cost; otherwise prefer highest (proxy for quality).
        reverse = not self._cheap_mode
        return sorted(models, key=lambda m: (m.cost_per_1k_tokens, m.model_id), reverse=reverse)

    def get_enabled_models(self, task_type: TaskType | None = None) -> List[ModelConfig]:
        """
        Get enabled models across providers, honoring CHEAP_MODE by preferring a tier bucket,
        then sorting within that bucket by cost. Falls back to any-tier if needed.
        """
        tiers = self._tier_preference()

        # Try the preferred tier bucket first.
        for tier in tiers:
            bucket: List[ModelConfig] = []
            for provider in self._providers.values():
                if not provider.is_available():
                    continue
                bucket.extend(provider.get_models(task_type, tier))
            bucket = [m for m in bucket if m.enabled]
            if bucket:
                return self._sort_models_for_selection(bucket)

        # Fall back to any tier.
        any_tier: List[ModelConfig] = []
        for provider in self._providers.values():
            if not provider.is_available():
                continue
            any_tier.extend(provider.get_models(task_type, tier=None))
        return self._sort_models_for_selection([m for m in any_tier if m.enabled])

    def get_triangulation_models(self, task_type: TaskType) -> List[Tuple[AIProvider, ModelConfig]]:
        """
        Get up to 3 models for triangulation.
        If a preferred model is pinned for this task, return that single model.
        """
        preferred = self._resolve_preferred(task_type)
        if preferred:
            provider_name, model_id = preferred
            picked = (
                self._find_model_by_id_any_provider(model_id, task_type)
                if provider_name == "*"
                else self._find_model_by_provider_and_id(provider_name, model_id, task_type)
            )
            if picked:
                return [picked]
            logger.warning(f"Preferred model {provider_name}:{model_id} not found/available for {task_type.name}")

        models = self.get_enabled_models(task_type)
        if not models:
            logger.warning(f"No models available for {task_type}")
            return []

        selected: List[Tuple[AIProvider, ModelConfig]] = []
        used_providers = set()

        # Prefer provider diversity first.
        for m in models:
            if m.provider in used_providers:
                continue
            provider = self._providers.get(m.provider)
            if not provider:
                continue
            selected.append((provider, m))
            used_providers.add(m.provider)
            if len(selected) >= 3:
                break

        # Fill remaining with different models even if from same provider.
        if len(selected) < 3:
            for m in models:
                if len(selected) >= 3:
                    break
                if any(m.model_id == sm.model_id for _, sm in selected):
                    continue
                provider = self._providers.get(m.provider)
                if not provider:
                    continue
                selected.append((provider, m))

        return selected[:3]

    def pick_model(
        self,
        task_type: TaskType,
        provider_name: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Optional[Tuple[AIProvider, ModelConfig]]:
        """
        Pick one model for the task.
        Priority:
          1) Explicit provider_name+model_id args (hard override)
          2) Preferred model pinned (per-task or global)
          3) Tier-preferred automatic selection
        """
        # (1) explicit override
        if provider_name and model_id:
            chosen = self._find_model_by_provider_and_id(provider_name, model_id, task_type)
            if chosen:
                logger.info(f"Using EXPLICIT model override for {task_type.name}: {provider_name}:{model_id}")
                return chosen
            raise RuntimeError(f"Explicit model override not found/available: {provider_name}:{model_id}")

        # (2) preferred (pinned) model
        preferred = self._resolve_preferred(task_type)
        if preferred:
            p_name, m_id = preferred
            chosen = (
                self._find_model_by_id_any_provider(m_id, task_type)
                if p_name == "*"
                else self._find_model_by_provider_and_id(p_name, m_id, task_type)
            )
            if chosen:
                logger.info(f"Using PREFERRED model for {task_type.name}: {chosen[1].provider}:{chosen[1].model_id}")
                return chosen
            logger.warning(f"Preferred model {p_name}:{m_id} not found/available for {task_type.name}")

        # (3) fallback to tier selection
        models = self.get_enabled_models(task_type)
        if not models:
            return None
        m = models[0]
        logger.info(f"Using FALLBACK model for {task_type.name}: {m.provider}:{m.model_id}")
        return self.get_provider(m.provider), m

    # ---------- convenience generation helpers ----------

    async def generate_text(
        self,
        task_type: TaskType,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        provider_name: Optional[str] = None,
        model_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Pick a model for the task and generate raw text.
        kwargs are forwarded to provider.generate (e.g., json_mode).
        """
        picked = self.pick_model(task_type, provider_name=provider_name, model_id=model_id)
        if not picked:
            raise RuntimeError(f"No enabled models available for task {task_type}")
        provider, model = picked
        if temperature is None:
            temperature = model.temperature
        if max_tokens is None:
            max_tokens = model.max_tokens

        # Pass a json_mode hint when caller asks; provider may choose to honor it.
        # (If the model supports native JSON mode, provider may switch it on.)
        return await provider.generate(
            prompt,
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    # --------------------- JSON helpers (robust & opinionated) ---------------------

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Remove ```json ... ``` or ``` ... ``` fences if present."""
        m = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
        return m.group(1).strip() if m else text.strip()

    @staticmethod
    def _extract_first_json_object_or_array(text: str) -> Optional[str]:
        """Extract the first balanced {...} or [...] region."""
        stack: List[str] = []
        start: Optional[int] = None
        for i, ch in enumerate(text):
            if ch in "{[":
                if not stack:
                    start = i
                stack.append(ch)
            elif ch in "}]":
                if not stack:
                    continue
                open_ch = stack.pop()
                if (open_ch, ch) in {("{", "}"), ("[", "]")} and not stack and start is not None:
                    return text[start : i + 1]
        return None

    @classmethod
    def _loads_best_effort(cls, raw_text: str) -> Dict[str, Any]:
        """
        Try direct loads, then fence-strip, then first balanced JSON fragment.
        Raises JSONDecodeError on failure.
        """
        candidates = (
            raw_text,
            cls._strip_code_fences(raw_text),
            cls._extract_first_json_object_or_array(raw_text) or "",
        )
        last_err: Optional[json.JSONDecodeError] = None
        for cand in candidates:
            if not cand:
                continue
            try:
                return json.loads(cand)
            except json.JSONDecodeError as e:
                last_err = e
        assert last_err is not None
        raise last_err

    @staticmethod
    def _normalize_null_strings(obj: Any) -> Any:
        """Convert string 'null' to None recursively."""
        if isinstance(obj, dict):
            return {k: ProviderRegistry._normalize_null_strings(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [ProviderRegistry._normalize_null_strings(v) for v in obj]
        if obj == "null":
            return None
        return obj

    async def _repair_json_via_model(
        self,
        provider: AIProvider,
        model: ModelConfig,
        raw_text: str,
        schema_hint: Optional[str],
    ) -> Dict[str, Any]:
        """
        Single cheap repair pass using the selected provider/model.
        Provider may honor json_mode to enforce strict JSON if supported.
        """
        repair_prompt = (
            "Fix the following into STRICT, valid JSON only.\n"
            "Do not add code fences or any prose.\n"
            + (f"It MUST match this shape (schema hint): {schema_hint}\n" if schema_hint else "")
            + "\n---\n"
            + raw_text
            + "\n---"
        )
        repaired = await provider.generate(
            repair_prompt,
            model,
            temperature=0,
            max_tokens=max(512, min(model.max_tokens, 2048)),
            json_mode=model.supports_json_mode,  # hint to provider
        )
        repaired = self._strip_code_fences(repaired)
        return self._loads_best_effort(repaired)

    async def generate_json(
        self,
        task_type: TaskType,
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        provider_name: Optional[str] = None,
        model_id: Optional[str] = None,
        allow_repair: bool = True,
        repair_schema_hint: Optional[str] = None,
        normalize_null_strings: bool = True,
        response_format: Dict[str, Any],  # required: forwarded to provider
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Generate JSON by calling provider.generate and parsing the result.
        - Tries best-effort parsing (fences/fragment) first.
        - If that fails and allow_repair=True, runs a one-shot repair call with the same model.
        - Optional normalize_null_strings=True maps string 'null' -> None recursively.
        - response_format: required; forwarded to the provider on the primary call.
        """
        picked = self.pick_model(task_type, provider_name=provider_name, model_id=model_id)
        if not picked:
            raise RuntimeError(f"No enabled models available for task {task_type}")
        provider, model = picked

        text = await self.generate_text(
            task_type,
            prompt,
            max_tokens=max_tokens,
            provider_name=provider.name,
            model_id=model.model_id,
            response_format=response_format,
            **kwargs,
        )

        try:
            data = self._loads_best_effort(text)
        except json.JSONDecodeError:
            if not allow_repair:
                raise
            logger.warning("Primary JSON parse failed; attempting single repair pass.")
            data = await self._repair_json_via_model(provider, model, text, repair_schema_hint)

        if normalize_null_strings:
            data = self._normalize_null_strings(data)
        return data

    async def summarize(
        self,
        task_type: TaskType,
        prompt: str,
        *,
        context_sources: Optional[List[str]] = None,
        provider_name: Optional[str] = None,
        model_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SummaryOutput:
        """Wrapper to call provider.generate_summary using task-aware model selection."""
        picked = self.pick_model(task_type, provider_name=provider_name, model_id=model_id)
        if not picked:
            raise RuntimeError(f"No enabled models available for task {task_type}")
        provider, model = picked
        return await provider.generate_summary(
            prompt,
            model,
            context_sources=context_sources or [],
            **kwargs,
        )
