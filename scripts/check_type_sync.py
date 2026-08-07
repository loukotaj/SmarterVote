"""Checks that web/src/lib/types.ts mirrors the Pydantic models in shared/models.py
and shared/pipeline_options.py.

Why a comparison checker instead of generate-and-diff
------------------------------------------------------
This repo's TypeScript types intentionally do not map 1:1 onto the Pydantic
annotations: `HttpUrl`/`datetime` collapse to `string`, `Dict[CanonicalIssue,
IssueStance]` is rendered as `Partial<Record<IssueKey, IssueStance>>` (a
superset key type, for legacy-issue-name tolerance), `model_overrides` is a
hand-shaped object instead of a generic `Record<string, string>`, and so on.
Reproducing the project's actual TS style well enough to auto-generate a
byte-for-byte-diffable file would require essentially the same per-field
override table this checker already needs -- so a generator buys little
extra robustness while adding a second artifact (the generated file) that
itself needs to be kept in sync with hand-written formatting conventions.
A direct comparison against the *committed* types.ts, backed by an explicit,
commented allowlist for legitimate divergence, is more transparent and cheaper
to maintain here.

What is (and is not) checked
-----------------------------
- Every enum in ENUM_TO_TS_NAME: exact member-value set match (this is how the
  12 frozen `CanonicalIssue` members, and the legacy issue name migration
  table, are enforced).
- Every model in CHECKED_MODELS: field presence (both directions, modulo
  ALLOWED_EXTRA_TS_FIELDS), optionality (`field?: T` iff the Python type is
  `Optional[T]`), and a best-effort structural type match (scalars, enums,
  nested checked models, List/Dict, and Literal value sets), with a small
  FIELD_TYPE_OVERRIDES table for fields where the intended TS type is not a
  generic rendering of the Python annotation.
- TS-only interfaces (RaceRecord, RaceSummary, RunInfo, analytics types, ...)
  are declared in FRONTEND_ONLY_OR_OTHER_BACKEND_TYPES with a one-line reason
  each and are deliberately NOT structurally checked here -- most of them
  mirror a *different* backend model (services/races-api/schemas.py,
  pipeline_client/backend/models.py, pipeline_client/backend/race_manager.py)
  or are pure frontend view types, not shared/models.py.
"""

from __future__ import annotations

import re
import sys
import typing
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Type, Union, get_args, get_origin

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import BaseModel, HttpUrl  # noqa: E402

from shared import models as shared_models  # noqa: E402
from shared import pipeline_config  # noqa: E402
from shared import pipeline_options as shared_pipeline_options  # noqa: E402
from shared import run_health as shared_run_health  # noqa: E402

DEFAULT_TYPES_TS_PATH = REPO_ROOT / "web" / "src" / "lib" / "types.ts"

# ---------------------------------------------------------------------------
# The 12 frozen canonical issues (CLAUDE.md rule #2 / frontend-types
# instructions). Kept here as an explicit, independent source of truth so a
# simultaneous, matching edit on both sides still gets caught.
# ---------------------------------------------------------------------------
FROZEN_CANONICAL_ISSUES: tuple[str, ...] = (
    "Healthcare",
    "Economy",
    "Climate/Energy",
    "Abortion & Reproductive Health",
    "Immigration",
    "Firearms & Second Amendment",
    "Foreign Policy",
    "Civil Rights & Equality",
    "Education",
    "Tech & AI",
    "Election Policy",
    "Local Issues",
)

# ---------------------------------------------------------------------------
# Enums checked for exact member-value parity with their TS union type.
# ---------------------------------------------------------------------------
ENUM_TO_TS_NAME: Dict[Type[Enum], str] = {
    shared_models.SourceType: "SourceType",
    shared_models.ConfidenceLevel: "ConfidenceLevel",
    shared_models.ContestStage: "ContestStage",
    shared_models.RosterSourceType: "RosterSourceType",
    shared_models.CanonicalIssue: "CanonicalIssue",
    shared_models.ForecastRating: "ForecastRating",
    shared_run_health.RunFailureReason: "RunFailureReason",
    shared_run_health.RunHealthStatus: "RunHealthStatus",
}

# ---------------------------------------------------------------------------
# Pydantic models checked field-by-field against a TS interface.
# Key = TS interface name, value = Pydantic model class.
# ---------------------------------------------------------------------------
CHECKED_MODELS: Dict[str, Type[BaseModel]] = {
    "Source": shared_models.Source,
    "IssueStance": shared_models.IssueStance,
    "CandidateLink": shared_models.CandidateLink,
    "CandidateRosterSource": shared_models.CandidateRosterSource,
    "CareerEntry": shared_models.CareerEntry,
    "EducationEntry": shared_models.EducationEntry,
    "ReviewFlag": shared_models.ReviewFlag,
    "AgentReview": shared_models.AgentReview,
    "ValidationGrade": shared_models.ValidationGrade,
    "ForecastMarketSignal": shared_models.ForecastMarketSignal,
    "ForecastEvidence": shared_models.ForecastEvidence,
    "RaceForecast": shared_models.RaceForecast,
    "Candidate": shared_models.Candidate,
    "PollMatchup": shared_models.PollMatchup,
    "PollEntry": shared_models.PollEntry,
    "RaceIdentityBrief": shared_models.RaceIdentityBrief,
    "RunAudit": shared_models.RunAudit,
    "PipelineState": shared_models.PipelineState,
    "IssueResearchAudit": shared_models.IssueResearchAudit,
    "RosterResearchAudit": shared_models.RosterResearchAudit,
    "MetadataResearchAudit": shared_models.MetadataResearchAudit,
    "Race": shared_models.RaceJSON,  # renamed on the TS side
    # PipelineRunOptions is the wire-level ("caller may omit anything")
    # schema shared by the races-api and worker request models; RunOptions is
    # its TS mirror. ResolvedPipelineRunOptions (execution defaults) is
    # backend-only and intentionally not mirrored.
    "RunOptions": shared_pipeline_options.PipelineRunOptions,
    # Run-health verdict surface: persisted on run records and returned by the
    # races-api /runs endpoints, so the TS mirror is load-bearing for the admin
    # UI rather than incidental.
    "StepFailure": shared_run_health.StepFailure,
    "RunHealthVerdict": shared_run_health.RunHealthVerdict,
}
MODEL_TO_TS_NAME: Dict[Type[BaseModel], str] = {cls: name for name, cls in CHECKED_MODELS.items()}
MODEL_TO_TS_NAME_BY_NAME: Dict[str, str] = {cls.__name__: name for name, cls in CHECKED_MODELS.items()}

# ---------------------------------------------------------------------------
# Every other `export interface` / `export type` in types.ts must be listed
# here with a reason, or check_all_types_classified() below fails. This is
# what makes the allowlist load-bearing rather than decorative: a new type
# added to types.ts that nobody classifies (as mirroring shared/models.py,
# mirroring some *other* backend model, or being frontend-only) trips the
# gate until a human makes an explicit call on it.
# ---------------------------------------------------------------------------
FRONTEND_ONLY_OR_OTHER_BACKEND_TYPES: Dict[str, str] = {
    "IssueKey": "Superset of CanonicalIssue plus legacy issue-name strings; covered by FIELD_TYPE_OVERRIDES + check_legacy_issue_names(), not an independent enum.",
    "CANONICAL_ISSUES": "Derived const array mirroring the CanonicalIssue enum values; covered transitively by check_frozen_canonical_issues().",
    "RENAMED_ISSUE_NOTES": "Frontend-only user-facing copy (tooltip text) for renamed issues; has no backend equivalent.",
    "CandidateSummary": "Mirrors services/races-api/schemas.py:CandidateSummary (search/listing projection), not shared/models.py:Candidate.",
    "RaceSummary": "Mirrors services/races-api/schemas.py:RaceSummary, not shared/models.py:RaceJSON.",
    "RunStatus": "Mirrors pipeline_client/backend/models.py:RunStatus, not shared/models.py; checked separately by check_run_status().",
    "PipelineStepId": "Mirrors shared/pipeline_config.py:PIPELINE_STEP_IDS; checked separately by check_pipeline_step_ids().",
    "PIPELINE_STEPS": "Derived const array; checked separately by check_pipeline_step_ids().",
    "DEFAULT_UPDATE_PIPELINE_STEP_IDS": "Derived const array mirroring shared/pipeline_config.py:DEFAULT_UPDATE_PIPELINE_STEPS; checked separately by check_pipeline_step_ids().",
    "RunStep": "Mirrors pipeline_client/backend/models.py:RunStep (pipeline run progress), not shared/models.py.",
    "RunInfo": "Mirrors pipeline_client/backend/models.py:RunInfo (pipeline run progress), not shared/models.py.",
    "Artifact": "Mirrors pipeline_client/backend/models.py artifact listing shape; not part of shared/models.py.",
    "LogEntry": "Mirrors pipeline_client/backend/logging_manager.py:LogEntry / backend/models.py:LogEntry, not shared/models.py.",
    "RunHistoryItem": "Frontend view type extending RunInfo with display-only fields (display_id, updated_at, last_step); no single backend equivalent.",
    "TimeseriesBucket": "Frontend-only analytics chart shape; no backend Pydantic model.",
    "AnalyticsOverview": "Admin analytics dashboard response shape (races-api traffic/analytics routes); not part of the RaceJSON schema.",
    "TrafficDimension": "Frontend-only analytics chart shape; no backend Pydantic model.",
    "TrafficTimeseriesBucket": "Frontend-only analytics chart shape; no backend Pydantic model.",
    "TrafficAnalytics": "Cloudflare traffic-analytics API response shape; not part of the RaceJSON schema.",
    "RaceAnalytics": "Per-race traffic analytics response shape; not part of the RaceJSON schema.",
    "AgentMetrics": "Pipeline-run cost/token metrics shape (Firestore-backed); merged into Race responses (see ALLOWED_EXTRA_TS_FIELDS['Race']) but not itself a shared/models.py model.",
    "PipelineRunRecord": "Mirrors Firestore pipeline_runs cost-metrics records surfaced by races-api; not part of shared/models.py.",
    "PipelineMetricsSummary": "Aggregate cost-metrics summary computed by races-api; not part of shared/models.py.",
    "GcpCostServiceLine": "GCP billing export line-item shape (admin cost dashboard); no backend Pydantic model.",
    "GcpCostSummary": "GCP billing export summary shape (admin cost dashboard); no backend Pydantic model.",
    "RaceRecord": "Mirrors pipeline_client/backend/race_manager.py:RaceRecord (unified admin race-catalog record), not shared/models.py:RaceJSON.",
    "RaceStatusType": "Mirrors the RaceStatus string values used by RaceRecord (pipeline_client/backend/race_manager.py); RaceStatus is a plain str class, not a Python Enum.",
    "ChamberForecastDetails": "Chamber-forecast (House/Senate/Governors) response shape produced by a separate forecast pipeline; not part of shared/models.py.",
    "ChamberForecasts": "Chamber-forecast top-level response shape; not part of shared/models.py.",
}


def check_all_types_classified(ts_source: str) -> List[str]:
    declared = set(re.findall(r"export interface (\w+)", ts_source))
    declared |= set(re.findall(r"export type (\w+)", ts_source))
    declared |= set(re.findall(r"export const (\w+)\s*:", ts_source))
    # Top-level `export const` values checked by their own bespoke function
    # rather than via CHECKED_MODELS/ENUM_TO_TS_NAME.
    bespoke_top_level_checks = {"LEGACY_ISSUE_NAMES"}
    classified = (
        set(CHECKED_MODELS)
        | set(ENUM_TO_TS_NAME.values())
        | set(FRONTEND_ONLY_OR_OTHER_BACKEND_TYPES)
        | bespoke_top_level_checks
    )
    unclassified = declared - classified
    if unclassified:
        return [
            f"[allowlist] TS type(s) declared in types.ts but not classified as checked or "
            f"intentionally-divergent: {sorted(unclassified)}. Add each to CHECKED_MODELS (if it "
            f"should mirror a shared/models.py or shared/pipeline_options.py model) or to "
            f"FRONTEND_ONLY_OR_OTHER_BACKEND_TYPES with a reason (if it's frontend-only or mirrors "
            f"a different backend model)."
        ]
    stale = set(FRONTEND_ONLY_OR_OTHER_BACKEND_TYPES) - declared
    if stale:
        return [
            f"[allowlist] FRONTEND_ONLY_OR_OTHER_BACKEND_TYPES entry no longer found in types.ts (rename or remove it): {sorted(stale)}"
        ]
    return []


# ---------------------------------------------------------------------------
# Fields present on the TS interface but not the Pydantic model -- e.g.
# server-composed fields merged into API responses. Documented, not ignored.
# ---------------------------------------------------------------------------
ALLOWED_EXTRA_TS_FIELDS: Dict[str, set] = {
    "Race": {
        # Merged into race responses from Firestore pipeline-run cost data by
        # services/races-api (gcs_helpers.py / routers/races_admin.py); not
        # part of the RaceJSON schema persisted to GCS.
        "agent_metrics",
    },
}

# ---------------------------------------------------------------------------
# Fields whose expected TS type is not a generic rendering of the Python
# annotation. Each entry documents *why*.
# ---------------------------------------------------------------------------
FIELD_TYPE_OVERRIDES: Dict[tuple, str] = {
    # `issue` also accepts legacy (pre-rename) issue-name strings so old
    # published JSON can be displayed before it's migrated; see
    # LEGACY_ISSUE_NAMES in shared/models.py.
    ("IssueStance", "issue"): "IssueKey",
    # Dict keyed by CanonicalIssue, but IssueKey (a superset including legacy
    # names) + Partial is the deliberately more tolerant TS rendering.
    ("Candidate", "issues"): "Partial<Record<IssueKey, IssueStance>>",
}

# Fields checked by a bespoke function below instead of the generic matcher
# (their TS shape is a fixed object literal, not a generic Record/union).
BESPOKE_FIELD_CHECKS: set = {
    ("RunOptions", "model_overrides"),
}

# Fields where the Pydantic annotation is deliberately generic (`str` /
# `List[str]`) because validation happens in a `@field_validator` rather than
# via a `Literal` type, but the TS side narrows to the canonical value set
# for editor autocomplete. Compared as a value set (order-independent)
# against the same shared/pipeline_config.py constants the validators use.
FIELD_LITERAL_SET_OVERRIDES: Dict[tuple, set] = {
    ("RunOptions", "model_profile"): set(pipeline_config.MODEL_PROFILES),  # see normalize_model_profile()
    ("RunOptions", "review_providers"): set(pipeline_config.REVIEW_PROVIDER_IDS),  # see normalize_review_providers()
}

SCALAR_TS_MAP = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
}


# ---------------------------------------------------------------------------
# TypeScript source parsing
# ---------------------------------------------------------------------------


def _strip_comments(ts_source: str) -> str:
    # Safe for this file: no type literal here contains "//" inside quotes.
    no_line_comments = re.sub(r"//[^\n]*", "", ts_source)
    no_block_comments = re.sub(r"/\*.*?\*/", "", no_line_comments, flags=re.DOTALL)
    return no_block_comments


def _find_matching_brace(text: str, open_index: int) -> int:
    """Given the index of an opening '{', return the index of its match."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("Unbalanced braces in TS source")


def _split_top_level(body: str, sep: str) -> List[str]:
    """Split `body` on `sep` only where bracket/paren/angle-bracket depth is 0."""
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in body:
        if ch in "{<([":
            depth += 1
        elif ch in "}>)]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


@dataclass
class TsField:
    name: str
    optional: bool
    type_text: str  # whitespace-normalized


@dataclass
class TsInterface:
    name: str
    fields: Dict[str, TsField] = field(default_factory=dict)


def parse_ts_interfaces(ts_source: str) -> Dict[str, TsInterface]:
    """Extract every `export interface Name { ... }` block."""
    interfaces: Dict[str, TsInterface] = {}
    for m in re.finditer(r"export interface (\w+)[^{]*\{", ts_source):
        name = m.group(1)
        open_idx = m.end() - 1
        close_idx = _find_matching_brace(ts_source, open_idx)
        body = ts_source[open_idx + 1 : close_idx]
        iface = TsInterface(name=name)
        for field_text in _split_top_level(body, ";"):
            field_match = re.match(r"^\s*\[?(\w+)\]?(\?)?\s*:\s*(.*)$", field_text, re.DOTALL)
            if not field_match:
                continue
            fname, optional_marker, type_text = field_match.groups()
            normalized = re.sub(r"\s+", " ", type_text).strip()
            iface.fields[fname] = TsField(name=fname, optional=bool(optional_marker), type_text=normalized)
        interfaces[name] = iface
    return interfaces


def _union_tokens(text: str) -> List[str]:
    """Split a `"a" | "b" | "c"`-style TS union (optionally with a stray
    leading `|` from a multi-line union, and stripped of whitespace) into
    its member tokens, dropping empties."""
    tokens = [t.strip().lstrip("|").strip() for t in _split_top_level(text, "|")]
    return [t for t in tokens if t]


def parse_ts_type_unions(ts_source: str) -> Dict[str, List[str]]:
    """Extract every `export type Name = ...;` union's raw member tokens.

    Returns the top-level pipe-separated tokens verbatim (quotes included for
    string literals) so callers can decide how to interpret them.
    """
    unions: Dict[str, List[str]] = {}
    for m in re.finditer(r"export type (\w+)\s*=\s*(.*?);", ts_source, re.DOTALL):
        name, rhs = m.group(1), m.group(2)
        rhs = re.sub(r"\s+", " ", rhs).strip()
        unions[name] = _union_tokens(rhs)
    return unions


def _quoted_string_literals(tokens: List[str]) -> set:
    literals = set()
    for t in tokens:
        lm = re.match(r'^"((?:[^"\\]|\\.)*)"$', t)
        if lm:
            literals.add(lm.group(1))
    return literals


# ---------------------------------------------------------------------------
# Python (Pydantic) introspection
# ---------------------------------------------------------------------------


def _unwrap_optional(annotation: Any) -> tuple:
    """Return (inner_type, is_optional) for an annotation, unwrapping Optional[X]."""
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]  # noqa: E721
        is_optional = type(None) in args
        if len(non_none) == 1:
            return non_none[0], is_optional
        return Union[tuple(non_none)], is_optional
    return annotation, False


def _literal_token_set(annotation: Any) -> set:
    tokens = set()
    for v in get_args(annotation):
        tokens.add(f'"{v}"' if isinstance(v, str) else str(v))
    return tokens


def expected_ts_type(annotation: Any) -> Optional[str]:
    """Best-effort generic derivation of the expected TS type text for a
    (already Optional-unwrapped) Python annotation. Returns None if this
    annotation shape isn't generically derivable (caller should consult
    FIELD_TYPE_OVERRIDES / BESPOKE_FIELD_CHECKS instead)."""
    if annotation in SCALAR_TS_MAP:
        return SCALAR_TS_MAP[annotation]
    if annotation is HttpUrl:
        return "string"
    import datetime as _dt

    if annotation is _dt.datetime:
        return "string"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return ENUM_TO_TS_NAME.get(annotation)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return MODEL_TO_TS_NAME.get(annotation) or MODEL_TO_TS_NAME_BY_NAME.get(annotation.__name__)

    origin = get_origin(annotation)
    if origin is Literal:
        # Rendered generically as a "|"-joined union; callers compare token
        # sets rather than this string directly, but return something for
        # completeness.
        return " | ".join(sorted(_literal_token_set(annotation)))
    if origin in (list, List):
        (inner,) = get_args(annotation)
        inner_ts = expected_ts_type(inner)
        return f"{inner_ts}[]" if inner_ts else None
    if origin in (dict, Dict):
        key_t, val_t = get_args(annotation)
        key_ts = expected_ts_type(key_t)
        val_ts = expected_ts_type(val_t)
        if key_ts and val_ts:
            return f"Record<{key_ts}, {val_ts}>"
        return None
    return None


def types_match(annotation: Any, ts_type_text: str) -> bool:
    origin = get_origin(annotation)
    if origin is Literal:
        return _literal_token_set(annotation) == set(_union_tokens(ts_type_text))
    expected = expected_ts_type(annotation)
    if expected is None:
        return False
    return expected == ts_type_text


def _literal_set_matches(expected_values: set, ts_type_text: str) -> bool:
    """Compare an expected set of plain string values against a TS type text
    that may be a bare union (`"a" | "b"`) or an array of one (`("a" | "b")[]`)."""
    text = ts_type_text.strip()
    if text.endswith("[]"):
        text = text[: -len("[]")].strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    ts_values = set(_quoted_string_literals(_union_tokens(text)))
    return ts_values == expected_values


# ---------------------------------------------------------------------------
# Comparators
# ---------------------------------------------------------------------------


def check_enums(ts_unions: Dict[str, List[str]]) -> List[str]:
    violations = []
    for py_enum, ts_name in ENUM_TO_TS_NAME.items():
        py_values = {member.value for member in py_enum}
        if ts_name not in ts_unions:
            violations.append(f"[{ts_name}] TS union type not found in types.ts (expected for Python enum {py_enum.__name__})")
            continue
        ts_values = _quoted_string_literals(ts_unions[ts_name])
        missing_in_ts = py_values - ts_values
        extra_in_ts = ts_values - py_values
        if missing_in_ts:
            violations.append(
                f"[{ts_name}] missing member(s) present in Python enum {py_enum.__name__}: {sorted(missing_in_ts)}"
            )
        if extra_in_ts:
            violations.append(
                f"[{ts_name}] extra member(s) not present in Python enum {py_enum.__name__}: {sorted(extra_in_ts)}"
            )
    return violations


def check_frozen_canonical_issues(ts_unions: Dict[str, List[str]]) -> List[str]:
    """Independent guard for CLAUDE.md rule #2: the 12 canonical issues are frozen."""
    violations = []
    py_values = tuple(m.value for m in shared_models.CanonicalIssue)
    if set(py_values) != set(FROZEN_CANONICAL_ISSUES):
        violations.append(
            "[CanonicalIssue] shared/models.py CanonicalIssue no longer matches the frozen 12-issue "
            f"list recorded in scripts/check_type_sync.py and .github/instructions/frontend-types.instructions.md: "
            f"python={sorted(py_values)} frozen={sorted(FROZEN_CANONICAL_ISSUES)}"
        )
    ts_values = _quoted_string_literals(ts_unions.get("CanonicalIssue", []))
    if ts_values != set(FROZEN_CANONICAL_ISSUES):
        violations.append(
            "[CanonicalIssue] types.ts CanonicalIssue no longer matches the frozen 12-issue list: "
            f"ts={sorted(ts_values)} frozen={sorted(FROZEN_CANONICAL_ISSUES)}"
        )
    return violations


def check_legacy_issue_names(ts_source: str) -> List[str]:
    violations = []
    py_legacy = shared_models.LEGACY_ISSUE_NAMES
    m = re.search(r"export const LEGACY_ISSUE_NAMES[^=]*=\s*\{(.*?)\};", ts_source, re.DOTALL)
    if not m:
        violations.append("[LEGACY_ISSUE_NAMES] could not find `export const LEGACY_ISSUE_NAMES` in types.ts")
        return violations
    body = m.group(1)
    pairs = re.findall(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', body)
    ts_legacy = dict(pairs)
    if ts_legacy != py_legacy:
        violations.append(f"[LEGACY_ISSUE_NAMES] TS/Python mismatch: python={py_legacy} ts={ts_legacy}")
    return violations


def check_model_overrides_shape(ts_interfaces: Dict[str, TsInterface]) -> List[str]:
    """Bespoke check: RunOptions.model_overrides is a fixed object literal of
    optional string values, one per shared.pipeline_config.MODEL_ROLES entry."""
    violations = []
    iface = ts_interfaces.get("RunOptions")
    if iface is None or "model_overrides" not in iface.fields:
        violations.append("[RunOptions] missing field 'model_overrides'")
        return violations
    type_text = iface.fields["model_overrides"].type_text
    obj_match = re.match(r"^\{(.*)\}$", type_text.strip())
    if not obj_match:
        violations.append(f"[RunOptions.model_overrides] expected an object literal type, got: {type_text!r}")
        return violations
    keys = set()
    for entry in _split_top_level(obj_match.group(1), ";"):
        km = re.match(r"^\s*(\w+)\??\s*:\s*string\s*$", entry)
        if not km:
            violations.append(f"[RunOptions.model_overrides] could not parse member: {entry!r}")
            continue
        keys.add(km.group(1))
    expected = set(pipeline_config.MODEL_ROLES)
    if keys != expected:
        violations.append(
            "[RunOptions.model_overrides] keys don't match shared.pipeline_config.MODEL_ROLES: "
            f"ts={sorted(keys)} expected={sorted(expected)}"
        )
    return violations


def check_model(ts_name: str, model_cls: Type[BaseModel], ts_interfaces: Dict[str, TsInterface]) -> List[str]:
    violations = []
    iface = ts_interfaces.get(ts_name)
    if iface is None:
        violations.append(f"[{ts_name}] no `export interface {ts_name}` found in types.ts")
        return violations

    py_fields = model_cls.model_fields
    allowed_extra = ALLOWED_EXTRA_TS_FIELDS.get(ts_name, set())

    missing_in_ts = set(py_fields) - set(iface.fields)
    if missing_in_ts:
        violations.append(
            f"[{ts_name}] field(s) present in Python model but missing from TS interface: {sorted(missing_in_ts)}"
        )

    extra_in_ts = set(iface.fields) - set(py_fields) - allowed_extra
    if extra_in_ts:
        violations.append(
            f"[{ts_name}] field(s) present in TS interface but not in Python model (and not in "
            f"ALLOWED_EXTRA_TS_FIELDS): {sorted(extra_in_ts)}"
        )

    for fname, py_field in py_fields.items():
        if fname not in iface.fields:
            continue  # already reported above
        ts_field = iface.fields[fname]
        inner_annotation, is_optional = _unwrap_optional(py_field.annotation)

        if ts_field.optional != is_optional:
            violations.append(
                f"[{ts_name}.{fname}] optionality mismatch: TS field is "
                f"{'optional' if ts_field.optional else 'required'} but Python type is "
                f"{'Optional' if is_optional else 'non-Optional (has a default but must always be present)'}"
            )

        key = (ts_name, fname)
        if key in BESPOKE_FIELD_CHECKS:
            continue
        if key in FIELD_TYPE_OVERRIDES:
            expected = FIELD_TYPE_OVERRIDES[key]
            if ts_field.type_text != expected:
                violations.append(
                    f"[{ts_name}.{fname}] type mismatch: ts={ts_field.type_text!r} expected(override)={expected!r}"
                )
            continue
        if key in FIELD_LITERAL_SET_OVERRIDES:
            expected_values = FIELD_LITERAL_SET_OVERRIDES[key]
            if not _literal_set_matches(expected_values, ts_field.type_text):
                violations.append(
                    f"[{ts_name}.{fname}] value-set mismatch: ts={ts_field.type_text!r} expected values={sorted(expected_values)}"
                )
            continue

        if not types_match(inner_annotation, ts_field.type_text):
            derived = expected_ts_type(inner_annotation)
            violations.append(
                f"[{ts_name}.{fname}] type mismatch: ts={ts_field.type_text!r} "
                f"python_annotation={inner_annotation!r} expected_ts~={derived!r}"
            )

    return violations


def check_run_status(ts_source: str) -> List[str]:
    """Bonus check: RunStatus in types.ts vs pipeline_client's RunStatus enum.

    RunStatus is excluded from `check_enums` because it lives in
    pipeline_client/backend/models.py rather than shared/models.py, and that
    exclusion left it with no check at all — unlike PipelineStepId, which is
    excluded for the same reason and then checked here. Both sides serialize
    the same run documents, so a value added on one side and not the other
    gives the admin UI a status it will not render.
    """
    from pipeline_client.backend.models import RunStatus

    violations = []
    unions = parse_ts_type_unions(ts_source)
    if "RunStatus" not in unions:
        return ["[RunStatus] TS union type not found in types.ts"]
    ts_values = _quoted_string_literals(unions["RunStatus"])
    py_values = {status.value for status in RunStatus}
    if ts_values != py_values:
        violations.append(
            f"[RunStatus] mismatch vs pipeline_client.backend.models.RunStatus: "
            f"ts={sorted(ts_values)} python={sorted(py_values)}"
        )
    return violations


def check_pipeline_step_ids(ts_source: str) -> List[str]:
    """Bonus check: PipelineStepId / PIPELINE_STEPS in types.ts vs the
    canonical step order + weights in shared/pipeline_config.py."""
    violations = []
    unions = parse_ts_type_unions(ts_source)
    ts_steps = _quoted_string_literals(unions.get("PipelineStepId", []))
    py_steps = set(pipeline_config.PIPELINE_STEP_IDS)
    if ts_steps != py_steps:
        violations.append(
            f"[PipelineStepId] mismatch vs shared.pipeline_config.PIPELINE_STEP_IDS: ts={sorted(ts_steps)} python={sorted(py_steps)}"
        )

    m = re.search(r"export const PIPELINE_STEPS[^=]*=\s*\[(.*?)\];", ts_source, re.DOTALL)
    if not m:
        violations.append("[PIPELINE_STEPS] could not find `export const PIPELINE_STEPS` in types.ts")
        return violations
    entries = re.findall(r'\{\s*id:\s*"([^"]+)"\s*,\s*label:\s*"([^"]*)"\s*,\s*weight:\s*(\d+)\s*\}', m.group(1))
    ts_weights = {step_id: int(weight) for step_id, _label, weight in entries}
    ts_labels = {step_id: label for step_id, label, _weight in entries}
    if ts_weights != pipeline_config.PIPELINE_STEP_WEIGHTS:
        violations.append(
            f"[PIPELINE_STEPS] weights mismatch vs shared.pipeline_config.PIPELINE_STEP_WEIGHTS: ts={ts_weights} python={pipeline_config.PIPELINE_STEP_WEIGHTS}"
        )
    if ts_labels != pipeline_config.PIPELINE_STEP_LABELS:
        violations.append(
            f"[PIPELINE_STEPS] labels mismatch vs shared.pipeline_config.PIPELINE_STEP_LABELS: ts={ts_labels} python={pipeline_config.PIPELINE_STEP_LABELS}"
        )

    update_opt_in_match = re.search(
        r"const UPDATE_OPT_IN_STEPS[^=]*=\s*new Set<PipelineStepId>\(\s*\[(.*?)\]\s*\)",
        ts_source,
        re.DOTALL,
    )
    if not update_opt_in_match:
        violations.append("[DEFAULT_UPDATE_PIPELINE_STEP_IDS] could not find UPDATE_OPT_IN_STEPS in types.ts")
    else:
        ts_opt_in = set(re.findall(r'"([^"]+)"', update_opt_in_match.group(1)))
        expected_opt_in = set(pipeline_config.PIPELINE_STEP_IDS) - set(pipeline_config.DEFAULT_UPDATE_PIPELINE_STEPS)
        if ts_opt_in != expected_opt_in:
            violations.append(
                "[DEFAULT_UPDATE_PIPELINE_STEP_IDS] opt-in steps mismatch vs "
                f"shared.pipeline_config.DEFAULT_UPDATE_PIPELINE_STEPS: ts={sorted(ts_opt_in)} "
                f"expected={sorted(expected_opt_in)}"
            )
    return violations


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_checks(types_ts_path: Path = DEFAULT_TYPES_TS_PATH) -> List[str]:
    ts_source_raw = Path(types_ts_path).read_text(encoding="utf-8")
    ts_source = _strip_comments(ts_source_raw)

    ts_interfaces = parse_ts_interfaces(ts_source)
    ts_unions = parse_ts_type_unions(ts_source)

    violations: List[str] = []
    violations += check_all_types_classified(ts_source)
    violations += check_enums(ts_unions)
    violations += check_frozen_canonical_issues(ts_unions)
    violations += check_legacy_issue_names(ts_source)
    violations += check_model_overrides_shape(ts_interfaces)
    violations += check_pipeline_step_ids(ts_source)
    violations += check_run_status(ts_source)

    for ts_name, model_cls in CHECKED_MODELS.items():
        violations += check_model(ts_name, model_cls, ts_interfaces)

    return violations


def main() -> int:
    violations = run_checks(DEFAULT_TYPES_TS_PATH)
    if violations:
        print(
            f"FAILED: web/src/lib/types.ts is out of sync with shared/models.py / shared/pipeline_options.py ({len(violations)} issue(s)):\n"
        )
        for v in violations:
            print(f"  - {v}")
        print(
            "\nSee .github/instructions/frontend-types.instructions.md. If this is a legitimate, "
            "intentional divergence, add it to ALLOWED_EXTRA_TS_FIELDS / FIELD_TYPE_OVERRIDES in "
            "scripts/check_type_sync.py with a comment explaining why -- do not silently ignore it."
        )
        return 1
    print("OK: web/src/lib/types.ts matches shared/models.py and shared/pipeline_options.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
