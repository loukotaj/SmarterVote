"""
Arbitrate Service for SmarterVote Pipeline

This module handles confidence scoring and validation logic for processed data.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

from ..schema import Summary, ConfidenceLevel


logger = logging.getLogger(__name__)


class ArbitrateService:
    """Service for arbitrating confidence and validating data quality."""
    
    def __init__(self):
        self.confidence_thresholds = {
            "high": 0.8,
            "medium": 0.6,
            "low": 0.4
        }
    
    async def process(self, summaries: List[Summary]) -> Dict[str, Any]:
        """
        Process summaries and assign confidence scores.
        
        Args:
            summaries: List of AI-generated summaries
            
        Returns:
            Arbitrated data with confidence scores
        """
        logger.info(f"Arbitrating {len(summaries)} summaries")
        
        arbitrated_data = {
            "summaries": [],
            "overall_confidence": ConfidenceLevel.UNKNOWN,
            "arbitration_timestamp": datetime.utcnow(),
            "quality_scores": {},
            "consensus_data": {}
        }
        
        high_confidence_count = 0
        medium_confidence_count = 0
        
        for summary in summaries:
            # Calculate quality score
            quality_score = self._calculate_quality_score(summary)
            
            # Adjust confidence based on quality
            adjusted_confidence = self._adjust_confidence(summary.confidence, quality_score)
            
            # Track confidence distribution
            if adjusted_confidence == ConfidenceLevel.HIGH:
                high_confidence_count += 1
            elif adjusted_confidence == ConfidenceLevel.MEDIUM:
                medium_confidence_count += 1
            
            arbitrated_summary = {
                "original_summary": summary,
                "quality_score": quality_score,
                "adjusted_confidence": adjusted_confidence,
                "arbitration_notes": self._generate_arbitration_notes(summary, quality_score)
            }
            
            arbitrated_data["summaries"].append(arbitrated_summary)
        
        # Calculate overall confidence
        total_summaries = len(summaries)
        if total_summaries > 0:
            high_ratio = high_confidence_count / total_summaries
            medium_ratio = medium_confidence_count / total_summaries
            
            if high_ratio >= 0.7:
                arbitrated_data["overall_confidence"] = ConfidenceLevel.HIGH
            elif high_ratio + medium_ratio >= 0.6:
                arbitrated_data["overall_confidence"] = ConfidenceLevel.MEDIUM
            else:
                arbitrated_data["overall_confidence"] = ConfidenceLevel.LOW
        
        # Generate consensus data
        arbitrated_data["consensus_data"] = self._generate_consensus(summaries)
        
        logger.info(f"Arbitration complete. Overall confidence: {arbitrated_data['overall_confidence']}")
        return arbitrated_data
    
    def _calculate_quality_score(self, summary: Summary) -> float:
        """Calculate quality score for a summary."""
        score = 0.5  # Base score
        
        # Factor in content length
        word_count = len(summary.content.split())
        if 50 <= word_count <= 500:
            score += 0.2
        elif word_count < 10:
            score -= 0.3
        
        # Factor in source references
        if summary.source_references:
            score += 0.1 * min(len(summary.source_references), 3)
        
        # Factor in model confidence
        if summary.confidence == ConfidenceLevel.HIGH:
            score += 0.2
        elif summary.confidence == ConfidenceLevel.MEDIUM:
            score += 0.1
        elif summary.confidence == ConfidenceLevel.LOW:
            score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _adjust_confidence(self, original_confidence: ConfidenceLevel, quality_score: float) -> ConfidenceLevel:
        """Adjust confidence based on quality score."""
        if quality_score >= self.confidence_thresholds["high"]:
            if original_confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]:
                return ConfidenceLevel.HIGH
            else:
                return ConfidenceLevel.MEDIUM
        elif quality_score >= self.confidence_thresholds["medium"]:
            if original_confidence == ConfidenceLevel.HIGH:
                return ConfidenceLevel.MEDIUM
            elif original_confidence == ConfidenceLevel.MEDIUM:
                return ConfidenceLevel.MEDIUM
            else:
                return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.LOW
    
    def _generate_arbitration_notes(self, summary: Summary, quality_score: float) -> List[str]:
        """Generate notes about the arbitration process."""
        notes = []
        
        if quality_score >= 0.8:
            notes.append("High quality content with strong source references")
        elif quality_score >= 0.6:
            notes.append("Good quality content with adequate validation")
        elif quality_score >= 0.4:
            notes.append("Moderate quality content, use with caution")
        else:
            notes.append("Low quality content, verify independently")
        
        if not summary.source_references:
            notes.append("No source references provided")
        
        word_count = len(summary.content.split())
        if word_count < 10:
            notes.append("Content is very brief")
        elif word_count > 500:
            notes.append("Content is very lengthy")
        
        return notes
    
    def _generate_consensus(self, summaries: List[Summary]) -> Dict[str, Any]:
        """Generate consensus data from multiple summaries."""
        # TODO: Implement consensus generation logic
        # This could include:
        # - Common themes across summaries
        # - Conflicting information
        # - Most frequently mentioned topics
        
        return {
            "common_themes": [],
            "conflicts": [],
            "key_topics": [],
            "consensus_confidence": ConfidenceLevel.UNKNOWN
        }
