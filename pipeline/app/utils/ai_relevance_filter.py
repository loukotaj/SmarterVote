import logging
from typing import Any, Dict, List

from ..providers import TaskType, registry

try:
    from ..schema import ExtractedContent
except ImportError:  # pragma: no cover - fallback for tests
    from shared.models import ExtractedContent  # type: ignore

logger = logging.getLogger(__name__)


class AIRelevanceFilter:
    """AI-based relevance filtering for extracted documents."""

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self.providers = registry

    async def assess(self, text: str, race_name: str, candidates: List[str]) -> Dict[str, Any]:
        """Assess relevance of text using the provider registry or a heuristic."""

        prompt = (
            "You are validating web content for a political research pipeline.\n"
            f"Election: {race_name}\n"
            f"Candidates: {', '.join(candidates) if candidates else 'unknown'}\n"
            "Content:\n"
            f"{text[:4000]}\n\n"
            "Determine if the content is relevant to this election. Reject messy or poorly formatted"
            " content. Respond in JSON with fields: relevant (boolean), score (0-1), reason (string)."
        )

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "relevance",
                "schema": {
                    "type": "object",
                    "properties": {
                        "relevant": {"type": "boolean"},
                        "score": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["relevant", "score"],
                },
            },
        }

        try:
            data = await self.providers.generate_json(
                TaskType.DISCOVER,
                prompt,
                max_tokens=200,
                response_format=response_format,
            )
            score = float(data.get("score", 0.0))
            is_rel = bool(data.get("relevant")) and score >= self.threshold
            reason = data.get("reason", "model_assessment")
            reasons = [reason] if reason else ["model_assessment"]
            return {"is_relevant": is_rel, "score": score, "reasons": reasons}
        except Exception as e:  # noqa: BLE001
            logger.warning("AI relevance check failed: %s", e)
            score = 1.0 if any(k in text.lower() for k in ["election", "candidate", "policy"]) else 0.0
            reasons = ["keyword_match"] if score > 0 else ["no_keywords"]
            return {"is_relevant": score >= self.threshold, "score": score, "reasons": reasons}

    async def filter_content(
        self, docs: List[ExtractedContent], race_name: str, candidates: List[str]
    ) -> List[ExtractedContent]:
        """Filter documents by relevance using assess()."""

        filtered: List[ExtractedContent] = []
        for doc in docs:
            assessment = await self.assess(doc.text, race_name, candidates)
            doc.metadata["relevance"] = assessment
            if assessment["is_relevant"]:
                filtered.append(doc)
        return filtered
