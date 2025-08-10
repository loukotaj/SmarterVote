"""
LLM Summarization Engine for SmarterVote Pipeline

This module handles AI-powered summarization using multiple LLM providers with
triangulation for consensus building. Implements the 2-of-3 consensus model
for high-confidence results.

Uses the new provider registry system for easy model switching and registration.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from ..providers import SummaryOutput, TaskType, registry
from ..schema import CanonicalIssue, ConfidenceLevel, ExtractedContent, Summary

logger = logging.getLogger(__name__)


class LLMAPIError(Exception):
    """Custom exception for LLM API errors."""

    def __init__(self, provider: str, message: str, status_code: Optional[int] = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} API Error: {message}")


class RateLimitError(LLMAPIError):
    """Exception for rate limiting errors."""

    def __init__(self, provider: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        message = "Rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(provider, message, 429)


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

        # Prompt templates for different tasks
        self.prompts = {
            "candidate_summary": self._get_candidate_summary_prompt(),
            "issue_stance": self._get_issue_stance_prompt(),
            "general_summary": self._get_general_summary_prompt(),
            "race_summary": self._get_race_summary_prompt(),
            "issue_summary": self._get_issue_summary_prompt(),
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
            "grok-3": "grok-3",
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
        await self.close()

    async def close(self):
        """Close the HTTP client."""
        if hasattr(self, "http_client") and self.http_client is not None:
            await self.http_client.aclose()

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
            "enabled_providers": [],
            "disabled_providers": [],
            "warnings": [],
            "errors": [],
        }

        all_providers = registry.list_providers()
        enabled_models = registry.get_enabled_models(TaskType.SUMMARIZE)

        # Check which providers actually have working API keys
        working_providers = []
        for provider_name in all_providers:
            provider = registry.get_provider(provider_name)
            if hasattr(provider, "client") and provider.client is not None:
                working_providers.append(provider_name)

        validation_result["enabled_providers"] = working_providers
        validation_result["disabled_providers"] = [p for p in all_providers if p not in working_providers]

        if not working_providers:
            validation_result["errors"].append("No LLM providers are enabled")
            validation_result["valid"] = False
        elif len(working_providers) == 1:
            validation_result["warnings"].append("Only one provider enabled - triangulation requires 2+ providers")

        return validation_result

    def _update_stats(self, provider: str, success: bool, tokens_used: int = 0):
        """Update API usage statistics."""
        self.api_stats["total_calls"] += 1
        if success:
            self.api_stats["successful_calls"] += 1
            self.api_stats["total_tokens"] += tokens_used
            self.api_stats["provider_stats"][provider]["tokens"] += tokens_used
        else:
            self.api_stats["failed_calls"] += 1
            self.api_stats["provider_stats"][provider]["errors"] += 1

        self.api_stats["provider_stats"][provider]["calls"] += 1

    async def generate_summaries(
        self,
        race_id: str,
        content: List[ExtractedContent],
        task_type: str = "general_summary",
    ) -> Dict[str, List[Summary]]:
        """
        Generate comprehensive summaries for extracted content using multiple LLMs.

        Creates summaries for:
        1. Overall race summary
        2. Individual candidate summaries
        3. Issue-specific analysis for each canonical issue

        Args:
            race_id: The race ID for context
            content: List of extracted content to summarize
            task_type: Type of summarization task (used for backwards compatibility)

        Returns:
            Dict with different types of summaries organized by category

        Implementation covers requirement to generate summaries on:
        - The race itself
        - Each candidate
        - Each issue
        """
        logger.info(f"Generating comprehensive summaries for {len(content)} content items using provider registry")

        if not content:
            return {"race_summaries": [], "candidate_summaries": [], "issue_summaries": []}

        # Get triangulation models for summarization
        model_pairs = registry.get_triangulation_models(TaskType.SUMMARIZE)
        logger.info(f"Using {len(model_pairs)} models for triangulation")

        # Generate different types of summaries
        all_summaries = {"race_summaries": [], "candidate_summaries": [], "issue_summaries": []}

        try:
            # Extract source URLs for context
            context_sources = [
                str(item.source.url)
                for item in content
                if hasattr(item, "source") and item.source and hasattr(item.source, "url")
            ]

            # 1. Generate overall race summary with each model
            logger.info("Generating overall race summary...")
            race_summaries = await self._generate_race_summary_with_providers(race_id, content, model_pairs, context_sources)
            all_summaries["race_summaries"] = race_summaries

            # 2. Generate candidate summaries with each model
            logger.info("Generating candidate summaries...")
            candidate_summaries = await self._generate_candidate_summaries_with_providers(
                race_id, content, model_pairs, context_sources
            )
            all_summaries["candidate_summaries"] = candidate_summaries

            # 3. Generate issue-specific summaries with each model
            logger.info("Generating issue-specific summaries...")
            issue_summaries = await self._generate_issue_summaries_with_providers(
                race_id, content, model_pairs, context_sources
            )
            all_summaries["issue_summaries"] = issue_summaries

            total_summaries = (
                len(all_summaries["race_summaries"])
                + len(all_summaries["candidate_summaries"])
                + len(all_summaries["issue_summaries"])
            )
            logger.info(f"Generated {total_summaries} total summaries across all categories")

            return all_summaries

        except Exception as e:
            logger.error(f"Failed to generate comprehensive summaries: {e}")
            return {"race_summaries": [], "candidate_summaries": [], "issue_summaries": []}

    def triangulate_summaries(self, summaries: List[Summary]) -> Optional[Dict[str, Any]]:
        """
        Triangulate multiple LLM summaries to create consensus analysis.

        Args:
            summaries: List of summaries from different LLMs

        Returns:
            Dict with triangulation results or None if insufficient data
        """
        if len(summaries) < 2:
            logger.warning("Need at least 2 summaries for triangulation")
            return None

        # Analyze agreement patterns
        high_confidence_summaries = [s for s in summaries if s.confidence == ConfidenceLevel.HIGH]
        medium_confidence_summaries = [s for s in summaries if s.confidence == ConfidenceLevel.MEDIUM]

        # Determine consensus confidence
        if len(high_confidence_summaries) >= 2:
            consensus_confidence = ConfidenceLevel.HIGH
            consensus_method = "2-of-3-high"
        elif len(summaries) >= 3 and (len(high_confidence_summaries) + len(medium_confidence_summaries)) >= 2:
            consensus_confidence = ConfidenceLevel.MEDIUM
            consensus_method = "majority-medium"
        else:
            consensus_confidence = ConfidenceLevel.LOW
            consensus_method = "minority-view"

        # Calculate average tokens used
        total_tokens = sum(s.tokens_used or 0 for s in summaries)

        # Create triangulation result
        return {
            "consensus_confidence": consensus_confidence,
            "consensus_method": consensus_method,
            "total_summaries": len(summaries),
            "high_confidence_count": len(high_confidence_summaries),
            "medium_confidence_count": len(medium_confidence_summaries),
            "total_tokens_used": total_tokens,
            "models_used": [s.model for s in summaries],
            "created_at": datetime.utcnow(),
        }

    async def _generate_race_summary_with_providers(
        self, race_id: str, content: List[ExtractedContent], model_pairs: List[tuple], context_sources: List[str]
    ) -> List[Summary]:
        """Generate race summary using provider registry."""
        summaries = []

        # Prepare content for race overview
        race_content = self._filter_content_for_race(content)
        prepared_content = self._prepare_content_for_summarization(race_content, race_id)

        # Generate race summary prompt
        prompt = f"""
        Based on the following content about the {race_id} election, provide a comprehensive race overview.

        Content:
        {prepared_content}

        Please analyze:
        1. Race dynamics and competitive landscape
        2. Key candidates and their backgrounds
        3. Major issues being debated
        4. Recent developments and turning points
        5. Electoral context and significance

        Provide a balanced, factual summary suitable for voters.
        """

        for provider, model_config in model_pairs:
            try:
                summary_output = await provider.generate_summary(prompt, model_config, context_sources)

                # Convert to legacy Summary format
                summary = Summary(
                    content=summary_output.content,
                    model=self._get_display_model_name(model_config.model_id),
                    confidence=self._map_confidence_to_enum(summary_output.confidence),
                    created_at=datetime.utcnow(),
                    metadata={
                        "summary_type": "race_overview",
                        "race_id": race_id,
                        "sources_used": summary_output.sources,
                        "model_provider": summary_output.model_provider,
                        "reasoning": summary_output.reasoning,
                    },
                )
                summaries.append(summary)

            except Exception as e:
                logger.error(f"Failed to generate race summary with {provider.name}/{model_config.model_id}: {e}")
                continue

        return summaries

    async def _generate_candidate_summaries_with_providers(
        self, race_id: str, content: List[ExtractedContent], model_pairs: List[tuple], context_sources: List[str]
    ) -> List[Summary]:
        """Generate candidate summaries using provider registry."""
        summaries = []

        # Extract candidates from content (simplified - could be enhanced)
        candidates = self._extract_candidates_from_content(content)

        for candidate in candidates:
            # Filter content relevant to this candidate
            candidate_content = self._filter_content_for_candidate(content, candidate)
            prepared_content = self._prepare_content_for_summarization(candidate_content, race_id)

            prompt = f"""
            Based on the following content about {candidate} in the {race_id} election, provide a comprehensive candidate analysis.

            Content:
            {prepared_content}

            Please analyze:
            1. Background and qualifications
            2. Policy positions and priorities
            3. Campaign strategy and messaging
            4. Public statements and endorsements
            5. Electoral viability and support base

            Focus specifically on {candidate} and provide factual, balanced analysis.
            """

            for provider, model_config in model_pairs:
                try:
                    summary_output = await provider.generate_summary(prompt, model_config, context_sources)

                    summary = Summary(
                        content=summary_output.content,
                        model=self._get_display_model_name(model_config.model_id),
                        confidence=self._map_confidence_to_enum(summary_output.confidence),
                        created_at=datetime.utcnow(),
                        metadata={
                            "summary_type": "candidate_analysis",
                            "race_id": race_id,
                            "candidate_name": candidate,
                            "sources_used": summary_output.sources,
                            "model_provider": summary_output.model_provider,
                            "reasoning": summary_output.reasoning,
                        },
                    )
                    summaries.append(summary)

                except Exception as e:
                    logger.error(f"Failed to generate candidate summary for {candidate} with {provider.name}: {e}")
                    continue

        return summaries

    async def _generate_issue_summaries_with_providers(
        self, race_id: str, content: List[ExtractedContent], model_pairs: List[tuple], context_sources: List[str]
    ) -> List[Summary]:
        """Generate issue summaries using provider registry."""
        summaries = []

        # Generate summaries for each canonical issue
        for issue in CanonicalIssue:
            # Filter content relevant to this issue
            issue_content = self._filter_content_for_issue(content, issue.value)
            prepared_content = self._prepare_content_for_summarization(issue_content, race_id)

            prompt = f"""
            Based on the following content about {issue.value} in the {race_id} election, provide a comprehensive issue analysis.

            Content:
            {prepared_content}

            Please analyze:
            1. How {issue.value} is being discussed in this race
            2. Different candidate positions and proposals
            3. Key policy differences and debates
            4. Voter concerns and priorities on this issue
            5. Recent developments or policy announcements

            Focus specifically on {issue.value} and provide balanced analysis of all perspectives.
            """

            for provider, model_config in model_pairs:
                try:
                    summary_output = await provider.generate_summary(prompt, model_config, context_sources)

                    summary = Summary(
                        content=summary_output.content,
                        model=self._get_display_model_name(model_config.model_id),
                        confidence=self._map_confidence_to_enum(summary_output.confidence),
                        created_at=datetime.utcnow(),
                        metadata={
                            "summary_type": "issue_analysis",
                            "race_id": race_id,
                            "issue": issue.value,
                            "sources_used": summary_output.sources,
                            "model_provider": summary_output.model_provider,
                            "reasoning": summary_output.reasoning,
                        },
                    )
                    summaries.append(summary)

                except Exception as e:
                    logger.error(f"Failed to generate issue summary for {issue.value} with {provider.name}: {e}")
                    continue

        return summaries

    def _map_confidence_to_enum(self, confidence_str: str) -> ConfidenceLevel:
        """Map string confidence to enum."""
        mapping = {
            "high": ConfidenceLevel.HIGH,
            "medium": ConfidenceLevel.MEDIUM,
            "low": ConfidenceLevel.LOW,
            "unknown": ConfidenceLevel.UNKNOWN,
        }
        return mapping.get(confidence_str.lower(), ConfidenceLevel.UNKNOWN)

    def _extract_candidates_from_content(self, content: List[ExtractedContent]) -> List[str]:
        """Extract candidate names from content (simplified implementation)."""
        # This is a simplified implementation - in reality would use NER or other techniques
        candidates = []
        common_titles = ["senator", "representative", "governor", "mayor", "congressman", "congresswoman"]

        for item in content[:5]:  # Check first few items
            text = item.text.lower()
            # Look for patterns like "candidate X" or "Senator Y"
            words = text.split()
            for i, word in enumerate(words):
                if word in common_titles and i + 1 < len(words):
                    potential_candidate = words[i + 1].title()
                    if len(potential_candidate) > 2 and potential_candidate not in candidates:
                        candidates.append(potential_candidate)
                elif word == "candidate" and i + 1 < len(words):
                    potential_candidate = words[i + 1].title()
                    if len(potential_candidate) > 2 and potential_candidate not in candidates:
                        candidates.append(potential_candidate)

        # Fallback to common names if nothing found
        if not candidates:
            candidates = ["Candidate A", "Candidate B"]

        return candidates[:5]  # Limit to 5 candidates max

    def _filter_content_for_candidate(self, content: List[ExtractedContent], candidate: str) -> List[ExtractedContent]:
        """Filter content relevant to a specific candidate."""
        filtered = []
        for item in content:
            if candidate.lower() in item.text.lower():
                filtered.append(item)
        return filtered[:10]  # Limit for token management

    async def _generate_race_summary(self, race_id: str, content: List[ExtractedContent]) -> List[Summary]:
        """Generate overall race summary from all content."""
        logger.info(f"Generating race summary for {race_id}")

        # Prepare content focusing on race overview
        race_content = self._filter_content_for_race(content)
        prepared_content = self._prepare_content_for_summarization(race_content, race_id)

        prompt_template = self.prompts.get("race_summary", self.prompts["general_summary"])

        return await self._generate_summaries_for_prompt(prompt_template, prepared_content, race_id)

    async def _generate_candidate_summaries(self, race_id: str, content: List[ExtractedContent]) -> List[Summary]:
        """Generate individual candidate summaries."""
        logger.info(f"Generating candidate summaries for {race_id}")

        candidate_summaries = []

        # Extract candidate names from content
        candidate_names = self._extract_candidate_names_from_content(content)

        for candidate_name in candidate_names:
            logger.info(f"Generating summary for candidate: {candidate_name}")

            # Filter content for this specific candidate
            candidate_content = self._filter_content_for_candidate(content, candidate_name)

            if candidate_content:
                prepared_content = self._prepare_content_for_summarization(candidate_content, race_id)
                prompt_template = self.prompts.get("candidate_summary", self.prompts["general_summary"])

                # Customize prompt with candidate name
                candidate_prompt = prompt_template.replace("{candidate_name}", candidate_name)

                summaries = await self._generate_summaries_for_prompt(candidate_prompt, prepared_content, race_id)
                candidate_summaries.extend(summaries)

        return candidate_summaries

    async def _generate_issue_summaries(self, race_id: str, content: List[ExtractedContent]) -> List[Summary]:
        """Generate issue-specific summaries for all canonical issues."""
        logger.info(f"Generating issue summaries for {race_id}")

        issue_summaries = []

        # Import CanonicalIssue from schema
        from ..schema import CanonicalIssue

        for issue in CanonicalIssue:
            logger.info(f"Generating summary for issue: {issue.value}")

            # Filter content for this specific issue
            issue_content = self._filter_content_for_issue(content, issue)

            if issue_content:
                prepared_content = self._prepare_content_for_summarization(issue_content, race_id)
                prompt_template = self.prompts.get("issue_summary", self.prompts["general_summary"])

                # Customize prompt with issue
                issue_prompt = prompt_template.replace("{issue_name}", issue.value)

                summaries = await self._generate_summaries_for_prompt(issue_prompt, prepared_content, race_id)
                issue_summaries.extend(summaries)

        return issue_summaries

    async def _generate_summaries_for_prompt(self, prompt_template: str, prepared_content: str, race_id: str) -> List[Summary]:
        """Generate summaries from all enabled LLMs for a given prompt."""
        tasks = []
        enabled_models = {k: v for k, v in self.models.items() if v.get("enabled", False)}

        if not enabled_models:
            logger.warning("No LLM providers are enabled. Check API key configuration.")
            return []

        for provider, config in enabled_models.items():
            task = self._generate_single_summary(provider, config, prompt_template, prepared_content, race_id)
            tasks.append(task)

        try:
            summaries = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out failed requests
            successful_summaries = []
            for i, summary in enumerate(summaries):
                if isinstance(summary, Exception):
                    provider = list(enabled_models.keys())[i]
                    logger.warning(f"Summary generation failed for {provider}: {summary}")
                else:
                    successful_summaries.append(summary)

            return successful_summaries

        except Exception as e:
            logger.error(f"Failed to generate summaries for prompt: {e}")
            return []

    def _extract_candidate_names_from_content(self, content: List[ExtractedContent]) -> List[str]:
        """Extract candidate names from content analysis."""
        # Simple implementation - in practice would use NER or other techniques
        candidate_names = ["Candidate A", "Candidate B"]  # Placeholder
        return candidate_names

    def _filter_content_for_race(self, content: List[ExtractedContent]) -> List[ExtractedContent]:
        """Filter content relevant to overall race information."""
        # For now return all content, but could filter for race-level info
        return content

    def _filter_content_for_candidate(self, content: List[ExtractedContent], candidate_name: str) -> List[ExtractedContent]:
        """Filter content relevant to specific candidate."""
        # Simple text matching - would use more sophisticated NLP in practice
        filtered = []
        for item in content:
            if candidate_name.lower() in item.text.lower():
                filtered.append(item)
        return filtered if filtered else content[:3]  # Fallback to some content

    def _filter_content_for_issue(self, content: List[ExtractedContent], issue) -> List[ExtractedContent]:
        """Filter content relevant to specific issue."""
        from ..schema import CanonicalIssue

        # Define issue keywords
        issue_keywords = {
            CanonicalIssue.HEALTHCARE: ["health", "medical", "insurance", "medicare", "medicaid"],
            CanonicalIssue.ECONOMY: ["economy", "economic", "jobs", "employment", "taxes"],
            CanonicalIssue.CLIMATE_ENERGY: ["climate", "environment", "energy", "renewable"],
            CanonicalIssue.REPRODUCTIVE_RIGHTS: ["abortion", "reproductive", "family planning"],
            CanonicalIssue.IMMIGRATION: ["immigration", "border", "refugees", "citizenship"],
            CanonicalIssue.GUNS_SAFETY: ["gun", "firearms", "second amendment", "safety"],
            CanonicalIssue.FOREIGN_POLICY: ["foreign", "international", "defense", "military"],
            CanonicalIssue.SOCIAL_JUSTICE: ["lgbtq", "equality", "civil rights", "justice"],
            CanonicalIssue.EDUCATION: ["education", "school", "teachers", "students"],
            CanonicalIssue.TECH_AI: ["technology", "artificial intelligence", "privacy", "tech"],
            CanonicalIssue.ELECTION_REFORM: ["voting", "election", "gerrymandering", "campaign finance"],
        }

        # Handle both string and CanonicalIssue input
        if isinstance(issue, str):
            # Try to match string to CanonicalIssue
            for canonical_issue in CanonicalIssue:
                if issue.lower() in canonical_issue.value.lower() or canonical_issue.value.lower() in issue.lower():
                    keywords = issue_keywords.get(canonical_issue, [issue.lower()])
                    break
            else:
                keywords = [issue.lower()]
        else:
            keywords = issue_keywords.get(issue, [issue.value.lower()])

        filtered = []
        for item in content:
            text_lower = item.text.lower()
            if any(keyword in text_lower for keyword in keywords):
                filtered.append(item)

        return filtered if filtered else content[:2]  # Fallback to some content

    def _prepare_content_for_summarization(self, content: List[ExtractedContent], race_id: str) -> str:
        """
        Prepare extracted content for summarization with detailed source attribution.

        TODO:
        - [ ] Add intelligent content ranking and selection
        - [ ] Implement content deduplication
        - [ ] Add source attribution and credibility weighting
        - [ ] Support for preserving important quotes and data
        """
        # Combine content with enhanced source attribution
        content_blocks = []

        for i, item in enumerate(content, 1):
            # Create detailed source information
            source_info = f"Source {i}: {item.source.title or 'Untitled'}"
            source_url = f"URL: {item.source.url}"
            source_type = f"Type: {item.source.type.value}"
            source_date = f"Accessed: {item.source.last_accessed.strftime('%Y-%m-%d')}"

            # Add metadata if available
            metadata_info = ""
            if item.metadata:
                metadata_items = [f"{k}: {v}" for k, v in item.metadata.items() if v]
                if metadata_items:
                    metadata_info = f"Metadata: {'; '.join(metadata_items)}"

            # Build source header
            source_header = f"{source_info}\n{source_url}\n{source_type}\n{source_date}"
            if metadata_info:
                source_header += f"\n{metadata_info}"

            # Add word count for reference
            word_count = f"Word count: {item.word_count}"
            source_header += f"\n{word_count}"

            content_block = f"{source_header}\n\nContent:\n{item.text}\n"
            content_blocks.append(content_block)

        combined_content = "\n" + "=" * 80 + "\n".join(content_blocks)

        # Add a summary header for the AI
        header = f"""
Race ID: {race_id}
Total Sources: {len(content)}
Content for Analysis:
{combined_content}
        """

        # Truncate if too long (TODO: Implement smarter chunking)
        max_content_length = 15000  # Leave room for prompt and response
        if len(header) > max_content_length:
            header = header[:max_content_length] + "\n\n[Content truncated...]"

        return header

    async def _generate_single_summary(
        self,
        provider: str,
        config: Dict[str, Any],
        prompt_template: str,
        content: str,
        race_id: str,
        original_content: List[ExtractedContent],
    ) -> Summary:
        """
        Generate a summary using a single LLM provider.

        TODO:
        - [ ] Implement actual API calls for each provider
        - [ ] Add retry logic with exponential backoff
        - [ ] Implement token counting and cost tracking
        - [ ] Add response validation and quality checks
        """
        logger.debug(f"Generating summary using {provider}")

        # Construct full prompt
        full_prompt = prompt_template.format(race_id=race_id, content=content)

        try:
            # TODO: Replace with actual API calls
            if provider == "openai":
                response = await self._call_openai_api(config, full_prompt)
            elif provider == "anthropic":
                response = await self._call_anthropic_api(config, full_prompt)
            elif provider == "xai":
                response = await self._call_xai_api(config, full_prompt)
            else:
                raise ValueError(f"Unknown provider: {provider}")

            # Update success statistics
            self._update_stats(provider, True, response.get("tokens_used", 0))

            # Create summary with AI-generated confidence and extracted sources
            ai_confidence = self._parse_ai_confidence(response["content"])
            cited_sources = self._extract_cited_sources(response["content"], original_content)

            summary = Summary(
                content=response["content"],
                model=self._get_display_model_name(config["model"]),
                confidence=ai_confidence,
                tokens_used=response.get("tokens_used"),
                created_at=datetime.utcnow(),
                source_ids=cited_sources,  # Use extracted source IDs
            )

            logger.debug(
                f"Generated summary from {provider}: {len(response['content'])} chars, {response.get('tokens_used', 0)} tokens"
            )
            return summary

        except Exception as e:
            # Update failure statistics
            self._update_stats(provider, False)
            logger.error(f"Failed to generate summary with {provider}: {e}")
            raise

    async def _call_openai_api(self, config: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """
        Call OpenAI API.

        Args:
            config: Model configuration with API key and parameters
            prompt: The prompt to send to the model

        Returns:
            Dict with 'content' and 'tokens_used' keys

        Raises:
            Exception: If API call fails after retries
        """
        if not config.get("api_key"):
            raise ValueError("OpenAI API key not configured")

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": config["max_tokens"],
            "temperature": config["temperature"],
        }

        for attempt in range(3):  # Retry up to 3 times
            try:
                response = await self.http_client.post(
                    f"{config['base_url']}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()

                data = response.json()

                if "choices" not in data or not data["choices"]:
                    raise ValueError("No choices in OpenAI response")

                content = data["choices"][0]["message"]["content"]
                tokens_used = data.get("usage", {}).get("total_tokens", 0)

                logger.debug(f"OpenAI API call successful. Tokens used: {tokens_used}")

                return {
                    "content": content,
                    "tokens_used": tokens_used,
                }

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    retry_after = e.response.headers.get("retry-after")
                    wait_time = int(retry_after) if retry_after else (2**attempt)
                    logger.warning(f"OpenAI rate limit hit. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    error_text = e.response.text if hasattr(e.response, "text") else str(e)
                    raise LLMAPIError("OpenAI", f"HTTP {e.response.status_code}: {error_text}", e.response.status_code)

            except Exception as e:
                if attempt == 2:  # Last attempt
                    if isinstance(e, LLMAPIError):
                        raise
                    raise LLMAPIError("OpenAI", f"Unexpected error: {str(e)}")
                else:
                    wait_time = 2**attempt
                    logger.warning(f"OpenAI API call failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)

        raise LLMAPIError("OpenAI", "API call failed after all retries")

    async def _call_anthropic_api(self, config: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """
        Call Anthropic Claude API.

        Args:
            config: Model configuration with API key and parameters
            prompt: The prompt to send to the model

        Returns:
            Dict with 'content' and 'tokens_used' keys

        Raises:
            Exception: If API call fails after retries
        """
        if not config.get("api_key"):
            raise ValueError("Anthropic API key not configured")

        headers = {
            "x-api-key": config["api_key"],
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": config["model"],
            "max_tokens": config["max_tokens"],
            "temperature": config["temperature"],
            "messages": [{"role": "user", "content": prompt}],
        }

        for attempt in range(3):  # Retry up to 3 times
            try:
                response = await self.http_client.post(
                    f"{config['base_url']}/messages",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()

                data = response.json()

                if "content" not in data or not data["content"]:
                    raise ValueError("No content in Anthropic response")

                content = data["content"][0]["text"]
                tokens_used = data.get("usage", {}).get("output_tokens", 0) + data.get("usage", {}).get("input_tokens", 0)

                logger.debug(f"Anthropic API call successful. Tokens used: {tokens_used}")

                return {
                    "content": content,
                    "tokens_used": tokens_used,
                }

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    retry_after = e.response.headers.get("retry-after")
                    wait_time = int(retry_after) if retry_after else (2**attempt)
                    logger.warning(f"Anthropic rate limit hit. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    error_text = e.response.text if hasattr(e.response, "text") else str(e)
                    raise LLMAPIError("Anthropic", f"HTTP {e.response.status_code}: {error_text}", e.response.status_code)

            except Exception as e:
                if attempt == 2:  # Last attempt
                    if isinstance(e, LLMAPIError):
                        raise
                    raise LLMAPIError("Anthropic", f"Unexpected error: {str(e)}")
                else:
                    wait_time = 2**attempt
                    logger.warning(f"Anthropic API call failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)

        raise LLMAPIError("Anthropic", "API call failed after all retries")

    async def _call_xai_api(self, config: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """
        Call xAI Grok API.

        Args:
            config: Model configuration with API key and parameters
            prompt: The prompt to send to the model

        Returns:
            Dict with 'content' and 'tokens_used' keys

        Raises:
            Exception: If API call fails after retries
        """
        if not config.get("api_key"):
            raise ValueError("xAI API key not configured")

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": config["max_tokens"],
            "temperature": config["temperature"],
        }

        for attempt in range(3):  # Retry up to 3 times
            try:
                response = await self.http_client.post(
                    f"{config['base_url']}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()

                data = response.json()

                if "choices" not in data or not data["choices"]:
                    raise ValueError("No choices in xAI response")

                content = data["choices"][0]["message"]["content"]
                tokens_used = data.get("usage", {}).get("total_tokens", 0)

                logger.debug(f"xAI API call successful. Tokens used: {tokens_used}")

                return {
                    "content": content,
                    "tokens_used": tokens_used,
                }

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    retry_after = e.response.headers.get("retry-after")
                    wait_time = int(retry_after) if retry_after else (2**attempt)
                    logger.warning(f"xAI rate limit hit. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    error_text = e.response.text if hasattr(e.response, "text") else str(e)
                    raise LLMAPIError("xAI", f"HTTP {e.response.status_code}: {error_text}", e.response.status_code)

            except Exception as e:
                if attempt == 2:  # Last attempt
                    if isinstance(e, LLMAPIError):
                        raise
                    raise LLMAPIError("xAI", f"Unexpected error: {str(e)}")
                else:
                    wait_time = 2**attempt
                    logger.warning(f"xAI API call failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)

        raise LLMAPIError("xAI", "API call failed after all retries")

    def _parse_ai_confidence(self, content: str) -> ConfidenceLevel:
        """
        Parse AI-generated confidence score from response content.

        Args:
            content: The AI response content containing confidence indicator

        Returns:
            ConfidenceLevel: The parsed confidence level
        """
        content_upper = content.upper()

        # Look for confidence indicators in the response
        if "CONFIDENCE: HIGH" in content_upper:
            return ConfidenceLevel.HIGH
        elif "CONFIDENCE: MEDIUM" in content_upper:
            return ConfidenceLevel.MEDIUM
        elif "CONFIDENCE: LOW" in content_upper:
            return ConfidenceLevel.LOW
        elif "CONFIDENCE: UNKNOWN" in content_upper:
            return ConfidenceLevel.UNKNOWN
        else:
            # Fallback to heuristic if AI didn't follow format
            logger.warning("AI response did not include expected confidence format, falling back to heuristic assessment")
            return self._assess_confidence(content)

    def _extract_cited_sources(self, ai_response: str, original_content: List[ExtractedContent]) -> List[str]:
        """
        Extract source references from AI response and map them to actual source IDs.

        Args:
            ai_response: The AI-generated response containing source citations
            original_content: The original content with source information

        Returns:
            List of source IDs that were cited in the response
        """
        cited_source_ids = []

        # Create mapping of URLs to source IDs for quick lookup
        url_to_content = {str(item.source.url): item for item in original_content}

        # Look for source citations in various formats
        import re

        # Pattern for (Source: URL) citations
        url_citations = re.findall(r"\(Source:\s*([^)]+)\)", ai_response, re.IGNORECASE)

        # Pattern for "Source N:" references where N is the source number
        source_num_citations = re.findall(r"Source\s+(\d+):", ai_response, re.IGNORECASE)

        # Map URL citations to source IDs
        for citation in url_citations:
            citation = citation.strip()
            # Try exact URL match first
            if citation in url_to_content:
                source_id = str(url_to_content[citation].source.url)
                if source_id not in cited_source_ids:
                    cited_source_ids.append(source_id)
            else:
                # Try partial URL match for cases where AI abbreviated
                for url, content_item in url_to_content.items():
                    if citation in url or url in citation:
                        source_id = str(content_item.source.url)
                        if source_id not in cited_source_ids:
                            cited_source_ids.append(source_id)
                        break

        # Map source number citations to source IDs
        for source_num in source_num_citations:
            try:
                idx = int(source_num) - 1  # Convert to 0-based index
                if 0 <= idx < len(original_content):
                    source_id = str(original_content[idx].source.url)
                    if source_id not in cited_source_ids:
                        cited_source_ids.append(source_id)
            except ValueError:
                continue

        # If no sources were extracted from citations, include all sources as fallback
        if not cited_source_ids:
            logger.warning("No source citations found in AI response, including all sources as fallback")
            cited_source_ids = [str(item.source.url) for item in original_content]

        logger.debug(f"Extracted {len(cited_source_ids)} cited sources from AI response")
        return cited_source_ids

    def _assess_confidence(self, content: str) -> ConfidenceLevel:
        """
        Assess the confidence level of a summary based on content quality indicators.

        Args:
            content: The generated summary content

        Returns:
            ConfidenceLevel: HIGH, MEDIUM, LOW, or UNKNOWN
        """
        if not content or len(content.strip()) < 50:
            return ConfidenceLevel.UNKNOWN

        # Convert to lowercase for analysis
        content_lower = content.lower()

        # High confidence indicators
        high_confidence_indicators = [
            "according to",
            "based on",
            "evidence shows",
            "data indicates",
            "research suggests",
            "studies show",
            "confirmed by",
            "verified",
            "documented",
            "official",
            "endorsed by",
        ]

        # Low confidence indicators
        low_confidence_indicators = [
            "placeholder",
            "unclear",
            "uncertain",
            "might",
            "possibly",
            "potentially",
            "appears to",
            "seems to",
            "allegedly",
            "reportedly",
            "rumored",
            "unverified",
            "unconfirmed",
        ]

        # Medium confidence indicators
        medium_confidence_indicators = [
            "likely",
            "probably",
            "suggests",
            "indicates",
            "implies",
            "generally",
            "typically",
            "tends to",
            "expected",
        ]

        # Count indicators
        high_count = sum(1 for indicator in high_confidence_indicators if indicator in content_lower)
        low_count = sum(1 for indicator in low_confidence_indicators if indicator in content_lower)
        medium_count = sum(1 for indicator in medium_confidence_indicators if indicator in content_lower)

        # Check for specific patterns that indicate low confidence
        if any(pattern in content_lower for pattern in ["placeholder", "todo", "not implemented"]):
            return ConfidenceLevel.LOW

        # Assess content length and structure
        word_count = len(content.split())
        sentence_count = len([s for s in content.split(".") if s.strip()])

        # Quality indicators - lowered word count threshold for better assessment
        has_good_structure = sentence_count >= 2 and word_count >= 30  # More reasonable minimum
        has_specific_details = any(char.isdigit() for char in content)  # Contains numbers/dates

        # Decision logic
        if high_count >= 2 and low_count == 0 and has_good_structure:
            return ConfidenceLevel.HIGH
        elif low_count >= 2:
            return ConfidenceLevel.LOW
        elif medium_count >= 1 or has_specific_details:
            return ConfidenceLevel.MEDIUM
        elif word_count >= 100 and sentence_count >= 4 and high_count >= 1:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _get_candidate_summary_prompt(self) -> str:
        """Get prompt template for candidate summarization."""
        return """
You are a political analyst tasked with creating an objective summary of a candidate in the {race_id} election.

Based on the following content from various sources, provide a comprehensive but concise summary of the candidate including:

1. Basic background and qualifications
2. Key policy positions on major issues
3. Recent campaign developments
4. Notable endorsements or controversies
5. Voting record (if applicable)

Content to analyze:
{content}

IMPORTANT: Your response must follow this exact format:

CONFIDENCE: [HIGH|MEDIUM|LOW|UNKNOWN]
- HIGH: Multiple reliable sources confirm most key information
- MEDIUM: Some reliable sources with limited conflicting information
- LOW: Limited sources or significant conflicting information
- UNKNOWN: Insufficient information to make reliable assessment

SUMMARY:
[Your factual, balanced summary here. Include specific source citations in the format (Source: [URL or title]) when referencing information. Clearly distinguish between verified facts and claims.]

SOURCES CITED:
- [List the specific sources you referenced in your summary]

Summary:
"""

    def _get_issue_stance_prompt(self) -> str:
        """Get prompt template for issue stance analysis."""
        return """
You are analyzing candidate positions on specific policy issues for the {race_id} election.

Based on the following content, identify and summarize each candidate's stance on the key issues.
For each position:

1. State the candidate's position clearly
2. Provide supporting evidence or quotes
3. Note the source and date of the information
4. Identify any changes or evolution in the position
5. Flag any ambiguous or unclear statements

Content to analyze:
{content}

IMPORTANT: Your response must follow this exact format:

CONFIDENCE: [HIGH|MEDIUM|LOW|UNKNOWN]
- HIGH: Multiple reliable sources confirm candidate positions with clear statements
- MEDIUM: Some reliable sources with minor ambiguities or gaps
- LOW: Limited sources or conflicting/unclear position statements
- UNKNOWN: Insufficient information to determine candidate positions

ISSUE ANALYSIS:
[Your factual analysis here. Include specific source citations in the format (Source: [URL or title]) for each position or statement. Focus on factual positions and avoid interpretation or bias.]

SOURCES CITED:
- [List the specific sources you referenced in your analysis]

Issue Analysis:
"""

    def _get_general_summary_prompt(self) -> str:
        """Get prompt template for general content summarization."""
        return """
You are summarizing electoral content for the {race_id} race.

Please provide a comprehensive summary of the following content that includes:

1. Key factual information about the race
2. Major developments and news
3. Candidate positions and statements
4. Important dates and events
5. Relevant context and background

Content to summarize:
{content}

IMPORTANT: Your response must follow this exact format:

CONFIDENCE: [HIGH|MEDIUM|LOW|UNKNOWN]
- HIGH: Multiple reliable sources confirm most key information with good coverage
- MEDIUM: Adequate sources with some gaps or minor inconsistencies
- LOW: Limited sources or significant information gaps
- UNKNOWN: Insufficient information for reliable analysis

SUMMARY:
[Your comprehensive summary here. Include specific source citations in the format (Source: [URL or title]) when referencing information. Maintain objectivity and distinguish between facts, claims, and opinions. Organize the information logically and highlight the most important points.]

SOURCES CITED:
- [List the specific sources you referenced in your summary]

Summary:
"""

    def _get_race_summary_prompt(self) -> str:
        """Get prompt template for overall race summarization."""
        return """
You are analyzing electoral content to create an overall race summary for {race_id}.

Please provide a comprehensive race overview that includes:

1. Race basics: Office, jurisdiction, election date, key context
2. Competitive landscape: Who are the main candidates, their parties
3. Major themes and issues driving the race
4. Recent developments and key events
5. Electoral dynamics and what makes this race significant
6. Historical context and precedent

Content to analyze:
{content}

Focus on providing voters with essential information to understand this electoral contest. Be factual, balanced, and comprehensive.

Race Summary:
"""

    def _get_issue_summary_prompt(self) -> str:
        """Get prompt template for issue-specific summarization."""
        return """
You are analyzing electoral content to summarize how {issue_name} is being addressed in the {race_id} race.

Please provide a focused analysis that includes:

1. How this issue is relevant to this particular race
2. Different candidate positions or approaches to {issue_name}
3. Recent developments or news related to this issue in the race
4. Key policy proposals or statements from candidates
5. Public opinion or stakeholder perspectives on this issue
6. How this issue might influence voter decisions

Content to analyze:
{content}

Focus on the specific issue of {issue_name} and how it relates to this electoral race. Provide balanced coverage of different perspectives.

Issue Analysis for {issue_name}:
"""
