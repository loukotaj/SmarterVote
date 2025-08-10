"""
LLM Summarization Engine for SmarterVote Pipeline

This module handles AI-powered summarization using multiple LLM providers with
triangulation for consensus building. Implements the 2-of-3 consensus model
for high-confidence results.

Uses the new provider registry system for easy model switching and registration.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from ..providers import SummaryOutput, TaskType, registry
from ..schema import CanonicalIssue, ConfidenceLevel, ExtractedContent, Summary
from .api_errors import LLMAPIError, RateLimitError
from .content_processor import ContentProcessor
from .prompt_templates import PromptTemplates
from .triangulation import SummaryTriangulator

logger = logging.getLogger(__name__)


class LLMSummarizationEngine:
    """Engine for generating AI summaries using multiple LLM providers."""

    def __init__(self, cheap_mode: bool = True):
        """Initialize the summarization engine with provider registry."""
        self.cheap_mode = cheap_mode

        # Log available providers
        providers = registry.list_providers()
        logger.info(f"🤖 Available AI providers: {', '.join(providers)}")

        # Get enabled models for summarization
        enabled_models = registry.get_enabled_models(TaskType.SUMMARIZE)
        logger.info(f"📊 Enabled models for summarization: {len(enabled_models)}")

        for model in enabled_models:
            logger.info(f"  - {model.provider}/{model.model_id} ({model.tier.value})")

        # Initialize utility classes
        self.content_processor = ContentProcessor()
        self.prompt_templates = PromptTemplates()
        self.triangulator = SummaryTriangulator()

        # Prompt templates for different tasks
        self.prompts = {
            "candidate_summary": self.prompt_templates.get_candidate_summary_prompt(),
            "issue_stance": self.prompt_templates.get_issue_stance_prompt(),
            "general_summary": self.prompt_templates.get_general_summary_prompt(),
            "race_summary": self.prompt_templates.get_race_summary_prompt(),
            "issue_summary": self.prompt_templates.get_issue_summary_prompt(),
        }

        # Track API usage statistics
        self.api_stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_tokens": 0,
            "provider_stats": {provider: {"calls": 0, "tokens": 0, "errors": 0} for provider in providers},
        }

    def _get_display_model_name(self, full_model_name: str) -> str:
        """
        Convert full model names to display names for backwards compatibility.

        Args:
            full_model_name: The full API model name

        Returns:
            Display name for the model
        """
        model_mapping = {
            # Standard models
            "gpt-4o": "gpt-4o",
            "claude-3-5-sonnet-20241022": "claude-3.5",
            "grok-beta": "grok-3",
            # Cheap/mini models
            "gpt-4o-mini": "gpt-4o-mini",
            "claude-3-haiku-20240307": "claude-3-haiku",
            "grok-3-mini": "grok-3-mini",
        }
        return model_mapping.get(full_model_name, full_model_name)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass

    def get_api_statistics(self) -> Dict[str, Any]:
        """Get API usage statistics."""
        return self.api_stats.copy()

    def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate the current configuration and return status report.

        Returns:
            Dict with validation results
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "provider_count": 0,
            "enabled_models": [],
        }

        try:
            # Check available providers
            providers = registry.list_providers()
            validation_result["provider_count"] = len(providers)

            if len(providers) == 0:
                validation_result["valid"] = False
                validation_result["errors"].append("No LLM providers available")

            # Check enabled models
            enabled_models = registry.get_enabled_models(TaskType.SUMMARIZE)
            validation_result["enabled_models"] = [f"{m.provider}/{m.model_id}" for m in enabled_models]

            if len(enabled_models) < 2:
                validation_result["warnings"].append("Less than 2 models enabled - triangulation not possible")

            if len(enabled_models) == 0:
                validation_result["valid"] = False
                validation_result["errors"].append("No models enabled for summarization")

        except Exception as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Configuration validation failed: {e}")

        return validation_result

    def _update_stats(self, provider: str, success: bool, tokens_used: int = 0):
        """Update API usage statistics."""
        self.api_stats["total_calls"] += 1

        if success:
            self.api_stats["successful_calls"] += 1
        else:
            self.api_stats["failed_calls"] += 1

        self.api_stats["total_tokens"] += tokens_used

        if provider in self.api_stats["provider_stats"]:
            self.api_stats["provider_stats"][provider]["calls"] += 1
            self.api_stats["provider_stats"][provider]["tokens"] += tokens_used
            if not success:
                self.api_stats["provider_stats"][provider]["errors"] += 1

    async def generate_summaries(
        self,
        race_id: str,
        content: List[ExtractedContent],
        summary_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate summaries for race content using multiple AI providers.

        Args:
            race_id: Unique identifier for the race
            content: List of extracted content to summarize
            summary_types: Types of summaries to generate (default: all types)

        Returns:
            Dictionary containing generated summaries and triangulation results

        TODO: Implement comprehensive summary generation:
        - Content preprocessing and optimization
        - Parallel provider execution with timeout handling
        - Dynamic prompt adaptation based on content characteristics
        - Quality scoring and filtering for individual summaries
        - Cross-provider consistency validation
        - Real-time confidence adjustment based on agreement
        - Fallback strategies for provider failures
        - Summary caching and incremental updates
        """
        if summary_types is None:
            summary_types = ["race", "candidates", "issues"]

        logger.info(f"Generating {len(summary_types)} summary types for race {race_id}")

        results = {
            "race_id": race_id,
            "generated_at": datetime.utcnow().isoformat(),
            "content_stats": {
                "total_items": len(content),
                "total_characters": sum(len(item.content) for item in content),
            },
            "summaries": {},
            "triangulation": {},
        }

        try:
            # Generate each type of summary
            for summary_type in summary_types:
                if summary_type == "race":
                    summaries = await self._generate_race_summary_with_providers(race_id, content)
                elif summary_type == "candidates":
                    summaries = await self._generate_candidate_summaries_with_providers(race_id, content)
                elif summary_type == "issues":
                    summaries = await self._generate_issue_summaries_with_providers(race_id, content)
                else:
                    logger.warning(f"Unknown summary type: {summary_type}")
                    continue

                # Store raw summaries
                results["summaries"][summary_type] = summaries

                # Perform triangulation if we have multiple summaries
                if len(summaries) >= 2:
                    triangulated = self.triangulator.triangulate_summaries(summaries)
                    if triangulated:
                        results["triangulation"][summary_type] = triangulated

            logger.info(f"Summary generation complete for race {race_id}")
            return results

        except Exception as e:
            logger.error(f"Failed to generate summaries for race {race_id}: {e}")
            raise

    def triangulate_summaries(self, summaries: List[Summary]) -> Optional[Dict[str, Any]]:
        """
        Delegate to triangulator for backward compatibility.

        Args:
            summaries: List of summaries to triangulate

        Returns:
            Triangulation result or None if insufficient data
        """
        return self.triangulator.triangulate_summaries(summaries)

    async def _generate_race_summary_with_providers(self, race_id: str, content: List[ExtractedContent]) -> List[Summary]:
        """Generate race summaries using multiple providers."""
        return await self._generate_race_summary(race_id, content)

    async def _generate_candidate_summaries_with_providers(
        self, race_id: str, content: List[ExtractedContent]
    ) -> List[Summary]:
        """Generate candidate summaries using multiple providers."""
        return await self._generate_candidate_summaries(race_id, content)

    async def _generate_issue_summaries_with_providers(self, race_id: str, content: List[ExtractedContent]) -> List[Summary]:
        """Generate issue summaries using multiple providers."""
        return await self._generate_issue_summaries(race_id, content)

    def _map_confidence_to_enum(self, confidence_str: str) -> ConfidenceLevel:
        """Map confidence string to ConfidenceLevel enum."""
        if not confidence_str:
            return ConfidenceLevel.UNKNOWN

        confidence_lower = confidence_str.lower().strip()
        if confidence_lower in ["high", "strong", "confident"]:
            return ConfidenceLevel.HIGH
        elif confidence_lower in ["medium", "moderate", "fair"]:
            return ConfidenceLevel.MEDIUM
        elif confidence_lower in ["low", "weak", "poor"]:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.UNKNOWN

    async def _generate_race_summary(self, race_id: str, content: List[ExtractedContent]) -> List[Summary]:
        """Generate race overview summaries."""
        race_content = self.content_processor.filter_content_for_race(content)
        prompt_template = self.prompts["race_summary"]
        return await self._generate_summaries_for_prompt(race_id, race_content, prompt_template, "race_summary")

    async def _generate_candidate_summaries(self, race_id: str, content: List[ExtractedContent]) -> List[Summary]:
        """Generate candidate profile summaries."""
        candidates = self.content_processor.extract_candidates_from_content(content)

        if not candidates:
            logger.warning(f"No candidates found in content for race {race_id}")
            return []

        # For now, generate summaries for all candidates together
        # TODO: Generate individual candidate summaries
        prompt_template = self.prompts["candidate_summary"]
        return await self._generate_summaries_for_prompt(race_id, content, prompt_template, "candidate_summary")

    async def _generate_issue_summaries(self, race_id: str, content: List[ExtractedContent]) -> List[Summary]:
        """Generate issue-specific summaries."""
        # Generate summaries for key canonical issues
        # TODO: Dynamically determine relevant issues from content
        prompt_template = self.prompts["issue_summary"]
        return await self._generate_summaries_for_prompt(race_id, content, prompt_template, "issue_summary")

    async def _generate_summaries_for_prompt(
        self,
        race_id: str,
        content: List[ExtractedContent],
        prompt_template: str,
        summary_type: str,
    ) -> List[Summary]:
        """
        Generate summaries using multiple providers for a given prompt.

        TODO: Implement advanced multi-provider execution:
        - Parallel execution with proper error handling
        - Provider-specific prompt optimization
        - Dynamic timeout adjustment based on content size
        - Retry logic with exponential backoff
        - Circuit breaker pattern for failing providers
        - Load balancing across available providers
        - Cost optimization and provider selection
        - Response quality validation and filtering
        """
        enabled_models = registry.get_enabled_models(TaskType.SUMMARIZE)

        if not enabled_models:
            logger.error("No enabled models available for summarization")
            return []

        # Prepare content for summarization
        formatted_content = self.content_processor.prepare_content_for_summarization(content, race_id)

        summaries = []

        # Generate summaries with available providers
        for model in enabled_models[:3]:  # Limit to 3 providers for triangulation
            try:
                summary = await self._generate_single_summary_with_provider(
                    race_id, formatted_content, prompt_template, summary_type, model
                )
                if summary:
                    summaries.append(summary)
                    self._update_stats(model.provider, True)
            except Exception as e:
                logger.error(f"Failed to generate summary with {model.provider}: {e}")
                self._update_stats(model.provider, False)
                continue

        return summaries

    async def _generate_single_summary_with_provider(
        self, race_id: str, content: str, prompt_template: str, summary_type: str, model
    ) -> Optional[Summary]:
        """Generate a single summary using a specific provider."""
        try:
            # Format the prompt with content
            formatted_prompt = prompt_template.format(race_id=race_id, content=content)

            # Get provider instance
            provider = registry.get_provider(model.provider)
            if not provider:
                logger.error(f"Provider {model.provider} not available")
                return None

            # Generate summary
            result: SummaryOutput = await provider.generate_summary(model.model_id, formatted_prompt, max_tokens=2000)

            if not result or not result.summary:
                logger.warning(f"Empty result from {model.provider}")
                return None

            # Parse confidence from response
            confidence = self.content_processor.parse_ai_confidence(result.summary)

            # Extract sources
            sources = self.content_processor.extract_cited_sources(result.summary, [])

            # Create Summary object
            summary = Summary(
                generator=self._get_display_model_name(model.model_id),
                summary_text=result.summary,
                confidence=confidence,
                sources=sources,
                created_at=datetime.utcnow(),
                race_id=race_id,
                summary_type=summary_type,
            )

            return summary

        except Exception as e:
            logger.error(f"Error generating summary with {model.provider}: {e}")
            raise
