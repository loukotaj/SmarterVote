"""
LLM Summarization Engine for SmarterVote Pipeline

This module handles AI-powered summarization using multiple LLM providers with
triangulation for consensus building. Implements the 2-of-3 consensus model
for high-confidence results.

TODO: Implement the following features:
- [ ] Add actual API integrations for OpenAI GPT-4o, Anthropic Claude 3.5, and xAI Grok
- [ ] Implement prompt engineering and optimization for political content
- [ ] Add token usage tracking and cost management
- [ ] Support for streaming responses and partial results
- [ ] Implement rate limiting and retry logic for each provider
- [ ] Add prompt templates for different content types and issues
- [ ] Support for custom model fine-tuning on political content
- [ ] Add bias detection and mitigation strategies
- [ ] Implement content safety and moderation checks
- [ ] Add multi-language summarization support
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from ..schema import ConfidenceLevel, ExtractedContent, LLMResponse, Summary

# Load environment variables
load_dotenv()

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

    def __init__(self, cheap_mode: bool = False):
        # Load API keys from environment
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.xai_api_key = os.getenv("XAI_API_KEY")

        # Set mode
        self.cheap_mode = cheap_mode

        # Validate that at least one API key is available
        if not any([self.openai_api_key, self.anthropic_api_key, self.xai_api_key]):
            logger.warning("No LLM API keys found in environment. Set OPENAI_API_KEY, " "ANTHROPIC_API_KEY, or XAI_API_KEY")

        # Choose model configurations based on mode
        if cheap_mode:
            self.models = {
                "openai": {
                    "model": "gpt-4o-mini",
                    "api_key": self.openai_api_key,
                    "base_url": "https://api.openai.com/v1",
                    "max_tokens": 2000,  # Reduced for mini models
                    "temperature": 0.1,
                    "enabled": bool(self.openai_api_key),
                },
                "anthropic": {
                    "model": "claude-3-haiku-20240307",
                    "api_key": self.anthropic_api_key,
                    "base_url": "https://api.anthropic.com/v1",
                    "max_tokens": 2000,  # Reduced for mini models
                    "temperature": 0.1,
                    "enabled": bool(self.anthropic_api_key),
                },
                "xai": {
                    "model": "grok-2-1212",  # Using available model, will need to update when mini is available
                    "api_key": self.xai_api_key,
                    "base_url": "https://api.x.ai/v1",
                    "max_tokens": 2000,  # Reduced for mini models
                    "temperature": 0.1,
                    "enabled": bool(self.xai_api_key),
                },
            }
        else:
            self.models = {
                "openai": {
                    "model": "gpt-4o",
                    "api_key": self.openai_api_key,
                    "base_url": "https://api.openai.com/v1",
                    "max_tokens": 4000,
                    "temperature": 0.1,  # Low temperature for factual content
                    "enabled": bool(self.openai_api_key),
                },
                "anthropic": {
                    "model": "claude-3-5-sonnet-20241022",
                    "api_key": self.anthropic_api_key,
                    "base_url": "https://api.anthropic.com/v1",
                    "max_tokens": 4000,
                    "temperature": 0.1,
                    "enabled": bool(self.anthropic_api_key),
                },
                "xai": {
                    "model": "grok-beta",
                    "api_key": self.xai_api_key,
                    "base_url": "https://api.x.ai/v1",
                    "max_tokens": 4000,
                    "temperature": 0.1,
                    "enabled": bool(self.xai_api_key),
                },
            }

        # Prompt templates for different tasks
        self.prompts = {
            "candidate_summary": self._get_candidate_summary_prompt(),
            "issue_stance": self._get_issue_stance_prompt(),
            "general_summary": self._get_general_summary_prompt(),
        }

        # HTTP client for API calls
        self.http_client = httpx.AsyncClient(timeout=30.0)

        # Track API usage statistics
        self.api_stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_tokens": 0,
            "provider_stats": {provider: {"calls": 0, "tokens": 0, "errors": 0} for provider in self.models.keys()},
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
            "grok-beta": "grok-4",
            # Cheap/mini models
            "gpt-4o-mini": "gpt-4o-mini",
            "claude-3-haiku-20240307": "claude-3-haiku",
            "grok-2-1212": "grok-3-mini",  # Using available model as placeholder
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
        if hasattr(self, "http_client"):
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

        for provider, config in self.models.items():
            if config.get("enabled"):
                validation_result["enabled_providers"].append(provider)

                # Check API key format (basic validation)
                api_key = config.get("api_key")
                if not api_key:
                    validation_result["errors"].append(f"{provider}: API key is None")
                    validation_result["valid"] = False
                elif len(api_key) < 10:
                    validation_result["warnings"].append(f"{provider}: API key appears too short")

            else:
                validation_result["disabled_providers"].append(provider)

        if not validation_result["enabled_providers"]:
            validation_result["errors"].append("No LLM providers are enabled")
            validation_result["valid"] = False
        elif len(validation_result["enabled_providers"]) == 1:
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
    ) -> List[Summary]:
        """
        Generate AI summaries for extracted content using multiple LLMs.

        Args:
            race_id: The race ID for context
            content: List of extracted content to summarize
            task_type: Type of summarization task

        Returns:
            List of summaries from each LLM

        TODO:
        - [ ] Add content grouping and chunking for large datasets
        - [ ] Implement parallel processing with rate limiting
        - [ ] Add content relevance filtering before summarization
        - [ ] Support for different summary lengths and styles
        """
        logger.info(f"Generating summaries for {len(content)} content items (task: {task_type})")

        if not content:
            return []

        # Prepare content for summarization
        prepared_content = self._prepare_content_for_summarization(content, race_id)

        # Get appropriate prompt template
        prompt_template = self.prompts.get(task_type, self.prompts["general_summary"])

        # Generate summaries from available LLMs
        tasks = []
        enabled_models = {k: v for k, v in self.models.items() if v.get("enabled", False)}

        if not enabled_models:
            logger.error("No LLM providers are enabled. Check API key configuration.")
            return []

        logger.info(f"Using {len(enabled_models)} enabled LLM providers: {list(enabled_models.keys())}")

        for provider, config in enabled_models.items():
            task = self._generate_single_summary(provider, config, prompt_template, prepared_content, race_id, content)
            tasks.append(task)

        try:
            summaries = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out failed requests
            successful_summaries = []
            for i, summary in enumerate(summaries):
                if isinstance(summary, Exception):
                    provider = list(self.models.keys())[i]
                    logger.error(f"Summary generation failed for {provider}: {summary}")
                else:
                    successful_summaries.append(summary)

            logger.info(f"Generated {len(successful_summaries)} summaries")
            return successful_summaries

        except Exception as e:
            logger.error(f"Failed to generate summaries: {e}")
            return []

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

            # Create LLM response record
            llm_response = LLMResponse(
                model=self._get_display_model_name(config["model"]),
                content=response["content"],
                tokens_used=response.get("tokens_used"),
                created_at=datetime.utcnow(),
            )

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

Based on the following content, identify and summarize each candidate's stance on the key issues. For each position:

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
