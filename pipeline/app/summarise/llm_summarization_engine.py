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

from ..schema import CanonicalIssue, ConfidenceLevel, ExtractedContent, LLMResponse, Summary

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class LLMSummarizationEngine:
    """Engine for generating AI summaries using multiple LLM providers."""

    def __init__(self):
        # Load API keys from environment
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.xai_api_key = os.getenv("XAI_API_KEY")
        
        # Validate that at least one API key is available
        if not any([self.openai_api_key, self.anthropic_api_key, self.xai_api_key]):
            logger.warning("No LLM API keys found in environment. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or XAI_API_KEY")
        
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

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close the HTTP client."""
        if hasattr(self, 'http_client'):
            await self.http_client.aclose()

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
            task = self._generate_single_summary(provider, config, prompt_template, prepared_content, race_id)
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

    def _prepare_content_for_summarization(self, content: List[ExtractedContent], race_id: str) -> str:
        """
        Prepare extracted content for summarization.

        TODO:
        - [ ] Add intelligent content ranking and selection
        - [ ] Implement content deduplication
        - [ ] Add source attribution and credibility weighting
        - [ ] Support for preserving important quotes and data
        """
        # Combine content with source attribution
        content_blocks = []

        for item in content:
            source_info = f"Source: {item.source.title or item.source.url}"
            content_block = f"{source_info}\n{item.text}\n"
            content_blocks.append(content_block)

        combined_content = "\n---\n".join(content_blocks)

        # Truncate if too long (TODO: Implement smarter chunking)
        max_content_length = 15000  # Leave room for prompt and response
        if len(combined_content) > max_content_length:
            combined_content = combined_content[:max_content_length] + "\n\n[Content truncated...]"

        return combined_content

    async def _generate_single_summary(
        self,
        provider: str,
        config: Dict[str, Any],
        prompt_template: str,
        content: str,
        race_id: str,
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

            # Create LLM response record
            llm_response = LLMResponse(
                model=config["model"],
                content=response["content"],
                tokens_used=response.get("tokens_used"),
                created_at=datetime.utcnow(),
            )

            # Create summary
            summary = Summary(
                content=response["content"],
                model=config["model"],
                confidence=self._assess_confidence(response["content"]),
                tokens_used=response.get("tokens_used"),
                created_at=datetime.utcnow(),
                source_ids=[race_id],  # Store race_id as source reference
            )

            return summary

        except Exception as e:
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
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
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
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"OpenAI rate limit hit. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
                    raise
                    
            except Exception as e:
                if attempt == 2:  # Last attempt
                    logger.error(f"OpenAI API call failed after 3 attempts: {e}")
                    raise
                else:
                    wait_time = 2 ** attempt
                    logger.warning(f"OpenAI API call failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
        
        raise Exception("OpenAI API call failed after all retries")

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
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
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
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Anthropic rate limit hit. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Anthropic API error: {e.response.status_code} - {e.response.text}")
                    raise
                    
            except Exception as e:
                if attempt == 2:  # Last attempt
                    logger.error(f"Anthropic API call failed after 3 attempts: {e}")
                    raise
                else:
                    wait_time = 2 ** attempt
                    logger.warning(f"Anthropic API call failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
        
        raise Exception("Anthropic API call failed after all retries")

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
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
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
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"xAI rate limit hit. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"xAI API error: {e.response.status_code} - {e.response.text}")
                    raise
                    
            except Exception as e:
                if attempt == 2:  # Last attempt
                    logger.error(f"xAI API call failed after 3 attempts: {e}")
                    raise
                else:
                    wait_time = 2 ** attempt
                    logger.warning(f"xAI API call failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
        
        raise Exception("xAI API call failed after all retries")

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
            "according to", "based on", "evidence shows", "data indicates",
            "research suggests", "studies show", "confirmed by", "verified",
            "documented", "official", "endorsed by"
        ]
        
        # Low confidence indicators
        low_confidence_indicators = [
            "placeholder", "unclear", "uncertain", "might", "possibly",
            "potentially", "appears to", "seems to", "allegedly",
            "reportedly", "rumored", "unverified", "unconfirmed"
        ]
        
        # Medium confidence indicators
        medium_confidence_indicators = [
            "likely", "probably", "suggests", "indicates", "implies",
            "generally", "typically", "tends to", "expected"
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
        sentence_count = len([s for s in content.split('.') if s.strip()])
        
        # Quality indicators
        has_good_structure = sentence_count >= 3 and word_count >= 100
        has_specific_details = any(char.isdigit() for char in content)  # Contains numbers/dates
        
        # Decision logic
        if high_count >= 2 and low_count == 0 and has_good_structure:
            return ConfidenceLevel.HIGH
        elif low_count >= 2 or not has_good_structure:
            return ConfidenceLevel.LOW
        elif medium_count >= 1 or has_specific_details:
            return ConfidenceLevel.MEDIUM
        elif word_count >= 200 and sentence_count >= 5:
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

Please provide a factual, balanced summary that clearly distinguishes between verified facts and claims. Cite sources when possible and note any conflicting information.

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

Focus on factual positions and avoid interpretation or bias. If information is contradictory or unclear, note this explicitly.

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

Maintain objectivity and distinguish between facts, claims, and opinions. Organize the information logically and highlight the most important points.

Summary:
"""
