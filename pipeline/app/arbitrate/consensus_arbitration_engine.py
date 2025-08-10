"""
AI-Driven LLM Response Arbitration Engine for SmarterVote Pipeline

This module handles the triangulation and arbitration of multiple LLM responses
to create high-confidence summaries. Uses AI calls instead of heuristics for:
- Bias detection
- Agreement level analysis
- Final consensus summary generation

Implements the 2-of-3 consensus model for determining final content.
"""

import logging
import os
import random
from typing import Any, Dict, List

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

from ..schema import ConfidenceLevel, LLMResponse, Summary, TriangulatedSummary

logger = logging.getLogger(__name__)


class LLMAPIError(Exception):
    """Custom exception for LLM API errors during arbitration."""

    def __init__(self, provider: str, message: str, status_code: int = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} API Error: {message}")


class ConsensusArbitrationEngine:
    """AI-driven engine for arbitrating between multiple LLM responses using AI analysis."""

    def __init__(self, cheap_mode: bool = True):
        # Load API keys from environment
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.xai_api_key = os.getenv("XAI_API_KEY")

        # Set mode
        self.cheap_mode = cheap_mode

        # Available models for arbitration based on mode
        if cheap_mode:
            self.arbitration_models = {
                "openai": {
                    "model": "gpt-4o-mini",
                    "api_key": self.openai_api_key,
                    "base_url": "https://api.openai.com/v1",
                    "enabled": bool(self.openai_api_key),
                },
                "anthropic": {
                    "model": "claude-3-haiku-20240307",
                    "api_key": self.anthropic_api_key,
                    "base_url": "https://api.anthropic.com/v1",
                    "enabled": bool(self.anthropic_api_key),
                },
                "xai": {
                    "model": "grok-2-1212",  # Using available model as placeholder
                    "api_key": self.xai_api_key,
                    "base_url": "https://api.x.ai/v1",
                    "enabled": bool(self.xai_api_key),
                },
            }
        else:
            self.arbitration_models = {
                "openai": {
                    "model": "gpt-4o",
                    "api_key": self.openai_api_key,
                    "base_url": "https://api.openai.com/v1",
                    "enabled": bool(self.openai_api_key),
                },
                "anthropic": {
                    "model": "claude-3-5-sonnet-20241022",
                    "api_key": self.anthropic_api_key,
                    "base_url": "https://api.anthropic.com/v1",
                    "enabled": bool(self.anthropic_api_key),
                },
                "xai": {
                    "model": "grok-beta",
                    "api_key": self.xai_api_key,
                    "base_url": "https://api.x.ai/v1",
                    "enabled": bool(self.xai_api_key),
                },
            }

        # HTTP client for API calls
        self.http_client = httpx.AsyncClient(timeout=30.0)

        # Get enabled models for arbitration
        self.enabled_models = [name for name, config in self.arbitration_models.items() if config["enabled"]]

        if not self.enabled_models:
            logger.warning("No LLM API keys found for arbitration. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or XAI_API_KEY")

    async def close(self):
        """Close the HTTP client."""
        if hasattr(self, "http_client"):
            await self.http_client.aclose()

    async def arbitrate_summaries(self, summaries: List[Summary], context: Dict[str, Any] = None) -> TriangulatedSummary:
        """
        Arbitrate between multiple LLM summaries using AI analysis.

        Args:
            summaries: List of summaries from different LLMs
            context: Additional context for arbitration

        Returns:
            TriangulatedSummary with AI-driven final content and confidence
        """
        logger.info(f"AI-driven arbitrating {len(summaries)} summaries")

        if len(summaries) == 0:
            return self._create_empty_result("No summaries to arbitrate")

        if len(summaries) == 1:
            return self._create_single_result(summaries[0])

        if not self.enabled_models:
            logger.warning("No AI models available for arbitration, falling back to simple selection")
            return await self._fallback_arbitration(summaries)

        try:
            # Step 1: Use AI to analyze bias in all summaries
            bias_analysis = await self._ai_detect_bias(summaries)

            # Step 2: Use AI to determine agreement levels between summaries
            agreement_analysis = await self._ai_analyze_agreement(summaries)

            # Step 3: Use AI to generate final consensus summary
            final_summary = await self._ai_generate_consensus(summaries, bias_analysis, agreement_analysis, context)

            return final_summary

        except Exception as e:
            logger.error(f"AI arbitration failed: {e}")
            # Fallback to simple selection if AI arbitration fails
            return await self._fallback_arbitration(summaries)

    async def _ai_detect_bias(self, summaries: List[Summary]) -> Dict[str, Any]:
        """
        Use AI to detect bias in the provided summaries.

        Returns:
            Dict with bias analysis for each summary
        """
        logger.debug("Using AI to detect bias in summaries")

        # Create prompt for bias detection
        summaries_text = ""
        for i, summary in enumerate(summaries):
            summaries_text += f"SUMMARY {i+1} (Model: {summary.model}):\n{summary.content}\n\n"

        bias_prompt = f"""
        Analyze the following political summaries for bias. For each summary, identify:
        1. Political bias (left-leaning, right-leaning, or neutral)
        2. Loaded language or emotional terms
        3. Bias severity (low, medium, high)
        4. Specific examples of biased language if found

        Provide your analysis in JSON format with a "bias_scores" array containing an object for each summary with
        "summary_index", "bias_level", "bias_direction", "severity", and "examples" fields.

        SUMMARIES TO ANALYZE:
        {summaries_text}

        Respond only with valid JSON.
        """

        try:
            # Select random AI model for bias detection
            arbitration_result = await self._call_random_ai_model(bias_prompt)

            # Parse JSON response
            import json

            bias_data = json.loads(arbitration_result["content"])

            logger.debug(f"AI bias detection completed: {bias_data}")
            return bias_data

        except Exception as e:
            logger.warning(f"AI bias detection failed: {e}")
            # Return empty analysis if AI fails
            return {
                "bias_scores": [
                    {"summary_index": i, "bias_level": "unknown", "severity": "low"} for i in range(len(summaries))
                ]
            }

    async def _ai_analyze_agreement(self, summaries: List[Summary]) -> Dict[str, Any]:
        """
        Use AI to analyze agreement levels between summaries.

        Returns:
            Dict with agreement analysis
        """
        logger.debug("Using AI to analyze agreement between summaries")

        # Create prompt for agreement analysis
        summaries_text = ""
        for i, summary in enumerate(summaries):
            summaries_text += f"SUMMARY {i+1} (Model: {summary.model}):\n{summary.content}\n\n"

        agreement_prompt = f"""
        Analyze the agreement between these political summaries. Determine:
        1. Which summaries agree with each other (form consensus groups)
        2. The strength of agreement (high, medium, low)
        3. Key points of consensus and disagreement
        4. Overall confidence in the consensus

        Provide analysis in JSON format with:
        - "consensus_groups": array of arrays showing which summaries agree (by index)
        - "agreement_strength": overall strength (high/medium/low)
        - "consensus_points": array of agreed-upon points
        - "disagreement_points": array of points of disagreement
        - "confidence_assessment": overall confidence in consensus (high/medium/low)

        SUMMARIES TO ANALYZE:
        {summaries_text}

        Respond only with valid JSON.
        """

        try:
            arbitration_result = await self._call_random_ai_model(agreement_prompt)

            # Parse JSON response
            import json

            agreement_data = json.loads(arbitration_result["content"])

            logger.debug(f"AI agreement analysis completed: {agreement_data}")
            return agreement_data

        except Exception as e:
            logger.warning(f"AI agreement analysis failed: {e}")
            # Return simple fallback analysis
            return {
                "consensus_groups": [[0, 1]] if len(summaries) >= 2 else [[0]],
                "agreement_strength": "medium",
                "confidence_assessment": "low",
            }

    async def _ai_generate_consensus(
        self,
        summaries: List[Summary],
        bias_analysis: Dict[str, Any],
        agreement_analysis: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> TriangulatedSummary:
        """
        Use AI to generate the final consensus summary.

        Returns:
            TriangulatedSummary with AI-generated consensus
        """
        logger.debug("Using AI to generate consensus summary")

        # Create context for consensus generation
        summaries_text = ""
        for i, summary in enumerate(summaries):
            summaries_text += f"SUMMARY {i+1} (Model: {summary.model}):\n{summary.content}\n\n"

        # Include analysis context
        consensus_prompt = f"""
        Based on the following summaries and analysis, generate a final consensus summary that:
        1. Incorporates the most reliable and agreed-upon information
        2. Avoids biased language identified in the analysis
        3. Reflects the strength of consensus found
        4. Maintains political neutrality and factual accuracy

        ORIGINAL SUMMARIES:
        {summaries_text}

        BIAS ANALYSIS:
        {bias_analysis}

        AGREEMENT ANALYSIS:
        {agreement_analysis}

        Generate a final consensus summary that synthesizes the best elements while avoiding bias.
        The summary should be comprehensive but concise, focusing on factual information and policy positions.

        Also determine the appropriate confidence level (HIGH, MEDIUM, LOW) based on:
        - Strength of agreement between models
        - Absence of bias
        - Quality of source consensus

        Provide response in JSON format with "final_summary" and "confidence_level" fields.
        Respond only with valid JSON.
        """

        try:
            arbitration_result = await self._call_random_ai_model(consensus_prompt)

            # Parse JSON response
            import json

            consensus_data = json.loads(arbitration_result["content"])

            final_content = consensus_data.get("final_summary", "")
            confidence_str = consensus_data.get("confidence_level", "MEDIUM").upper()

            # Convert confidence string to enum
            confidence_mapping = {"HIGH": ConfidenceLevel.HIGH, "MEDIUM": ConfidenceLevel.MEDIUM, "LOW": ConfidenceLevel.LOW}
            confidence = confidence_mapping.get(confidence_str, ConfidenceLevel.MEDIUM)

            # Determine consensus method based on agreement analysis
            consensus_groups = agreement_analysis.get("consensus_groups", [])
            consensus_method = "ai_arbitrated"
            if consensus_groups and len(max(consensus_groups, key=len)) >= 2:
                consensus_method = "ai_2_of_3_consensus"

            # Create arbitration notes
            arbitration_notes = f"AI-driven arbitration using {arbitration_result.get('model', 'AI')}. "
            arbitration_notes += f"Agreement strength: {agreement_analysis.get('agreement_strength', 'unknown')}"

            # Add bias warnings if detected
            bias_scores = bias_analysis.get("bias_scores", [])
            high_bias_count = sum(1 for score in bias_scores if score.get("severity") == "high")
            if high_bias_count > 0:
                arbitration_notes += f". Warning: {high_bias_count} summaries showed high bias"
                if confidence == ConfidenceLevel.HIGH:
                    confidence = ConfidenceLevel.MEDIUM  # Downgrade confidence

            return TriangulatedSummary(
                final_content=final_content,
                confidence=confidence,
                llm_responses=[self._summary_to_llm_response(s) for s in summaries],
                consensus_method=consensus_method,
                arbitration_notes=arbitration_notes,
            )

        except Exception as e:
            logger.error(f"AI consensus generation failed: {e}")
            # Fallback to selecting best summary
            best_summary = max(summaries, key=lambda s: len(s.content))
            return TriangulatedSummary(
                final_content=best_summary.content,
                confidence=ConfidenceLevel.LOW,
                llm_responses=[self._summary_to_llm_response(s) for s in summaries],
                consensus_method="ai_fallback",
                arbitration_notes=f"AI consensus failed, using fallback: {str(e)[:100]}",
            )

    async def _call_random_ai_model(self, prompt: str) -> Dict[str, Any]:
        """
        Call a random available AI model for arbitration tasks.

        Returns:
            Dict with response content and metadata
        """
        if not self.enabled_models:
            raise LLMAPIError("no_models", "No AI models available for arbitration")

        # Select random model for arbitration
        selected_provider = random.choice(self.enabled_models)
        config = self.arbitration_models[selected_provider]

        logger.debug(f"Using {selected_provider} for arbitration AI call")

        # Call the appropriate API
        if selected_provider == "openai":
            result = await self._call_openai_api(config, prompt)
        elif selected_provider == "anthropic":
            result = await self._call_anthropic_api(config, prompt)
        elif selected_provider == "xai":
            result = await self._call_xai_api(config, prompt)
        else:
            raise LLMAPIError(selected_provider, f"Unknown provider: {selected_provider}")

        result["model"] = config["model"]
        result["provider"] = selected_provider
        return result

    async def _call_openai_api(self, config: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Call OpenAI API for arbitration."""
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.1,  # Low temperature for consistent arbitration
        }

        response = await self.http_client.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        data = response.json()

        if "choices" not in data or not data["choices"]:
            raise ValueError("No choices in OpenAI response")

        return {
            "content": data["choices"][0]["message"]["content"],
            "tokens_used": data.get("usage", {}).get("total_tokens", 0),
        }

    async def _call_anthropic_api(self, config: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Call Anthropic API for arbitration."""
        headers = {
            "x-api-key": config["api_key"],
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": config["model"],
            "max_tokens": 2000,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = await self.http_client.post(
            f"{config['base_url']}/messages",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        data = response.json()

        if "content" not in data or not data["content"]:
            raise ValueError("No content in Anthropic response")

        return {
            "content": data["content"][0]["text"],
            "tokens_used": data.get("usage", {}).get("output_tokens", 0) + data.get("usage", {}).get("input_tokens", 0),
        }

    async def _call_xai_api(self, config: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Call xAI API for arbitration."""
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.1,
        }

        response = await self.http_client.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        data = response.json()

        if "choices" not in data or not data["choices"]:
            raise ValueError("No choices in xAI response")

        return {
            "content": data["choices"][0]["message"]["content"],
            "tokens_used": data.get("usage", {}).get("total_tokens", 0),
        }

    async def _fallback_arbitration(self, summaries: List[Summary]) -> TriangulatedSummary:
        """
        Simple fallback arbitration when AI is not available.
        """
        logger.warning("Using fallback arbitration without AI")

        # Simple heuristic: pick the longest summary as it's likely most detailed
        best_summary = max(summaries, key=lambda s: len(s.content))

        return TriangulatedSummary(
            final_content=best_summary.content,
            confidence=ConfidenceLevel.LOW,
            llm_responses=[self._summary_to_llm_response(s) for s in summaries],
            consensus_method="fallback_longest",
            arbitration_notes="Fallback arbitration used due to AI unavailability",
        )

    def _create_empty_result(self, reason: str) -> TriangulatedSummary:
        """Create empty result for error cases."""
        return TriangulatedSummary(
            final_content="",
            confidence=ConfidenceLevel.LOW,
            llm_responses=[],
            consensus_method="error",
            arbitration_notes=reason,
        )

    def _create_single_result(self, summary: Summary) -> TriangulatedSummary:
        """Create result from single summary."""
        return TriangulatedSummary(
            final_content=summary.content,
            confidence=summary.confidence,
            llm_responses=[self._summary_to_llm_response(summary)],
            consensus_method="single",
            arbitration_notes="Only one summary available",
        )

    def _summary_to_llm_response(self, summary: Summary) -> LLMResponse:
        """Convert Summary to LLMResponse."""
        return LLMResponse(
            model=summary.model,
            content=summary.content,
            tokens_used=summary.tokens_used,
            created_at=summary.created_at,
        )
