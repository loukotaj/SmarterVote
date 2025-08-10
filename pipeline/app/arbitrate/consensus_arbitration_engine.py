"""
LLM Response Arbitration Engine for SmarterVote Pipeline

This module handles the triangulation and arbitration of multiple LLM responses
to create high-confidence summaries. Implements the 2-of-3 consensus model
for determining final content.

TODO: Implement the following features:
- [ ] Add sophisticated similarity scoring algorithms for text comparison
- [ ] Implement weighted consensus based on model reliability scores
- [ ] Add fact-checking integration to validate claims
- [ ] Support for handling edge cases where no consensus is reached
- [ ] Add bias detection and mitigation in consensus building
- [ ] Implement confidence scoring based on source quality and agreement
- [ ] Add support for partial consensus on different aspects
- [ ] Support for escalation to human review when needed
- [ ] Add audit trails for arbitration decisions
- [ ] Implement learning from feedback to improve arbitration
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List

from ..schema import ConfidenceLevel, LLMResponse, Summary, TriangulatedSummary

logger = logging.getLogger(__name__)


class ConsensusArbitrationEngine:
    """Engine for arbitrating between multiple LLM responses using consensus."""

    def __init__(self):
        self.confidence_thresholds = {
            "high": 0.8,  # 2+ models strongly agree
            "medium": 0.6,  # 2+ models somewhat agree
            "low": 0.4,  # Significant disagreement
        }

        # Model reliability weights (can be adjusted based on performance)
        self.model_weights = {"gpt-4o": 1.0, "claude-3.5": 1.0, "grok-4": 1.0}

        # Similarity thresholds for consensus detection
        self.similarity_thresholds = {
            "high_agreement": 0.8,
            "moderate_agreement": 0.6,
            "low_agreement": 0.4,
        }

    async def arbitrate_summaries(
        self, summaries: List[Summary], context: Dict[str, Any] | None = None
    ) -> TriangulatedSummary:
        """
        Arbitrate between multiple LLM summaries to create consensus.

        Args:
            summaries: List of summaries from different LLMs
            context: Additional context for arbitration

        Returns:
            TriangulatedSummary with final content and confidence

        TODO:
        - [ ] Add support for different arbitration strategies
        - [ ] Implement topic-specific arbitration rules
        - [ ] Add handling for contradictory information
        - [ ] Support for preserving minority viewpoints when relevant
        """
        logger.info(f"Arbitrating {len(summaries)} summaries")

        if len(summaries) == 0:
            return self._create_empty_result("No summaries to arbitrate")

        if len(summaries) == 1:
            return self._create_single_result(summaries[0])

        # Calculate pairwise similarities
        similarity_matrix = self._calculate_similarity_matrix(summaries)

        # Find groups of agreeing summaries
        consensus_groups = self._find_consensus_groups(summaries, similarity_matrix)

        # Implement 2-of-3 consensus: select largest agreeing group if it has 2+
        top_group = max(consensus_groups, key=len) if consensus_groups else []

        if len(top_group) >= 2:
            result = await self._create_consensus_result(top_group, summaries)

            # Note if there are dissenting opinions
            other_groups = len(consensus_groups) - 1
            if other_groups > 0:
                result.arbitration_notes += f". Note: {other_groups} alternative viewpoint(s) detected"
                if result.confidence == ConfidenceLevel.HIGH:
                    result.confidence = ConfidenceLevel.MEDIUM
        else:
            result = await self._handle_no_consensus(summaries)

        logger.info(f"Arbitration complete - confidence: {result.confidence}")
        return result

    def _calculate_similarity_matrix(self, summaries: List[Summary]) -> List[List[float]]:
        """
        Calculate similarity matrix between all summary pairs.

        TODO:
        - [ ] Add semantic similarity using embeddings
        - [ ] Implement topic-specific similarity metrics
        - [ ] Add handling for different summary structures
        - [ ] Support for multilingual similarity comparison
        """
        n = len(summaries)
        matrix = [[0.0 for _ in range(n)] for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                similarity = self._calculate_text_similarity(summaries[i].content, summaries[j].content)
                matrix[i][j] = similarity
                matrix[j][i] = similarity  # Symmetric matrix

        return matrix

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two text summaries.

        TODO:
        - [ ] Implement more sophisticated similarity metrics
        - [ ] Add semantic similarity using sentence transformers
        - [ ] Consider factual accuracy vs. stylistic differences
        - [ ] Add domain-specific similarity scoring
        """
        # Clean and normalize texts
        clean_text1 = self._clean_text_for_comparison(text1)
        clean_text2 = self._clean_text_for_comparison(text2)

        # Basic sequence similarity
        sequence_sim = SequenceMatcher(None, clean_text1, clean_text2).ratio()

        # Word overlap similarity
        words1_list = clean_text1.lower().split()
        words2_list = clean_text2.lower().split()
        words1 = set(words1_list)
        words2 = set(words2_list)

        if len(words1) == 0 and len(words2) == 0:
            word_sim = 1.0
        elif len(words1) == 0 or len(words2) == 0:
            word_sim = 0.0
        else:
            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))
            word_sim = intersection / union if union > 0 else 0.0

        # Bigram overlap similarity for additional context
        bigrams1 = {tuple(words1_list[i : i + 2]) for i in range(len(words1_list) - 1)}
        bigrams2 = {tuple(words2_list[i : i + 2]) for i in range(len(words2_list) - 1)}

        if len(bigrams1) == 0 and len(bigrams2) == 0:
            bigram_sim = 1.0
        elif len(bigrams1) == 0 or len(bigrams2) == 0:
            bigram_sim = 0.0
        else:
            bigram_intersection = len(bigrams1.intersection(bigrams2))
            bigram_union = len(bigrams1.union(bigrams2))
            bigram_sim = bigram_intersection / bigram_union if bigram_union > 0 else 0.0

        # Combine similarities (weighted average)
        combined_similarity = 0.2 * sequence_sim + 0.4 * word_sim + 0.4 * bigram_sim

        return combined_similarity

    def _clean_text_for_comparison(self, text: str) -> str:
        """
        Clean text for more accurate similarity comparison.

        TODO:
        - [ ] Add more sophisticated text normalization
        - [ ] Remove model-specific formatting and signatures
        - [ ] Standardize political terminology and names
        """
        # Remove common LLM signatures/headers
        patterns_to_remove = [
            r"\[.*?\]",  # Remove [Model Name] headers
            r"Summary:?\s*",  # Remove "Summary:" headers
            r"Analysis:?\s*",  # Remove "Analysis:" headers
        ]

        cleaned = text
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Normalize whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    def _detect_bias(self, text: str) -> float:
        """Return a simple bias score based on loaded terms in text."""
        bias_terms = {
            "liberal",
            "conservative",
            "left-wing",
            "right-wing",
            "radical",
            "extremist",
            "biased",
        }
        lowered = text.lower()
        count = sum(lowered.count(term) for term in bias_terms)
        total_words = len(lowered.split())
        return count / total_words if total_words else 0.0

    def _find_consensus_groups(self, summaries: List[Summary], similarity_matrix: List[List[float]]) -> List[List[int]]:
        """
        Find groups of summaries that agree with each other.

        TODO:
        - [ ] Implement more sophisticated clustering algorithms
        - [ ] Add support for hierarchical clustering
        - [ ] Consider model reliability in grouping
        - [ ] Add dynamic threshold adjustment
        """
        n = len(summaries)
        groups = []
        assigned = [False] * n

        for i in range(n):
            if assigned[i]:
                continue

            # Start new group with current summary
            group = [i]
            assigned[i] = True

            # Find similar summaries
            for j in range(i + 1, n):
                if assigned[j]:
                    continue

                # Check if j is similar to any summary in current group
                max_similarity = max(similarity_matrix[idx][j] for idx in group)

                if max_similarity >= self.similarity_thresholds["moderate_agreement"]:
                    group.append(j)
                    assigned[j] = True

            groups.append(group)

        return groups

    async def _create_consensus_result(self, consensus_indices: List[int], summaries: List[Summary]) -> TriangulatedSummary:
        """
        Create result from a consensus group.

        TODO:
        - [ ] Implement intelligent content merging
        - [ ] Add fact verification for consensus claims
        - [ ] Support for preserving different perspectives
        - [ ] Add source attribution in merged content
        """
        consensus_summaries = [summaries[i] for i in consensus_indices]

        # Calculate weighted model confidence
        total_weight = sum(self.model_weights.get(s.model, 1.0) for s in consensus_summaries)
        weighted_confidence = (
            sum(self.model_weights.get(s.model, 1.0) * self._confidence_to_float(s.confidence) for s in consensus_summaries)
            / total_weight
            if total_weight > 0
            else 0.5
        )

        # Average pairwise similarity within the consensus group
        pairwise_sim = 0.0
        comparisons = 0
        for i in range(len(consensus_summaries)):
            for j in range(i + 1, len(consensus_summaries)):
                pairwise_sim += self._calculate_text_similarity(consensus_summaries[i].content, consensus_summaries[j].content)
                comparisons += 1
        pairwise_sim = pairwise_sim / comparisons if comparisons else 1.0

        # Basic bias detection - penalise confidence if biased language present
        bias_score = max(self._detect_bias(s.content) for s in consensus_summaries)

        confidence_score = 0.5 * weighted_confidence + 0.5 * pairwise_sim
        confidence_score = max(0, confidence_score * (1 - bias_score))

        # Merge content (simple approach - use longest/most detailed)
        merged_content = max(consensus_summaries, key=lambda s: len(s.content)).content

        if confidence_score >= self.confidence_thresholds["high"]:
            confidence = ConfidenceLevel.HIGH
        elif confidence_score >= self.confidence_thresholds["medium"]:
            confidence = ConfidenceLevel.MEDIUM if len(consensus_summaries) >= 2 else ConfidenceLevel.LOW
        else:
            confidence = ConfidenceLevel.LOW

        notes = f"Consensus reached with {len(consensus_summaries)} models"
        if bias_score > 0:
            notes += "; potential bias detected"

        return TriangulatedSummary(
            final_content=merged_content,
            confidence=confidence,
            llm_responses=[self._summary_to_llm_response(s) for s in consensus_summaries],
            consensus_method="2-of-3" if len(consensus_summaries) >= 2 else "single",
            arbitration_notes=notes,
        )

    async def _handle_disagreement(self, consensus_groups: List[List[int]], summaries: List[Summary]) -> TriangulatedSummary:
        """
        Handle case where there are multiple competing viewpoints.

        TODO:
        - [ ] Add intelligent conflict resolution
        - [ ] Implement fact-checking to resolve disagreements
        - [ ] Support for preserving multiple valid perspectives
        - [ ] Add escalation to human review
        """
        logger.warning("Multiple consensus groups found - handling disagreement")

        # Find largest consensus group
        largest_group = max(consensus_groups, key=len)
        largest_summaries = [summaries[i] for i in largest_group]

        # Create result from largest group but with lower confidence
        result = await self._create_consensus_result(largest_group, summaries)

        # Lower confidence due to disagreement
        if result.confidence == ConfidenceLevel.HIGH:
            result.confidence = ConfidenceLevel.MEDIUM
        else:
            result.confidence = ConfidenceLevel.LOW

        # Add note about disagreement
        other_groups_count = len(consensus_groups) - 1
        result.arbitration_notes += f". Note: {other_groups_count} alternative viewpoint(s) detected"

        return result

    async def _handle_no_consensus(self, summaries: List[Summary]) -> TriangulatedSummary:
        """
        Handle case where no clear consensus exists.

        TODO:
        - [ ] Add fallback strategies for no consensus
        - [ ] Implement human escalation process
        - [ ] Add support for presenting multiple viewpoints
        - [ ] Consider external fact-checking sources
        """
        logger.warning("No consensus found among summaries")

        # Use highest-weighted model's result
        best_summary = max(summaries, key=lambda s: self.model_weights.get(s.model, 1.0))

        note = "No consensus reached - using best single model result"
        if self._detect_bias(best_summary.content) > 0:
            note += "; potential bias detected"

        return TriangulatedSummary(
            final_content=best_summary.content,
            confidence=ConfidenceLevel.LOW,
            llm_responses=[self._summary_to_llm_response(s) for s in summaries],
            consensus_method="fallback_best_model",
            arbitration_notes=note,
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

    def _confidence_to_float(self, confidence: ConfidenceLevel) -> float:
        """Convert confidence level to float for calculations."""
        mapping = {
            ConfidenceLevel.HIGH: 0.9,
            ConfidenceLevel.MEDIUM: 0.7,
            ConfidenceLevel.LOW: 0.3,
            ConfidenceLevel.UNKNOWN: 0.1,
        }
        return mapping.get(confidence, 0.5)

    async def validate_arbitration_quality(self, result: TriangulatedSummary) -> Dict[str, Any]:
        """
        Validate the quality of arbitration result.

        TODO:
        - [ ] Add comprehensive quality metrics
        - [ ] Implement fact-checking validation
        - [ ] Add bias detection
        - [ ] Support for domain-specific validation
        """
        quality_metrics = {
            "consensus_strength": len(result.llm_responses) / 3.0,  # Assuming max 3 models
            "confidence_score": self._confidence_to_float(result.confidence),
            "content_length": len(result.final_content),
            "has_consensus": len(result.llm_responses) >= 2,
            "arbitration_method": result.consensus_method,
        }

        return quality_metrics

    def _get_model_name(self, summary: Summary) -> str:
        """Extract model name from summary metadata."""
        return summary.metadata.get("model", "unknown") if summary.metadata else "unknown"
