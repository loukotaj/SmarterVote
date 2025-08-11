"""
AI-Driven LLM Response Arbitration Engine for SmarterVote Pipeline

This module handles the triangulation and arbitration of multiple LLM responses
to create high-confidence summaries. Uses AI calls instead of heuristics for:
- Bias detection
- Agreement level analysis
- Final consensus summary generation

Implements the 2-of-3 consensus model for determining final content.
Uses the provider registry system for easy model switching.
"""

import json
import logging
import random
from datetime import datetime
from typing import Any, Dict, List

from ..providers import TaskType, registry
from ..schema import ConfidenceLevel, LLMResponse, Summary, TriangulatedSummary

logger = logging.getLogger(__name__)


class ConsensusArbitrationEngine:
    """AI-driven engine for arbitrating between multiple LLM responses using AI analysis."""

    def __init__(self, cheap_mode: bool = True):
        """Initialize the arbitration engine with provider registry."""
        self.cheap_mode = cheap_mode

        # Log available providers for arbitration
        providers = registry.list_providers()
        logger.info(f"⚖️  Available AI providers for arbitration: {', '.join(providers)}")

        # Get enabled models for arbitration
        enabled_models = registry.get_enabled_models(TaskType.ARBITRATE)
        logger.info(f"📊 Enabled models for arbitration: {len(enabled_models)}")

        for model in enabled_models:
            logger.info(f"  - {model.provider}/{model.model_id} ({model.tier.value})")

    async def close(self):
        """Close any resources (kept for compatibility)."""
        pass

    async def arbitrate_summaries(self, all_summaries: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Arbitrate between multiple LLM summaries using AI analysis.

        Args:
            all_summaries: Dictionary containing race_summaries, candidate_summaries, issue_summaries
            context: Additional context for arbitration

        Returns:
            Dictionary with consensus_data and arbitrated_summaries
        """
        logger.info(f"AI-driven arbitrating summaries from all categories")

        # Extract all summaries from the dictionary structure
        race_summaries = all_summaries.get("race_summaries", [])
        candidate_summaries = all_summaries.get("candidate_summaries", [])
        issue_summaries = all_summaries.get("issue_summaries", [])

        # Combine all summaries for arbitration
        all_summary_list = race_summaries + candidate_summaries + issue_summaries
        total_summaries = len(all_summary_list)

        logger.info(
            f"Total summaries to arbitrate: {total_summaries} ({len(race_summaries)} race, {len(candidate_summaries)} candidate, {len(issue_summaries)} issue)"
        )

        if total_summaries == 0:
            return self._create_empty_arbitrated_result("No summaries to arbitrate")

        # Arbitrate each category separately and combine results
        arbitrated_summaries = []

        # Arbitrate race summaries
        if race_summaries:
            race_result = await self._arbitrate_summary_list(race_summaries, context)
            if race_result.final_content:
                arbitrated_summaries.append(
                    {
                        "query_type": "race_summary",
                        "content": race_result.final_content,
                        "confidence": race_result.confidence.value.lower(),
                        "consensus_method": race_result.consensus_method,
                        "arbitration_notes": race_result.arbitration_notes,
                    }
                )

        # Arbitrate candidate summaries
        if candidate_summaries:
            candidate_result = await self._arbitrate_summary_list(candidate_summaries, context)
            if candidate_result.final_content:
                arbitrated_summaries.append(
                    {
                        "query_type": "candidate_summary",
                        "content": candidate_result.final_content,
                        "confidence": candidate_result.confidence.value.lower(),
                        "consensus_method": candidate_result.consensus_method,
                        "arbitration_notes": candidate_result.arbitration_notes,
                    }
                )

        # Arbitrate issue summaries
        if issue_summaries:
            issue_result = await self._arbitrate_summary_list(issue_summaries, context)
            if issue_result.final_content:
                arbitrated_summaries.append(
                    {
                        "query_type": "issue_summary",
                        "content": issue_result.final_content,
                        "confidence": issue_result.confidence.value.lower(),
                        "consensus_method": issue_result.consensus_method,
                        "arbitration_notes": issue_result.arbitration_notes,
                    }
                )

        # Create consensus data (can be expanded with metadata)
        consensus_data = {
            "total_summaries_arbitrated": total_summaries,
            "arbitration_timestamp": datetime.utcnow().isoformat() + "Z",
            "arbitration_method": "ai_driven_consensus",
        }

        return {"consensus_data": consensus_data, "arbitrated_summaries": arbitrated_summaries}

    async def _arbitrate_summary_list(self, summaries: List[Summary], context: Dict[str, Any] = None) -> TriangulatedSummary:
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
            return self._create_empty_triangulated_result("No summaries to arbitrate")

        if len(summaries) == 1:
            return self._create_single_result(summaries[0])

        # Get available arbitration models
        model_pairs = registry.get_triangulation_models(TaskType.ARBITRATE)

        if not model_pairs:
            logger.warning("No AI models available for arbitration, falling back to simple selection")
            return await self._fallback_arbitration(summaries)

        try:
            # Step 1: Use AI to analyze bias in all summaries
            bias_analysis = await self._ai_detect_bias(summaries, model_pairs)

            # Step 2: Use AI to determine agreement levels between summaries
            agreement_analysis = await self._ai_analyze_agreement(summaries, model_pairs)

            # Step 3: Use AI to generate final consensus summary
            final_summary = await self._ai_generate_consensus(
                summaries, bias_analysis, agreement_analysis, model_pairs, context
            )

            return final_summary

        except Exception as e:
            logger.error(f"AI arbitration failed: {e}")
            # Fallback to simple selection if AI arbitration fails
            return await self._fallback_arbitration(summaries)

    async def _ai_detect_bias(self, summaries: List[Summary], model_pairs: List[tuple]) -> Dict[str, Any]:
        """
        Use AI to detect bias in the provided summaries.

        Returns:
            Dict with bias analysis for each summary
        """

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
            provider, model_config = random.choice(model_pairs)

            # Generate using provider
            result_content = await provider.generate(bias_prompt, model_config)

            # Parse JSON response
            bias_data = json.loads(result_content)

            return bias_data

        except Exception as e:
            logger.warning(f"AI bias detection failed: {e}")
            # Return empty analysis if AI fails
            return {
                "bias_scores": [
                    {"summary_index": i, "bias_level": "unknown", "severity": "low"} for i in range(len(summaries))
                ]
            }

    async def _ai_analyze_agreement(self, summaries: List[Summary], model_pairs: List[tuple]) -> Dict[str, Any]:
        """
        Use AI to analyze agreement levels between summaries.

        Returns:
            Dict with agreement analysis
        """

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
            # Select random AI model for agreement analysis
            provider, model_config = random.choice(model_pairs)

            # Generate using provider
            result_content = await provider.generate(agreement_prompt, model_config)

            # Parse JSON response
            agreement_data = json.loads(result_content)

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
        model_pairs: List[tuple],
        context: Dict[str, Any] = None,
    ) -> TriangulatedSummary:
        """
        Use AI to generate the final consensus summary.

        Returns:
            TriangulatedSummary with AI-generated consensus
        """

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
            # Select random AI model for consensus generation
            provider, model_config = random.choice(model_pairs)

            # Generate using provider
            result_content = await provider.generate(consensus_prompt, model_config)

            # Parse JSON response
            consensus_data = json.loads(result_content)

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
            arbitration_notes = f"AI-driven arbitration using {model_config.provider}/{model_config.model_id}. "
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

    def _create_empty_arbitrated_result(self, reason: str) -> Dict[str, Any]:
        """Create empty arbitrated result for error cases."""
        return {
            "consensus_data": {
                "total_summaries_arbitrated": 0,
                "arbitration_timestamp": datetime.utcnow().isoformat() + "Z",
                "arbitration_method": "error",
                "error_reason": reason,
            },
            "arbitrated_summaries": [],
        }

    def _create_empty_triangulated_result(self, reason: str) -> TriangulatedSummary:
        """Create empty triangulated result for error cases."""
        return TriangulatedSummary(
            final_content="",
            confidence=ConfidenceLevel.LOW,
            llm_responses=[],
            consensus_method="error",
            arbitration_notes=reason,
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
