"""Review-flag filtering and formatting for pipeline iteration passes."""

from typing import Any, Dict, List


def format_review_flags(
    reviews: List[Dict[str, Any]],
    *,
    candidate_index: int | None = None,
    candidate_name: str | None = None,
    include_global: bool = True,
) -> str:
    lines: list[str] = []
    candidate_prefix = f"candidates[{candidate_index}]" if candidate_index is not None else None
    candidate_name_lower = candidate_name.casefold() if candidate_name else None

    def applies(flag: Dict[str, Any]) -> bool:
        if candidate_prefix is None and candidate_name_lower is None:
            return True
        field = str(flag.get("field") or "")
        if candidate_prefix and field.startswith(candidate_prefix):
            return True
        text = " ".join(str(flag.get(key) or "") for key in ("field", "concern", "suggestion")).casefold()
        if candidate_name_lower and candidate_name_lower in text:
            return True
        return include_global and not field.startswith("candidates[")

    for review in reviews:
        review_lines = [f"\n--- Review by {review.get('model', 'unknown')} (verdict: {review.get('verdict', 'unknown')}) ---"]
        if review.get("summary"):
            review_lines.append(f"Summary: {review['summary']}")
        for flag in review.get("flags", []):
            if isinstance(flag, dict) and not applies(flag):
                continue
            review_lines.append(
                f"  [{flag.get('severity', 'info').upper()}] {flag.get('field', '?')}: {flag.get('concern', '')}"
            )
            if flag.get("suggestion"):
                review_lines.append(f"    Suggestion: {flag['suggestion']}")
        if len(review_lines) > (2 if review.get("summary") else 1):
            lines.extend(review_lines)
    return "\n".join(lines) if lines else "  (no specific flags)"


def has_actionable_flags(
    reviews: List[Dict[str, Any]], min_severity: str = "warning", exclude_fields: set | None = None
) -> bool:
    severity_rank = {"info": 0, "warning": 1, "error": 2}
    threshold = severity_rank.get(min_severity, 1)
    excluded = exclude_fields or set()
    return any(
        severity_rank.get(flag.get("severity", "info"), 0) >= threshold and flag.get("field", "") not in excluded
        for review in reviews
        for flag in review.get("flags", [])
    )


def flagged_fields(reviews: List[Dict[str, Any]], min_severity: str = "warning") -> set:
    """Return the set of field paths carrying a flag at or above *min_severity*.

    Used to tell whether an iteration pass actually cleared what it was given.
    A flag the model cannot act on — because the tool schema gives it no way to
    express the fix, say — otherwise persists silently, costing the same grade
    penalty on every future run with nothing in the logs to explain why.
    """
    severity_rank = {"info": 0, "warning": 1, "error": 2}
    threshold = severity_rank.get(min_severity, 1)
    return {
        str(flag.get("field") or "").strip()
        for review in reviews
        for flag in review.get("flags") or []
        if isinstance(flag, dict)
        and severity_rank.get(flag.get("severity", "info"), 0) >= threshold
        and str(flag.get("field") or "").strip()
    }
