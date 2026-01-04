"""Step 03: LLM Summarization using Multi-Model Triangulation

This handler queries the vector corpus and uses multiple LLMs to generate
summaries with 2-of-3 consensus for high confidence results.
"""

import logging
import time
from typing import Any, Dict, List

from pipeline.app.schema import CanonicalIssue, ExtractedContent
from shared.models import CanonicalIssue as SharedCanonicalIssue


class Step03SummariseHandler:
    """Handler for AI-powered summarization with multi-model consensus."""

    # Use canonical issues from shared models for consistency
    CANONICAL_ISSUES = [issue.value for issue in SharedCanonicalIssue]

    def __init__(self):
        self.summarization_engine = None

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """
        Generate AI summaries for race candidates.

        Payload expected:
            - race_id: str
            - race_json: dict (with candidates)
            - corpus_stats: dict (from step02)

        Options:
            - cheap_mode: bool (default True - use mini models)

        Returns:
            - summaries: dict with candidate summaries and issue stances
        """
        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        race_json = payload.get("race_json")
        corpus_stats = payload.get("corpus_stats", {})

        if not race_id:
            raise ValueError("Step03SummariseHandler: Missing 'race_id' in payload")

        if not race_json:
            raise ValueError("Step03SummariseHandler: Missing 'race_json' in payload")

        cheap_mode = options.get("cheap_mode", True)
        logger.info(f"Step03 Summarise: Processing race {race_id} (cheap_mode={cheap_mode})")

        # Extract candidates from race_json
        if isinstance(race_json, dict):
            candidates = race_json.get("candidates", [])
        else:
            candidates = getattr(race_json, "candidates", [])

        if not candidates:
            logger.warning("No candidates found in race_json")
            return {
                "race_id": race_id,
                "summaries": {},
                "status": "no_candidates",
            }

        logger.info(f"Generating summaries for {len(candidates)} candidates")

        # Initialize the summarization engine
        from pipeline.app.step03_summarise.llm_summarization_engine import LLMSummarizationEngine

        t0 = time.perf_counter()

        try:
            engine = LLMSummarizationEngine(cheap_mode=cheap_mode)

            # Validate configuration
            validation = engine.validate_configuration()
            if not validation["valid"]:
                logger.error(f"LLM configuration invalid: {validation['errors']}")
                raise RuntimeError(f"LLM configuration error: {validation['errors']}")

            # Generate summaries for each candidate
            candidate_summaries = {}
            for candidate in candidates:
                if isinstance(candidate, dict):
                    candidate_name = candidate.get("name", "Unknown")
                else:
                    candidate_name = getattr(candidate, "name", "Unknown")

                logger.info(f"Generating summary for {candidate_name}")

                try:
                    # Build content for summarization from corpus
                    content_items = await self._get_candidate_content(race_id, candidate_name)

                    if content_items:
                        # Generate summary using multi-model consensus
                        summary_result = await engine.generate_summaries(
                            race_id=race_id,
                            content=content_items,
                            summary_types=["candidates", "issues"],
                        )

                        # Extract the final summary from triangulation or raw summaries
                        candidate_summary_text = self._extract_summary_text(
                            summary_result, "candidates"
                        )

                        candidate_summaries[candidate_name] = {
                            "summary": candidate_summary_text,
                            "issues": self._extract_issue_stances(summary_result),
                            "confidence": self._extract_confidence(summary_result),
                            "sources": self._extract_sources(summary_result),
                        }
                    else:
                        logger.warning(f"No content found for {candidate_name}")
                        candidate_summaries[candidate_name] = {
                            "summary": f"Insufficient data available for {candidate_name}.",
                            "issues": {},
                            "confidence": "low",
                            "sources": [],
                        }

                except Exception as e:
                    logger.error(f"Failed to generate summary for {candidate_name}: {e}")
                    candidate_summaries[candidate_name] = {
                        "summary": "",
                        "issues": {},
                        "confidence": "low",
                        "error": str(e),
                    }

            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(f"Summarization completed in {duration_ms}ms")

            return {
                "race_id": race_id,
                "summaries": candidate_summaries,
                "api_stats": engine.get_api_statistics(),
                "duration_ms": duration_ms,
                "status": "completed",
            }

        except Exception as e:
            logger.error(f"Summarization engine error: {e}")
            return {
                "race_id": race_id,
                "summaries": {},
                "error": str(e),
                "status": "failed",
            }

    async def _get_candidate_content(self, race_id: str, candidate_name: str) -> List[ExtractedContent]:
        """Query the vector corpus for candidate-specific content."""
        logger = logging.getLogger("pipeline")

        try:
            from pipeline.app.step02_corpus.vector_database_manager import VectorDatabaseManager

            vector_db = VectorDatabaseManager()
            await vector_db.initialize()

            # Search for content mentioning this candidate using similarity search
            results = await vector_db.search_similar(
                query=f"{candidate_name} positions policies views",
                where={"race_id": race_id},
                limit=20,
            )

            # Convert VectorDocuments to ExtractedContent for the engine
            content_items = []
            for doc in results:
                content_items.append(ExtractedContent(
                    source=doc.source,
                    text=doc.content,
                    extraction_timestamp=doc.source.last_accessed,
                    language="en",
                    word_count=len(doc.content.split()),
                    metadata={
                        **doc.metadata,
                        "similarity_score": doc.similarity_score,
                    },
                ))

            logger.info(f"Found {len(content_items)} content items for {candidate_name}")
            return content_items

        except Exception as e:
            logger.warning(f"Failed to query corpus for {candidate_name}: {e}")
            return []

    def _extract_issue_stances(self, summary_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract issue stances from summary result."""
        issues = {}

        # Check for triangulated issue summaries first
        triangulation = summary_result.get("triangulation", {})
        if "issues" in triangulation:
            tri_data = triangulation["issues"]
            if hasattr(tri_data, "final_content"):
                # Parse issue stances from triangulated content
                return self._parse_issue_content(tri_data.final_content)

        # Fall back to raw issue summaries
        raw_summaries = summary_result.get("summaries", {}).get("issues", [])
        if raw_summaries:
            # Use the first summary's content
            first_summary = raw_summaries[0]
            content = getattr(first_summary, "content", str(first_summary))
            return self._parse_issue_content(content)

        # If no summaries yet, generate placeholder issues with TODO markers
        # This ensures the frontend has structure to display
        for issue in self.CANONICAL_ISSUES:
            issues[issue] = {
                "stance": "Position analysis pending - run full summarization",
                "summary": "",
                "confidence": "low",
            }
        return issues

    def _parse_issue_content(self, content: str) -> Dict[str, Any]:
        """Parse issue content into structured stance data.

        This attempts to extract actual stance information from LLM-generated
        content. First tries to parse as JSON (from structured prompt), then
        falls back to keyword-based extraction.
        """
        import json
        import re

        issues = {}
        logger = logging.getLogger("pipeline")

        # First, try to parse as JSON (from structured prompt response)
        try:
            # Find JSON in the content (may be wrapped in markdown code blocks)
            json_match = re.search(r'```json?\s*([\s\S]*?)\s*```', content)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON object
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = None

            if json_str:
                parsed = json.loads(json_str)
                # Extract candidate issues from structured response
                if "candidates" in parsed:
                    # Return the first candidate's issues (caller passes per-candidate)
                    for candidate_name, candidate_data in parsed["candidates"].items():
                        if isinstance(candidate_data, dict):
                            for issue_name, issue_data in candidate_data.items():
                                if isinstance(issue_data, dict):
                                    issues[issue_name.lower().replace(" ", "_").replace("/", "_")] = {
                                        "stance": issue_data.get("stance", ""),
                                        "summary": issue_data.get("evidence", ""),
                                        "confidence": issue_data.get("confidence", "medium"),
                                    }
                        break  # Only take first candidate

                    if issues:
                        logger.info(f"Parsed {len(issues)} issues from structured JSON response")
                        return issues
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Could not parse JSON from content: {e}")

        # Fall back to keyword-based extraction
        content_lower = content.lower()

        # Map canonical issue names to keywords for detection (expanded for all election types)
        issue_keywords = {
            "economy": ["economy", "economic", "jobs", "employment", "inflation", "wages", "trade", "business", "development"],
            "healthcare": ["healthcare", "health care", "medical", "insurance", "medicare", "medicaid", "hospital", "public health"],
            "immigration": ["immigration", "immigrant", "border", "asylum", "visa", "deportation", "sanctuary"],
            "climate_environment": ["climate", "environment", "energy", "renewable", "emissions", "green", "sustainability", "solar", "wind"],
            "education": ["education", "school", "student", "college", "university", "teacher", "curriculum", "funding"],
            "gun_policy": ["gun", "firearm", "second amendment", "2nd amendment", "weapon", "safety"],
            "abortion_reproductive_rights": ["abortion", "reproductive", "roe", "pro-choice", "pro-life", "women's health"],
            "foreign_policy": ["foreign policy", "international", "diplomacy", "military", "defense", "nato", "treaty"],
            "criminal_justice": ["criminal justice", "police", "prison", "crime", "law enforcement", "reform", "incarceration"],
            "voting_rights": ["voting", "election", "ballot", "voter", "democracy", "redistricting"],
            "taxation": ["tax", "taxes", "taxation", "irs", "revenue", "budget", "fiscal"],
            "local_issues": ["housing", "zoning", "transportation", "transit", "infrastructure", "roads", "water", "sewer", "parks", "development", "downtown", "neighborhood"],
        }

        for issue, keywords in issue_keywords.items():
            # Check if any keyword appears in content
            found_keywords = [kw for kw in keywords if kw in content_lower]

            if found_keywords:
                # Try to extract a relevant sentence containing the keyword
                stance_text = self._extract_stance_sentence(content, found_keywords[0])
                confidence = "medium" if len(found_keywords) > 1 else "low"

                issues[issue] = {
                    "stance": stance_text or f"Mentioned in analysis - see full summary",
                    "summary": "",
                    "confidence": confidence,
                }
            else:
                # Issue not mentioned - include with low confidence placeholder
                issues[issue] = {
                    "stance": "No specific position found in analyzed sources",
                    "summary": "",
                    "confidence": "low",
                }

        return issues

    def _extract_stance_sentence(self, content: str, keyword: str) -> str:
        """Extract a sentence containing the keyword as the stance."""
        # Split into sentences
        sentences = content.replace('\n', ' ').split('.')

        for sentence in sentences:
            if keyword.lower() in sentence.lower():
                cleaned = sentence.strip()
                if len(cleaned) > 20 and len(cleaned) < 500:  # Reasonable sentence length
                    return cleaned + "."

        return ""

    def _extract_summary_text(self, summary_result: Dict[str, Any], summary_type: str) -> str:
        """Extract the final summary text from the result."""
        # Check triangulation first (consensus result)
        triangulation = summary_result.get("triangulation", {})
        if summary_type in triangulation:
            tri_data = triangulation[summary_type]
            if hasattr(tri_data, "final_content"):
                return tri_data.final_content
            elif isinstance(tri_data, dict):
                return tri_data.get("final_content", "")

        # Fall back to raw summaries
        raw_summaries = summary_result.get("summaries", {}).get(summary_type, [])
        if raw_summaries:
            first_summary = raw_summaries[0]
            if hasattr(first_summary, "content"):
                return first_summary.content
            elif isinstance(first_summary, dict):
                return first_summary.get("content", str(first_summary))
            else:
                return str(first_summary)

        return ""

    def _extract_confidence(self, summary_result: Dict[str, Any]) -> str:
        """Extract overall confidence level from result."""
        # Check triangulation first
        triangulation = summary_result.get("triangulation", {})
        for key in ["candidates", "race", "issues"]:
            if key in triangulation:
                tri_data = triangulation[key]
                if hasattr(tri_data, "confidence"):
                    conf = tri_data.confidence
                    return conf.value if hasattr(conf, "value") else str(conf)
                elif isinstance(tri_data, dict):
                    return tri_data.get("confidence", "medium")

        # Fall back to raw summaries
        raw_summaries = summary_result.get("summaries", {})
        for key in ["candidates", "race"]:
            if key in raw_summaries and raw_summaries[key]:
                first_summary = raw_summaries[key][0]
                if hasattr(first_summary, "confidence"):
                    conf = first_summary.confidence
                    return conf.value if hasattr(conf, "value") else str(conf)

        return "medium"

    def _extract_sources(self, summary_result: Dict[str, Any]) -> List[str]:
        """Extract source references from result."""
        sources = []

        # Collect sources from all summaries
        raw_summaries = summary_result.get("summaries", {})
        for summary_list in raw_summaries.values():
            for summary in summary_list:
                if hasattr(summary, "source_ids"):
                    sources.extend(summary.source_ids)
                elif isinstance(summary, dict) and "source_ids" in summary:
                    sources.extend(summary["source_ids"])

        return list(set(sources))  # Deduplicate
