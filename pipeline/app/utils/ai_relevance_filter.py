import asyncio
import logging
import os
from typing import Any, Dict, List

try:
    from ..schema import ExtractedContent
except ImportError:
    from shared.models import ExtractedContent  # type: ignore

logger = logging.getLogger(__name__)


class AIRelevanceFilter:
    """Simple AI-based relevance filtering for extracted documents."""

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    async def assess(self, text: str) -> Dict[str, Any]:
        """Assess relevance of text using an AI model or keyword heuristic."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            score = 1.0 if any(k in text.lower() for k in ["election", "candidate", "policy"]) else 0.0
            reasons = ["keyword_match"] if score > 0 else ["no_keywords"]
            return {"is_relevant": score >= self.threshold, "score": score, "reasons": reasons}

        try:
            import openai

            openai.api_key = api_key
            resp = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Rate the relevance of the following text to election policies on a scale 0-1",
                    },
                    {"role": "user", "content": text[:4000]},
                ],
                max_tokens=5,
            )
            raw = resp.choices[0].message["content"].strip()
            score = float(raw)
            reasons: List[str] = ["model_assessment"]
        except Exception as e:  # noqa: BLE001
            logger.warning("AI relevance check failed: %s", e)
            score = 0.0
            reasons = ["model_error"]

        return {"is_relevant": score >= self.threshold, "score": score, "reasons": reasons}

    async def filter_content(self, docs: List[ExtractedContent]) -> List[ExtractedContent]:
        """Filter documents by relevance using assess()."""
        filtered: List[ExtractedContent] = []
        for doc in docs:
            assessment = await self.assess(doc.text)
            doc.metadata["relevance"] = assessment
            if assessment["is_relevant"]:
                filtered.append(doc)
        return filtered
