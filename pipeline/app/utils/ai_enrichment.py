"""AI Enrichment Service for Content Chunks

This module provides AI-powered enrichment for content chunks before indexing,
including issue tagging, candidate linking, claim extraction, and usefulness scoring.
"""

import hashlib
import logging
from typing import Dict, List, Any, Optional
import json
import re

"""AI Enrichment Service for Content Chunks

This module provides AI-powered enrichment for content chunks before indexing,
including issue tagging, candidate linking, claim extraction, and usefulness scoring.
"""

import hashlib
import logging
from typing import Dict, List, Any, Optional
import json
import re

logger = logging.getLogger(__name__)

# Define AIAnnotations here to avoid import issues during development
try:
    from ...shared.models import AIAnnotations, CanonicalIssue
except ImportError:
    # Fallback definition for standalone testing
    class AIAnnotations:
        def __init__(self, **kwargs):
            self.issues = kwargs.get("issues", [])
            self.candidates = kwargs.get("candidates", [])
            self.stance = kwargs.get("stance", [])
            self.index_summary = kwargs.get("index_summary", "")
            self.claims = kwargs.get("claims", [])
            self.qa_pairs = kwargs.get("qa_pairs", [])
            self.usefulness = kwargs.get("usefulness", {})


def hash_claims(claims: List[Dict[str, Any]]) -> str:
    """Generate a hash from normalized claims for duplicate detection."""
    if not claims:
        return ""

    # Extract and normalize claims for hashing
    normalized_claims = []
    for claim in claims:
        if "normalized" in claim:
            # Sort and normalize text for consistent hashing
            normalized_text = claim["normalized"].lower().strip()
            # Remove extra whitespace and special characters for better deduplication
            normalized_text = re.sub(r"\s+", " ", normalized_text)
            normalized_text = re.sub(r"[^\w\s]", "", normalized_text)
            normalized_claims.append(normalized_text)

    # Sort claims for consistent ordering
    normalized_claims.sort()

    # Generate hash from sorted, normalized claims
    claims_text = "|".join(normalized_claims)
    return hashlib.md5(claims_text.encode("utf-8")).hexdigest()


def ai_enrich(content_text: str, metadata: Optional[Dict[str, Any]] = None) -> AIAnnotations:
    """
    Enrich content chunk with AI annotations.

    Args:
        content_text: The text content to enrich
        metadata: Optional metadata context for enrichment

    Returns:
        AIAnnotations object with enriched metadata
    """
    logger.debug(f"Enriching content chunk ({len(content_text)} chars)")

    # For now, implement a simplified version that can be enhanced later
    # This provides the basic structure while allowing the pipeline to work

    try:
        # Simplified issue detection using keyword matching
        detected_issues = _detect_issues(content_text)

        # Simplified candidate detection using metadata hints
        detected_candidates = _detect_candidates(content_text, metadata)

        # Generate simple stance analysis
        stance_analysis = _analyze_stance(content_text, detected_candidates, detected_issues)

        # Create index summary (simplified compression)
        index_summary = _create_index_summary(content_text)

        # Extract basic claims
        claims = _extract_claims(content_text)

        # Generate simple QA pairs
        qa_pairs = _generate_qa_pairs(content_text)

        # Calculate usefulness score
        usefulness = _calculate_usefulness(content_text, detected_issues, detected_candidates)

        return AIAnnotations(
            issues=detected_issues,
            candidates=detected_candidates,
            stance=stance_analysis,
            index_summary=index_summary,
            claims=claims,
            qa_pairs=qa_pairs,
            usefulness=usefulness,
        )

    except Exception as e:
        logger.error(f"Failed to enrich content: {e}")
        # Return minimal annotations to allow pipeline to continue
        return AIAnnotations(usefulness={"score": 0.5, "reasons": ["enrichment_failed"]})


def _detect_issues(text: str) -> List[str]:
    """Detect canonical issues mentioned in text using keyword matching."""
    issues_found = []
    text_lower = text.lower()

    # Simple keyword-based detection
    issue_keywords = {
        "Healthcare": ["health", "healthcare", "medical", "insurance", "medicare", "medicaid", "hospital"],
        "Economy": ["economy", "economic", "jobs", "employment", "unemployment", "wages", "income", "tax"],
        "Climate/Energy": ["climate", "environment", "energy", "renewable", "fossil", "carbon", "emissions"],
        "Reproductive Rights": ["abortion", "reproductive", "birth control", "contraception", "roe"],
        "Immigration": ["immigration", "immigrant", "border", "refugee", "asylum", "deportation"],
        "Guns & Safety": ["gun", "firearm", "shooting", "violence", "safety", "security", "police"],
        "Foreign Policy": ["foreign", "international", "military", "defense", "war", "diplomacy"],
        "Social Justice": ["justice", "equality", "discrimination", "civil rights", "racism", "bias"],
        "Education": ["education", "school", "teacher", "student", "university", "college"],
        "Tech & AI": ["technology", "tech", "artificial intelligence", "ai", "digital", "internet"],
        "Election Reform": ["election", "voting", "ballot", "campaign", "democracy", "reform"],
    }

    for issue, keywords in issue_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            issues_found.append(issue)

    return issues_found


def _detect_candidates(text: str, metadata: Optional[Dict[str, Any]]) -> List[str]:
    """Detect candidate names mentioned in text."""
    candidates_found = []

    # Use metadata hints if available
    if metadata:
        race_id = metadata.get("race_id", "")
        # Simple extraction from race_id patterns like "mo-senate-2024"
        if race_id:
            # This is a placeholder - in real implementation would use
            # candidate databases or NER models
            pass

    # Simple name pattern detection (placeholder)
    # In real implementation, would use NER or candidate databases
    text_words = text.split()
    potential_names = []

    for i, word in enumerate(text_words):
        # Look for capitalized words that might be names
        if word.isalpha() and word[0].isupper() and len(word) > 2:
            # Check if next word is also capitalized (likely full name)
            if i + 1 < len(text_words) and text_words[i + 1].isalpha() and text_words[i + 1][0].isupper():
                full_name = f"{word} {text_words[i + 1]}"
                potential_names.append(full_name)

    # Filter common words that aren't likely names
    common_words = {"The", "This", "That", "When", "Where", "How", "Why", "What", "Who"}
    candidates_found = [name for name in potential_names if not any(w in common_words for w in name.split())]

    # Limit to most likely candidates
    return candidates_found[:3]


def _analyze_stance(text: str, candidates: List[str], issues: List[str]) -> List[Dict[str, Any]]:
    """Analyze candidate stances on issues mentioned in text."""
    stance_analysis = []

    for candidate in candidates:
        for issue in issues:
            # Simple sentiment/position analysis
            position = "unknown"
            confidence = 0.3
            evidence = []

            # Look for candidate and issue co-occurrence
            if candidate.lower() in text.lower() and any(keyword in text.lower() for keyword in _get_issue_keywords(issue)):
                # Simple position detection
                if any(word in text.lower() for word in ["support", "favor", "for", "endorse", "promote"]):
                    position = "pro"
                    confidence = 0.6
                elif any(word in text.lower() for word in ["oppose", "against", "reject", "ban", "stop"]):
                    position = "con"
                    confidence = 0.6
                elif any(word in text.lower() for word in ["mixed", "some", "certain", "limited"]):
                    position = "mixed"
                    confidence = 0.5

                # Extract evidence snippet
                sentences = text.split(".")
                for sentence in sentences:
                    if candidate.lower() in sentence.lower() and any(
                        keyword in sentence.lower() for keyword in _get_issue_keywords(issue)
                    ):
                        evidence.append(
                            {
                                "quote": sentence.strip(),
                                "start": text.find(sentence),
                                "end": text.find(sentence) + len(sentence),
                            }
                        )
                        break

            if evidence:  # Only include if we found some evidence
                stance_analysis.append(
                    {
                        "candidate": candidate,
                        "issue": issue,
                        "position": position,
                        "confidence": confidence,
                        "evidence": evidence,
                    }
                )

    return stance_analysis


def _get_issue_keywords(issue: str) -> List[str]:
    """Get keywords for a specific issue."""
    issue_keywords = {
        "Healthcare": ["health", "healthcare", "medical", "insurance"],
        "Economy": ["economy", "economic", "jobs", "employment"],
        "Climate/Energy": ["climate", "environment", "energy"],
        "Reproductive Rights": ["abortion", "reproductive"],
        "Immigration": ["immigration", "immigrant", "border"],
        "Guns & Safety": ["gun", "firearm", "safety"],
        "Foreign Policy": ["foreign", "international", "military"],
        "Social Justice": ["justice", "equality", "discrimination"],
        "Education": ["education", "school", "teacher"],
        "Tech & AI": ["technology", "tech", "ai"],
        "Election Reform": ["election", "voting", "ballot"],
    }
    return issue_keywords.get(issue, [])


def _create_index_summary(text: str) -> str:
    """Create a compressed summary for indexing (120-180 words)."""
    # Simple extractive summarization
    sentences = [s.strip() for s in text.split(".") if s.strip()]

    if not sentences:
        return ""

    # Take first few sentences up to word limit
    summary_words = []
    target_words = 150  # Aim for middle of 120-180 range

    for sentence in sentences:
        words = sentence.split()
        if len(summary_words) + len(words) <= target_words:
            summary_words.extend(words)
        else:
            # Add partial sentence if needed
            remaining_words = target_words - len(summary_words)
            if remaining_words > 0:
                summary_words.extend(words[:remaining_words])
            break

    summary = " ".join(summary_words)

    # Ensure minimum length
    if len(summary.split()) < 50:
        return text[:800] + "..." if len(text) > 800 else text

    return summary


def _extract_claims(text: str) -> List[Dict[str, Any]]:
    """Extract and normalize claims from text."""
    claims = []

    # Simple sentence-based claim extraction
    sentences = [s.strip() for s in text.split(".") if s.strip()]

    for i, sentence in enumerate(sentences):
        # Look for declarative statements (simple heuristic)
        if len(sentence.split()) > 6 and any(
            keyword in sentence.lower()
            for keyword in ["will", "should", "must", "believes", "supports", "opposes", "plans", "proposes"]
        ):
            # Simple normalization
            normalized = sentence.lower().strip()
            # Remove extra whitespace
            normalized = re.sub(r"\s+", " ", normalized)

            claims.append(
                {
                    "quote": sentence,
                    "normalized": normalized,
                    "start": text.find(sentence),
                    "end": text.find(sentence) + len(sentence),
                }
            )

    # Limit number of claims
    return claims[:5]


def _generate_qa_pairs(text: str) -> List[Dict[str, Any]]:
    """Generate synthetic QA pairs from content."""
    qa_pairs = []

    # Simple QA generation based on content patterns
    sentences = [s.strip() for s in text.split(".") if s.strip()]

    for sentence in sentences[:3]:  # Limit to first few sentences
        if len(sentence.split()) > 8:
            # Generate simple questions
            if "support" in sentence.lower() or "oppose" in sentence.lower():
                question = (
                    f"What is the position on {sentence.split()[-3:][0] if len(sentence.split()) > 3 else 'this issue'}?"
                )
                qa_pairs.append(
                    {
                        "q": question,
                        "a": sentence,
                        "evidence_offsets": [(text.find(sentence), text.find(sentence) + len(sentence))],
                    }
                )

    return qa_pairs[:3]  # Limit to 3 QA pairs


def _calculate_usefulness(text: str, issues: List[str], candidates: List[str]) -> Dict[str, Any]:
    """Calculate usefulness score for content."""
    score = 0.0
    reasons = []

    # Base score factors
    word_count = len(text.split())

    # Word count factor
    if word_count < 20:
        score += 0.1
        reasons.append("very_short_content")
    elif word_count < 50:
        score += 0.3
        reasons.append("short_content")
    elif word_count < 200:
        score += 0.6
        reasons.append("adequate_length")
    else:
        score += 0.8
        reasons.append("substantial_content")

    # Issue relevance factor
    if issues:
        score += 0.2
        reasons.append("contains_relevant_issues")

    # Candidate mention factor
    if candidates:
        score += 0.2
        reasons.append("mentions_candidates")

    # Content quality heuristics
    sentences = text.split(".")
    if len(sentences) > 2:
        score += 0.1
        reasons.append("multi_sentence")

    # Check for substantive content keywords
    substantive_keywords = ["policy", "position", "stance", "plan", "proposal", "agenda", "platform"]
    if any(keyword in text.lower() for keyword in substantive_keywords):
        score += 0.1
        reasons.append("substantive_content")

    # Ensure score is in valid range
    score = min(1.0, max(0.0, score))

    return {"score": score, "reasons": reasons}
