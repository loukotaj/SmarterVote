"""Step 04: Publish Race Data to RaceJSON v0.2 Format

This handler takes the summarized data and publishes it as a standardized
RaceJSON file for consumption by the web frontend.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class Step04PublishHandler:
    """Handler for publishing race data as RaceJSON."""

    def __init__(self, storage_backend=None):
        self.storage_backend = storage_backend

    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """
        Publish race data as RaceJSON v0.2.

        Payload expected:
            - race_id: str
            - race_json: dict (original metadata)
            - summaries: dict (from step03)

        Returns:
            - published_path: str
            - race_json: dict (final output)
        """
        logger = logging.getLogger("pipeline")
        race_id = payload.get("race_id")
        race_json = payload.get("race_json", {})
        summaries = payload.get("summaries", {})

        if not race_id:
            raise ValueError("Step04PublishHandler: Missing 'race_id' in payload")

        logger.info(f"Step04 Publish: Publishing race {race_id}")

        t0 = time.perf_counter()

        # Build final RaceJSON v0.2
        final_race_json = self._build_race_json(race_id, race_json, summaries)

        # Validate the output
        validation_errors = self._validate_race_json(final_race_json)
        if validation_errors:
            logger.warning(f"RaceJSON validation warnings: {validation_errors}")

        # Publish to local filesystem
        published_path = await self._publish_local(race_id, final_race_json)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"Published {race_id} to {published_path} in {duration_ms}ms")

        return {
            "race_id": race_id,
            "published_path": str(published_path),
            "race_json": final_race_json,
            "validation_warnings": validation_errors,
            "duration_ms": duration_ms,
            "status": "published",
        }

    def _build_race_json(
        self, race_id: str, race_json: Dict[str, Any], summaries: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build the final RaceJSON v0.2 structure."""

        # Start with existing race_json as base
        final = {
            "id": race_id,
            "election_date": race_json.get("election_date", ""),
            "candidates": [],
            "updated_utc": datetime.utcnow().isoformat(),
            "generator": ["SmarterVote Pipeline v1.1"],
            "race_metadata": race_json.get("race_metadata", {}),
        }

        # Merge candidate data with summaries
        existing_candidates = race_json.get("candidates", [])
        for candidate in existing_candidates:
            name = candidate.get("name", "")
            candidate_summary = summaries.get(name, {})

            # Transform issues to frontend-expected format
            # Frontend expects: Record<CanonicalIssue, IssueStance>
            # where IssueStance = { stance: string, confidence: string, sources: Source[] }
            raw_issues = candidate_summary.get("issues", candidate.get("issues", {}))
            formatted_issues = self._format_issues_for_frontend(raw_issues)

            final["candidates"].append({
                "name": name,
                "party": candidate.get("party", ""),
                "incumbent": candidate.get("incumbent", False),
                "summary": candidate_summary.get("summary", candidate.get("summary", "")),
                "issues": formatted_issues,
                "top_donors": candidate.get("top_donors", []),
                "social_media": candidate.get("social_media", {}),
            })

        return final

    def _format_issues_for_frontend(self, issues: Dict[str, Any]) -> Dict[str, Any]:
        """Transform issue data to frontend-expected IssueStance format."""
        formatted = {}

        # Map internal issue names to canonical display names
        issue_name_map = {
            "economy": "Economy",
            "healthcare": "Healthcare",
            "immigration": "Immigration",
            "climate_environment": "Climate/Energy",
            "education": "Education",
            "gun_policy": "Guns & Safety",
            "abortion_reproductive_rights": "Reproductive Rights",
            "foreign_policy": "Foreign Policy",
            "criminal_justice": "Social Justice",
            "voting_rights": "Election Reform",
            "taxation": "Economy",
            "tech_ai": "Tech & AI",
            "local_issues": "Local Issues",
            # Additional mappings for variations
            "climate_energy": "Climate/Energy",
            "social_justice": "Social Justice",
            "guns_safety": "Guns & Safety",
            "election_reform": "Election Reform",
            "reproductive_rights": "Reproductive Rights",
        }

        for issue_key, issue_data in issues.items():
            # Map to canonical issue name
            canonical_name = issue_name_map.get(issue_key.lower(), issue_key)

            if isinstance(issue_data, dict):
                raw_sources = issue_data.get("sources", [])
                formatted[canonical_name] = {
                    "stance": issue_data.get("stance", issue_data.get("summary", "")),
                    "confidence": issue_data.get("confidence", "medium"),
                    "sources": self._format_sources(raw_sources),
                }
            elif isinstance(issue_data, str):
                formatted[canonical_name] = {
                    "stance": issue_data,
                    "confidence": "medium",
                    "sources": [],
                }

        return formatted

    def _format_sources(self, raw_sources: list) -> list:
        """Convert source data to frontend Source format."""
        formatted = []
        for source in raw_sources:
            if isinstance(source, str):
                # Source is just a URL string
                formatted.append({
                    "url": source,
                    "type": "website",
                    "title": None,
                    "last_accessed": datetime.utcnow().isoformat(),
                })
            elif isinstance(source, dict):
                # Source is already a dict
                formatted.append({
                    "url": source.get("url", ""),
                    "type": source.get("type", "website"),
                    "title": source.get("title"),
                    "last_accessed": source.get("last_accessed", datetime.utcnow().isoformat()),
                })
        return formatted

    def _validate_race_json(self, race_json: Dict[str, Any]) -> list:
        """Validate RaceJSON structure and return any warnings."""
        warnings = []

        if not race_json.get("id"):
            warnings.append("Missing race ID")

        if not race_json.get("candidates"):
            warnings.append("No candidates in race")

        for candidate in race_json.get("candidates", []):
            if not candidate.get("name"):
                warnings.append("Candidate missing name")
            if not candidate.get("summary"):
                warnings.append(f"Candidate {candidate.get('name', 'unknown')} missing summary")
            if not candidate.get("issues"):
                warnings.append(f"Candidate {candidate.get('name', 'unknown')} missing issues")

        return warnings

    async def _publish_local(self, race_id: str, race_json: Dict[str, Any]) -> Path:
        """Publish RaceJSON to local filesystem."""
        logger = logging.getLogger("pipeline")

        # Determine output directory
        published_dir = Path(__file__).resolve().parents[3] / "data" / "published"
        published_dir.mkdir(parents=True, exist_ok=True)

        output_path = published_dir / f"{race_id}.json"

        # Backup existing file if present
        if output_path.exists():
            backup_path = output_path.with_suffix(
                f".json.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            output_path.rename(backup_path)
            logger.info(f"Backed up existing file to {backup_path}")

        # Write new file
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(race_json, f, indent=2, default=str)

        return output_path
