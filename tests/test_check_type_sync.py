"""Tests for scripts/check_type_sync.py -- the CI gate that enforces
web/src/lib/types.ts mirrors shared/models.py and shared/pipeline_options.py.

Includes a deliberately-drifted fixture (test_injected_field_rename_is_detected
and friends) that mutates a temporary copy of the real, committed types.ts to
prove the checker actually fails on real drift, not just on contrived toy
inputs.
"""

import sys
from pathlib import Path
from typing import List, Optional, Union, get_args

import pytest
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_type_sync as cts  # noqa: E402

REAL_TYPES_TS = REPO_ROOT / "web" / "src" / "lib" / "types.ts"


# ---------------------------------------------------------------------------
# The check must pass against the current committed state (requirement #7).
# ---------------------------------------------------------------------------


def test_real_repo_files_are_in_sync():
    violations = cts.run_checks(REAL_TYPES_TS)
    assert (
        violations == []
    ), "web/src/lib/types.ts has drifted from shared/models.py / shared/pipeline_options.py:\n" + "\n".join(violations)


def test_frozen_canonical_issue_list_has_12_members_and_matches_python():
    assert len(cts.FROZEN_CANONICAL_ISSUES) == 12
    python_values = {m.value for m in cts.shared_models.CanonicalIssue}
    assert python_values == set(cts.FROZEN_CANONICAL_ISSUES)


# ---------------------------------------------------------------------------
# Deliberately-drifted fixtures against the REAL committed types.ts, mutated
# in a temp copy. This is the proof the checker actually catches real drift.
# ---------------------------------------------------------------------------


@pytest.fixture
def real_ts_source() -> str:
    return REAL_TYPES_TS.read_text(encoding="utf-8")


def _write_temp_ts(tmp_path: Path, source: str) -> Path:
    p = tmp_path / "types.ts"
    p.write_text(source, encoding="utf-8")
    return p


def test_injected_field_rename_is_detected(tmp_path, real_ts_source):
    """Renaming a real, required field (Candidate.name) must be caught as
    both a missing-field and an extra-field violation."""
    mutated = real_ts_source.replace(
        "export interface Candidate {\n  name: string;", "export interface Candidate {\n  full_name: string;"
    )
    assert mutated != real_ts_source, "fixture setup did not actually change anything"

    violations = cts.run_checks(_write_temp_ts(tmp_path, mutated))

    assert any("Candidate" in v and "name" in v and "missing" in v.lower() for v in violations)
    assert any("Candidate" in v and "full_name" in v for v in violations)


def test_injected_optionality_drift_is_detected(tmp_path, real_ts_source):
    """Marking a required (non-Optional) Python field as `?` in TS must be caught."""
    mutated = real_ts_source.replace(
        "  incumbent: boolean;\n  roster_sources: CandidateRosterSource[];",
        "  incumbent?: boolean;\n  roster_sources: CandidateRosterSource[];",
    )
    assert mutated != real_ts_source

    violations = cts.run_checks(_write_temp_ts(tmp_path, mutated))

    assert any("Candidate.incumbent" in v and "optionality mismatch" in v for v in violations)


def test_injected_canonical_issue_removal_is_detected(tmp_path, real_ts_source):
    """Removing one of the 12 frozen canonical issues must be caught, both by
    the generic enum-parity check and the independent frozen-list guard."""
    mutated = real_ts_source.replace(
        'export type CanonicalIssue =\n  | "Healthcare"\n', 'export type CanonicalIssue =\n  | "Healthcare Reform"\n'
    )
    assert mutated != real_ts_source

    violations = cts.run_checks(_write_temp_ts(tmp_path, mutated))

    assert any("CanonicalIssue" in v and "Healthcare" in v for v in violations)
    assert any("frozen" in v.lower() for v in violations)


def test_injected_unclassified_type_is_detected(tmp_path, real_ts_source):
    """A brand-new `export interface` that nobody has classified as checked
    or intentionally-divergent must trip the allowlist-freshness guard."""
    mutated = real_ts_source + "\n\nexport interface TotallyNewThing {\n  foo: string;\n}\n"

    violations = cts.run_checks(_write_temp_ts(tmp_path, mutated))

    assert any("TotallyNewThing" in v for v in violations)


# ---------------------------------------------------------------------------
# Unit tests for the TS parsing primitives, using small synthetic snippets so
# failures point precisely at the parser rather than at unrelated repo drift.
# ---------------------------------------------------------------------------


def test_parse_ts_interfaces_handles_nested_multiline_field_types():
    snippet = """
    export interface AgentMetrics {
      model: string;
      model_breakdown: Record<
        string,
        { prompt_tokens: number; completion_tokens: number }
      >;
      duration_s: number;
    }
    """
    interfaces = cts.parse_ts_interfaces(cts._strip_comments(snippet))
    assert "AgentMetrics" in interfaces
    fields = interfaces["AgentMetrics"].fields
    assert set(fields) == {"model", "model_breakdown", "duration_s"}
    assert fields["model_breakdown"].type_text.startswith("Record<")
    assert not fields["model_breakdown"].optional
    assert not fields["duration_s"].optional


def test_parse_ts_interfaces_strips_trailing_line_comments():
    snippet = """
    export interface Foo {
      jurisdiction?: string; // Full geographic scope (e.g. "X's 1st District")
      state?: string; // trailing comment
    }
    """
    interfaces = cts.parse_ts_interfaces(cts._strip_comments(snippet))
    fields = interfaces["Foo"].fields
    assert fields["jurisdiction"].type_text == "string"
    assert fields["state"].type_text == "string"


def test_parse_ts_type_unions_handles_multiline_leading_pipe():
    snippet = """
    export type ContestStage =
      | "pre_primary"
      | "post_primary_general"
      | "unknown";
    """
    unions = cts.parse_ts_type_unions(snippet)
    assert unions["ContestStage"] == ['"pre_primary"', '"post_primary_general"', '"unknown"']


# ---------------------------------------------------------------------------
# Unit tests for the model-comparison logic, using small synthetic Pydantic
# models rather than the real (large) shared/models.py classes.
# ---------------------------------------------------------------------------


class _Widget(BaseModel):
    name: str
    count: int = 0
    label: Optional[str] = None


def test_check_model_detects_missing_field():
    ts_source = cts._strip_comments("export interface Widget {\n  name: string;\n  label?: string;\n}\n")
    interfaces = cts.parse_ts_interfaces(ts_source)
    violations = cts.check_model("Widget", _Widget, interfaces)
    assert any("count" in v and "missing" in v.lower() for v in violations)


def test_check_model_detects_extra_field():
    ts_source = cts._strip_comments(
        "export interface Widget {\n  name: string;\n  count: number;\n  label?: string;\n  bogus: string;\n}\n"
    )
    interfaces = cts.parse_ts_interfaces(ts_source)
    violations = cts.check_model("Widget", _Widget, interfaces)
    assert any("bogus" in v for v in violations)


def test_check_model_detects_optionality_mismatch_both_directions():
    ts_source = cts._strip_comments(
        "export interface Widget {\n"
        "  name: string;\n"
        "  count?: number;\n"  # wrong: python `count` is non-Optional (has default 0)
        "  label: string;\n"  # wrong: python `label` is Optional
        "}\n"
    )
    interfaces = cts.parse_ts_interfaces(ts_source)
    violations = cts.check_model("Widget", _Widget, interfaces)
    assert any("count" in v and "optionality mismatch" in v for v in violations)
    assert any("label" in v and "optionality mismatch" in v for v in violations)


def test_check_model_passes_for_a_correct_mirror():
    ts_source = cts._strip_comments("export interface Widget {\n  name: string;\n  count: number;\n  label?: string;\n}\n")
    interfaces = cts.parse_ts_interfaces(ts_source)
    violations = cts.check_model("Widget", _Widget, interfaces)
    assert violations == []


def test_check_enums_detects_member_drift():
    ts_unions = {"SourceType": ['"website"', '"finance"']}  # missing several real members
    violations = cts.check_enums(ts_unions)
    assert any("SourceType" in v and "missing" in v.lower() for v in violations)


def test_main_exits_nonzero_on_drift(tmp_path, real_ts_source, capsys):
    mutated = real_ts_source.replace(
        "export interface Candidate {\n  name: string;", "export interface Candidate {\n  full_name: string;"
    )
    ts_path = _write_temp_ts(tmp_path, mutated)

    original_default = cts.DEFAULT_TYPES_TS_PATH
    cts.DEFAULT_TYPES_TS_PATH = ts_path
    try:
        exit_code = cts.main()
    finally:
        cts.DEFAULT_TYPES_TS_PATH = original_default

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAILED" in out


# ---------------------------------------------------------------------------
# Both spellings of an optional annotation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "annotation",
    [Optional[str], Union[str, None], str | None],
    ids=["Optional[str]", "Union[str, None]", "str | None"],
)
def test_unwrap_optional_handles_every_spelling_of_optional(annotation):
    """PEP 604's `str | None` carries types.UnionType as its origin, not
    typing.Union. Matching only the latter reported the field as required and,
    because the annotation was never unwrapped, raised a second false type
    mismatch on the same field. Every model checked today writes `Optional[X]`,
    so this cost nothing until someone modernised one."""
    inner, is_optional = cts._unwrap_optional(annotation)
    assert inner is str
    assert is_optional is True


def test_unwrap_optional_leaves_non_optional_annotations_alone():
    assert cts._unwrap_optional(str) == (str, False)
    assert cts._unwrap_optional(List[str]) == (List[str], False)


@pytest.mark.parametrize(
    "annotation",
    [Union[int, str, None], int | str | None],
    ids=["Union[int, str, None]", "int | str | None"],
)
def test_unwrap_optional_keeps_a_multi_member_union_intact(annotation):
    inner, is_optional = cts._unwrap_optional(annotation)
    assert is_optional is True
    assert set(get_args(inner)) == {int, str}
