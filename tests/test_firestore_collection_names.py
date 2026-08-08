"""Firestore collection names live in `shared/config.py` and nowhere else.

They used to be written inline at ~100 call sites across pipeline_client and
services/races-api while the constants naming them went unimported, so renaming
a collection meant finding every literal by hand and the constants read as a
single point of control they were not.

This fails on a bare `collection("...")` anywhere in the tree, which is what
keeps that from creeping back one call site at a time.
"""

from __future__ import annotations

import ast
import io
import pathlib

import pytest

from shared import config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SEARCH_ROOTS = ("pipeline_client", "services/races-api", "shared", "smartervote_mcp")


def _python_files():
    for root in SEARCH_ROOTS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            if "__pycache__" not in str(path):
                yield path


def _literal_collection_calls(path: pathlib.Path):
    """Every `.collection("literal")` call, found via the AST.

    Parsing rather than grepping so a mention inside a comment or docstring —
    including the one in shared/config.py explaining this rule — is not a hit.
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "collection":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                yield node.lineno, arg.value


def test_no_collection_name_is_written_inline():
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno} collection({name!r})"
        for path in _python_files()
        for lineno, name in _literal_collection_calls(path)
    ]
    assert not offenders, "import the name from shared.config instead:\n" + "\n".join(offenders)


def test_the_scan_reaches_the_code_it_claims_to_cover():
    """Guards the guard: a scan that silently found nothing would pass forever."""
    files = list(_python_files())
    assert len(files) > 100, f"only {len(files)} files scanned"
    assert any("queue_processor" in str(f) for f in files)
    assert any("races-api" in str(f) for f in files)


def test_the_scan_would_catch_an_inline_name(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text('db.collection("pipeline_queue").document("x")\n', encoding="utf-8")
    assert list(_literal_collection_calls(sample)) == [(1, "pipeline_queue")]


def test_the_scan_ignores_a_name_in_a_comment(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text('# db.collection("pipeline_queue") is what this replaces\nx = 1\n', encoding="utf-8")
    assert list(_literal_collection_calls(sample)) == []


@pytest.mark.parametrize(
    "constant, expected",
    [
        ("FIRESTORE_QUEUE_COLLECTION", "pipeline_queue"),
        ("FIRESTORE_RUNS_COLLECTION", "pipeline_runs"),
        ("FIRESTORE_RACES_COLLECTION", "races"),
        ("FIRESTORE_SEARCH_CACHE_COLLECTION", "search_cache"),
        ("FIRESTORE_PAGE_CACHE_COLLECTION", "page_cache"),
        ("FIRESTORE_METRICS_COLLECTION", "pipeline_metrics"),
        ("FIRESTORE_ANALYTICS_EVENTS_COLLECTION", "analytics_events"),
        ("FIRESTORE_RACE_RUNS_SUBCOLLECTION", "runs"),
        ("FIRESTORE_RUN_LOGS_SUBCOLLECTION", "logs"),
    ],
)
def test_constants_still_name_the_deployed_collections(constant, expected):
    """These are live Firestore collections; the value is the wire format, not a
    label. Changing one migrates data, so it should take a deliberate edit here."""
    assert getattr(config, constant) == expected


def test_the_race_runs_subcollection_is_not_the_top_level_runs_collection():
    """`runs` hangs off a race document; `pipeline_runs` is at the root. They are
    different collections and the shorter name invites confusing them."""
    assert config.FIRESTORE_RACE_RUNS_SUBCOLLECTION != config.FIRESTORE_RUNS_COLLECTION
