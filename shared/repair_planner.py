"""Deterministic race repair planning and conservative cost ceilings."""

from __future__ import annotations

from typing import Any, Dict, List

from shared.models import CanonicalIssue
from shared.pipeline_config import PIPELINE_STEP_ORDER, PipelineRuntimeConfig
from shared.race_catalog import _coerce_datetime, _is_missing_image, _issue_verdict, build_catalog_health, compute_freshness

_FIXED_STEP_COST_USD = {
    "discovery": 0.10,
    "polling": 0.08,
    "forecast": 0.07,
    "voter_resources": 0.03,
    "review": 0.18,
    "iteration": 0.25,
}
_PER_CANDIDATE_COST_USD = {
    "images": 0.04,
    "finance": 0.08,
    "refinement": 0.06,
}
_PER_ISSUE_COST_USD = 0.05
_CANONICAL_ISSUES = {issue.value for issue in CanonicalIssue}


def _ordered_steps(steps: set[str]) -> List[str]:
    return [step for step in PIPELINE_STEP_ORDER if step in steps]


def _sources_are_stale(sources: List[Any]) -> bool:
    dates = [
        date
        for date in (
            _coerce_datetime(source.get("last_accessed") or source.get("published_at"))
            for source in sources
            if isinstance(source, dict)
        )
        if date is not None
    ]
    return bool(dates) and compute_freshness(max(dates)) in {"stale", "old"}


def _estimate_group(
    steps: set[str],
    *,
    candidate_count: int = 0,
    missing_issue_count: int = 0,
    phase_breakdown: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ordered = _ordered_steps(steps)
    static_cost = sum(_FIXED_STEP_COST_USD.get(step, 0.0) for step in ordered)
    static_cost += sum(_PER_CANDIDATE_COST_USD.get(step, 0.0) * candidate_count for step in ordered)
    if "issues" in steps:
        static_cost += _PER_ISSUE_COST_USD * missing_issue_count
    calibrated_cost = 0.0
    calibration_samples = 0
    for step in ordered:
        phase = (phase_breakdown or {}).get(step)
        if not isinstance(phase, dict):
            continue
        observed = float(phase.get("provider_cost_usd") or 0) + int(phase.get("search_calls") or 0) * 0.001
        if observed > 0:
            calibrated_cost += observed * 1.25
            calibration_samples += 1
    search_demand = (
        (12 if "discovery" in steps else 0)
        + (4 * candidate_count if "images" in steps else 0)
        + (10 * missing_issue_count if "issues" in steps else 0)
        + (10 * candidate_count if "finance" in steps else 0)
        + (6 * candidate_count if "refinement" in steps else 0)
        + (12 if "polling" in steps else 0)
        + (8 if "forecast" in steps else 0)
    )
    ceiling = PipelineRuntimeConfig.from_env().max_search_calls
    return {
        "enabled_steps": ordered,
        "estimated_max_cost_usd": round(max(static_cost, calibrated_cost, 0.01 if ordered else 0.0), 2),
        "estimated_max_search_calls": min(search_demand, ceiling),
        "estimated_search_demand": search_demand,
        "estimate_kind": "observed_plus_25pct_or_static_ceiling" if calibration_samples else "static_ceiling",
        "calibration_samples": calibration_samples,
    }


def build_repair_plan(race_id: str, race_data: Dict[str, Any], *, freshness: str | None = None) -> Dict[str, Any]:
    """Return a bounded, non-mutating repair proposal for one RaceJSON document."""
    health = build_catalog_health(race_data)
    candidates = [candidate for candidate in race_data.get("candidates", []) if isinstance(candidate, dict)]
    steps: set[str] = set()
    reasons: List[str] = []
    target_names: List[str] = []
    candidate_groups: List[Dict[str, Any]] = []
    race_steps: set[str] = set()
    race_reasons: List[str] = []

    if health["candidate_count"] == 0:
        race_steps.add("discovery")
        reasons.append("Roster is empty.")
        race_reasons.append("Roster is empty.")
    elif health["roster_verified_candidates"] < health["candidate_count"]:
        race_steps.add("discovery")
        reasons.append("One or more candidates lack roster evidence.")
        race_reasons.append("One or more candidates lack roster evidence.")

    for candidate in candidates:
        candidate_steps: set[str] = set()
        candidate_reasons: List[str] = []
        if _is_missing_image(candidate.get("image_url")):
            steps.add("images")
            candidate_steps.add("images")
            candidate_reasons.append("Candidate photo is missing.")
        issues = candidate.get("issues") if isinstance(candidate.get("issues"), dict) else {}
        terminal_issues = sum(
            _issue_verdict(issue)[0] for issue_name, issue in issues.items() if str(issue_name) in _CANONICAL_ISSUES
        )
        candidate_missing_issues = max(0, len(_CANONICAL_ISSUES) - terminal_issues)
        if candidate_missing_issues:
            steps.add("issues")
            candidate_steps.add("issues")
            candidate_reasons.append(f"{candidate_missing_issues} issue slot(s) lack a terminal verdict.")
        donor_sources = candidate.get("donor_sources")
        if not candidate.get("donor_summary") or not (
            candidate.get("donor_source_url") or (isinstance(donor_sources, list) and donor_sources)
        ):
            steps.add("finance")
            candidate_steps.add("finance")
            candidate_reasons.append("Finance summary or citation is incomplete.")
        if candidate.get("incumbent"):
            voting_sources = candidate.get("voting_sources")
            if not candidate.get("voting_summary") or not (
                candidate.get("voting_source_url") or (isinstance(voting_sources, list) and voting_sources)
            ):
                steps.add("finance")
                candidate_steps.add("finance")
                candidate_reasons.append("Incumbent voting summary or citation is incomplete.")
        unsourced = sum(
            int(_issue_verdict(issue)[1] and not _issue_verdict(issue)[2])
            for issue_name, issue in issues.items()
            if str(issue_name) in _CANONICAL_ISSUES
        )
        if unsourced:
            steps.add("refinement")
            candidate_steps.add("refinement")
            candidate_reasons.append(f"{unsourced} substantive stance(s) lack sources.")
        issue_sources = [
            source for issue in issues.values() if isinstance(issue, dict) for source in issue.get("sources") or []
        ]
        if _sources_are_stale(issue_sources):
            steps.add("refinement")
            candidate_steps.add("refinement")
            candidate_reasons.append("Issue evidence is stale.")
        finance_sources = [source for key in ("donor_sources", "voting_sources") for source in candidate.get(key) or []]
        if _sources_are_stale(finance_sources):
            steps.add("finance")
            candidate_steps.add("finance")
            candidate_reasons.append("Finance or voting evidence is stale.")
        candidate_name = str(candidate.get("name") or "").strip()
        if candidate_steps and candidate_name:
            target_names.append(candidate_name)
            estimate = _estimate_group(
                candidate_steps,
                candidate_count=1,
                missing_issue_count=candidate_missing_issues,
                phase_breakdown=(race_data.get("agent_metrics") or {}).get("phase_breakdown"),
            )
            candidate_groups.append(
                {
                    **estimate,
                    "candidate_names": [candidate_name],
                    "reasons": candidate_reasons,
                }
            )

    if health["missing_image_count"]:
        reasons.append(f"{health['missing_image_count']} candidate photo(s) are missing.")
    if health["missing_issue_count"]:
        reasons.append(f"{health['missing_issue_count']} issue slot(s) lack a terminal research verdict.")
    if health["finance_complete_candidates"] < health["candidate_count"]:
        reasons.append("Candidate finance summaries or citations are incomplete.")
    if health["voting_complete_incumbents"] < health["incumbent_count"]:
        reasons.append("An incumbent voting summary or citation is incomplete.")
    if health["substantive_issue_count"] > health["sourced_substantive_issue_count"]:
        reasons.append("One or more substantive issue stances lack sources.")
    if not health["forecast_present"] or not health["forecast_evidence_complete"]:
        steps.add("forecast")
        race_steps.add("forecast")
        reasons.append("The forecast is missing or lacks explicit source URLs.")
        race_reasons.append("The forecast is missing or lacks explicit source URLs.")

    freshness = str(freshness or "").lower()
    if freshness in {"stale", "old"}:
        steps.update({"polling", "forecast", "voter_resources"})
        race_steps.update({"polling", "forecast", "voter_resources"})
        reasons.append(f"Race data is {freshness}.")
        race_reasons.append(f"Race data is {freshness}.")
    stale_sections = set(health.get("stale_sections") or [])
    section_steps = {
        "roster": "discovery",
        "polling": "polling",
        "forecast": "forecast",
        "voter_resources": "voter_resources",
    }
    for section, step in section_steps.items():
        if section in stale_sections:
            steps.add(step)
            race_steps.add(step)
            reason = f"{section.replace('_', ' ').title()} evidence is stale."
            reasons.append(reason)
            race_reasons.append(reason)

    if health["research_tier"] in {"full_unreviewed", "graded_low"}:
        steps.add("review")
        race_steps.add("review")
        reasons.append("Research needs a current validation review.")
        race_reasons.append("Research needs a current validation review.")
    if health["research_tier"] == "graded_low":
        steps.add("iteration")
        race_steps.add("iteration")
        reasons.append("The previous validation grade did not pass.")
        race_reasons.append("The previous validation grade did not pass.")

    steps.update(race_steps)
    ordered_steps = _ordered_steps(steps)
    target_names = list(dict.fromkeys(target_names))
    repair_groups = candidate_groups
    if race_steps:
        repair_groups.insert(
            0,
            {
                **_estimate_group(
                    race_steps,
                    phase_breakdown=(race_data.get("agent_metrics") or {}).get("phase_breakdown"),
                ),
                "candidate_names": None,
                "reasons": race_reasons,
            },
        )
    estimated_cost = sum(float(group["estimated_max_cost_usd"]) for group in repair_groups)
    estimated_search_demand = sum(int(group["estimated_search_demand"]) for group in repair_groups)
    search_ceiling = PipelineRuntimeConfig.from_env().max_search_calls
    estimated_search_calls = sum(int(group["estimated_max_search_calls"]) for group in repair_groups)
    budget_warnings = []
    if estimated_search_demand > search_ceiling:
        budget_warnings.append(
            f"Estimated search demand ({estimated_search_demand}) exceeds the logical-run ceiling "
            f"({search_ceiling}); split the repair by candidate or step."
        )

    return {
        "race_id": race_id,
        "needs_repair": bool(ordered_steps),
        "research_tier": health["research_tier"],
        "health": health,
        "recommended_steps": ordered_steps,
        "candidate_names": target_names or None,
        "repair_groups": repair_groups,
        "queueable_repair_groups_only": True,
        "reasons": reasons,
        "estimated_max_cost_usd": round(max(estimated_cost, 0.01 if ordered_steps else 0.0), 2),
        "estimated_max_search_calls": estimated_search_calls,
        "estimated_search_demand": estimated_search_demand,
        "budget_warnings": budget_warnings,
        "estimate_kind": (
            "observed_plus_25pct_or_static_ceiling"
            if any(group["calibration_samples"] for group in repair_groups)
            else "static_ceiling"
        ),
    }


def summarize_repair_plans(plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "plans": plans,
        "race_count": len(plans),
        "repair_count": sum(bool(plan.get("needs_repair")) for plan in plans),
        "estimated_max_cost_usd": round(sum(float(plan.get("estimated_max_cost_usd") or 0) for plan in plans), 2),
        "estimated_max_search_calls": sum(int(plan.get("estimated_max_search_calls") or 0) for plan in plans),
    }
