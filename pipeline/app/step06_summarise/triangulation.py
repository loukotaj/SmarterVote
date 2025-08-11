"""
Summary triangulation and consensus logic for LLM Summarization Engine.

This module handles the 2-of-3 consensus model for building high-confidence
summaries from multiple LLM providers.
"""

import logging
from typing import Any, Dict, List, Optional

from ..schema import ConfidenceLevel, Summary

logger = logging.getLogger(__name__)


class SummaryTriangulator:
    """Handles triangulation and consensus building from multiple LLM summaries."""

    def triangulate_summaries(self, summaries: List[Summary]) -> Optional[Dict[str, Any]]:
        """
        Implement 2-of-3 triangulation logic for consensus building.

        TODO: Implement sophisticated consensus algorithms:
        - Semantic similarity scoring between responses
        - Weighted voting based on provider reliability
        - Confidence interval calculation for consensus
        - Minority opinion preservation and analysis
        - Cross-validation with external fact-checking
        - Temporal consistency tracking across updates
        - Bias detection and mitigation strategies
        - Quality scoring for individual summaries
        """
        if len(summaries) < 2:
            logger.warning("Insufficient summaries for triangulation (need at least 2)")
            return None

        logger.info(f"Triangulating {len(summaries)} summaries for consensus")

        # Group summaries by confidence level
        confidence_groups = {}
        for summary in summaries:
            conf_level = summary.confidence
            if conf_level not in confidence_groups:
                confidence_groups[conf_level] = []
            confidence_groups[conf_level].append(summary)

        # Determine overall confidence based on agreement
        overall_confidence = self._determine_consensus_confidence(confidence_groups)

        # Build consensus summary
        consensus_summary = self._build_consensus_summary(summaries)

        # Track provider agreement
        provider_agreement = self._analyze_provider_agreement(summaries)

        triangulated_result = {
            "consensus_summary": consensus_summary,
            "consensus_confidence": overall_confidence,
            "overall_confidence": overall_confidence,  # Backwards compatibility
            "consensus_method": self._determine_consensus_method(confidence_groups),
            "total_summaries": len(summaries),
            "models_used": [summary.model for summary in summaries],
            "provider_count": len(summaries),
            "provider_agreement": provider_agreement,
            "confidence_distribution": {conf.value: len(summaries_list) for conf, summaries_list in confidence_groups.items()},
            "source_summaries": [
                {
                    "provider": summary.model,
                    "confidence": summary.confidence.value,
                    "summary": summary.content[:500],  # Truncate for storage
                    "sources": summary.source_ids,
                }
                for summary in summaries
            ],
        }

        logger.info(f"Triangulation complete: {overall_confidence.value} confidence")
        return triangulated_result

    def _determine_consensus_confidence(self, confidence_groups: Dict[ConfidenceLevel, List[Summary]]) -> ConfidenceLevel:
        """Determine overall confidence based on provider agreement."""
        if not confidence_groups:
            return ConfidenceLevel.UNKNOWN

        # Count votes for each confidence level
        confidence_counts = {conf: len(summaries) for conf, summaries in confidence_groups.items()}

        # Sort by count (most votes first)
        sorted_confidence = sorted(confidence_counts.items(), key=lambda x: x[1], reverse=True)

        most_common_confidence, most_common_count = sorted_confidence[0]

        # Consensus rules
        total_summaries = sum(confidence_counts.values())

        if total_summaries >= 3:
            # For 3+ summaries: need majority agreement
            if most_common_count >= 2:
                # 2+ providers agree on confidence level
                return most_common_confidence
            else:
                # No clear majority - use conservative approach
                return ConfidenceLevel.MEDIUM

        elif total_summaries == 2:
            # For 2 summaries: average the confidence levels
            if most_common_count == 2:
                # Both agree
                return most_common_confidence
            else:
                # They disagree - return middle ground
                confidence_levels = list(confidence_counts.keys())
                if ConfidenceLevel.HIGH in confidence_levels and ConfidenceLevel.LOW in confidence_levels:
                    return ConfidenceLevel.MEDIUM
                elif ConfidenceLevel.HIGH in confidence_levels:
                    return ConfidenceLevel.MEDIUM
                elif ConfidenceLevel.LOW in confidence_levels:
                    return ConfidenceLevel.LOW
                else:
                    return ConfidenceLevel.MEDIUM

        else:
            # Single summary
            return most_common_confidence

    def _determine_consensus_method(self, confidence_groups: Dict[ConfidenceLevel, List[Summary]]) -> str:
        """Determine the method used for consensus building."""
        if not confidence_groups:
            return "unknown"

        confidence_counts = {conf: len(summaries) for conf, summaries in confidence_groups.items()}
        sorted_confidence = sorted(confidence_counts.items(), key=lambda x: x[1], reverse=True)
        most_common_confidence, most_common_count = sorted_confidence[0]
        total_summaries = sum(confidence_counts.values())

        if total_summaries >= 3 and most_common_count >= 2:
            return f"majority-{most_common_confidence.value.lower()}"
        elif total_summaries == 2 and most_common_count == 2:
            return f"unanimous-{most_common_confidence.value.lower()}"
        else:
            # When there's no clear majority, we default to medium confidence
            # so the method should reflect "majority-medium"
            return "majority-medium"

    def _build_consensus_summary(self, summaries: List[Summary]) -> str:
        """Build a consensus summary from multiple provider responses."""
        if not summaries:
            return "No summaries available for consensus building."

        if len(summaries) == 1:
            return summaries[0].content

        # For multiple summaries, create a combined summary
        # TODO: Implement sophisticated summary fusion
        summary_texts = [s.content for s in summaries if s.content]

        if not summary_texts:
            return "No valid summary text available."

        # Simple approach: concatenate with provider attribution
        consensus_parts = []
        for i, summary in enumerate(summaries):
            provider = summary.model
            text = summary.content[:1000]  # Limit length

            if len(summaries) > 1:
                consensus_parts.append(f"[{provider}]: {text}")
            else:
                consensus_parts.append(text)

        consensus_text = "\n\n".join(consensus_parts)

        # Add consensus metadata
        provider_list = [s.model for s in summaries]
        consensus_header = f"Consensus summary from {len(summaries)} providers ({', '.join(provider_list)}):\n\n"

        return consensus_header + consensus_text

    def _analyze_provider_agreement(self, summaries: List[Summary]) -> Dict[str, Any]:
        """Analyze agreement levels between different providers."""
        if len(summaries) < 2:
            return {"agreement_score": 1.0, "analysis": "Single provider, no comparison possible"}

        # Count confidence level agreement
        confidence_levels = [s.confidence for s in summaries]
        unique_confidences = set(confidence_levels)

        confidence_agreement = 1.0 - (len(unique_confidences) - 1) / len(summaries)

        # Analyze summary length consistency
        summary_lengths = [len(s.content) for s in summaries if s.content]
        if summary_lengths:
            avg_length = sum(summary_lengths) / len(summary_lengths)
            length_variance = sum((length - avg_length) ** 2 for length in summary_lengths) / len(summary_lengths)
            length_consistency = max(0.0, 1.0 - (length_variance / (avg_length**2)) if avg_length > 0 else 0.0)
        else:
            length_consistency = 0.0

        # Overall agreement score (simple average for now)
        overall_agreement = (confidence_agreement + length_consistency) / 2

        return {
            "agreement_score": round(overall_agreement, 3),
            "confidence_agreement": round(confidence_agreement, 3),
            "length_consistency": round(length_consistency, 3),
            "provider_count": len(summaries),
            "confidence_distribution": {conf.value: confidence_levels.count(conf) for conf in unique_confidences},
            "analysis": self._generate_agreement_analysis(confidence_agreement, length_consistency, summaries),
        }

    def _generate_agreement_analysis(
        self, confidence_agreement: float, length_consistency: float, summaries: List[Summary]
    ) -> str:
        """Generate human-readable analysis of provider agreement."""
        analysis_parts = []

        # Confidence agreement analysis
        if confidence_agreement >= 0.8:
            analysis_parts.append("High confidence agreement between providers")
        elif confidence_agreement >= 0.5:
            analysis_parts.append("Moderate confidence agreement between providers")
        else:
            analysis_parts.append("Low confidence agreement between providers")

        # Length consistency analysis
        if length_consistency >= 0.8:
            analysis_parts.append("consistent summary lengths")
        elif length_consistency >= 0.5:
            analysis_parts.append("somewhat consistent summary lengths")
        else:
            analysis_parts.append("variable summary lengths")

        # Provider diversity
        providers = [s.model for s in summaries]
        unique_providers = set(providers)
        analysis_parts.append(f"{len(unique_providers)} unique providers")

        return "; ".join(analysis_parts) + "."
