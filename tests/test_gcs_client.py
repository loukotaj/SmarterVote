"""One GCS client factory, and production code must not reach it through the debug app.

race_manager imported _get_gcs_client from backend/main.py — the local debug
FastAPI app that CLAUDE.md marks "not production". The import was lazy, so it
would not have failed at startup; it would have failed the first time a run
needed GCS, part-way through, in a deployment that never meant to import a web
framework at all.
"""

from __future__ import annotations

import pathlib

import pytest

from pipeline_client.backend import gcs_client

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset():
    gcs_client.reset_gcs_client()
    yield
    gcs_client.reset_gcs_client()


def test_missing_library_returns_none_rather_than_raising(monkeypatch):
    """Local mode runs without GCS; every call site branches on a falsy client."""
    import builtins

    real_import = builtins.__import__

    def _no_storage(name, *args, **kwargs):
        if name == "google.cloud":
            raise ImportError("no google-cloud-storage")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_storage)
    assert gcs_client.get_gcs_client() is None


def test_credential_failure_returns_none_rather_than_raising(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _bad_creds(name, *args, **kwargs):
        if name == "google.cloud":
            raise RuntimeError("could not determine credentials")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _bad_creds)
    assert gcs_client.get_gcs_client() is None


def test_client_is_built_once(monkeypatch):
    """Six modules used to build their own; the point of the factory is one."""
    built = {"n": 0}

    class _FakeClient:
        def __init__(self):
            built["n"] += 1

    class _FakeStorage:
        Client = _FakeClient

    monkeypatch.setattr(gcs_client, "_client", None)
    import sys
    import types

    fake = types.ModuleType("google.cloud")
    fake.storage = _FakeStorage  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.cloud", fake)

    first = gcs_client.get_gcs_client()
    second = gcs_client.get_gcs_client()
    assert first is second
    assert built["n"] == 1


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Module names this file actually imports, at any nesting depth.

    Parsed rather than grepped: the docstrings here name backend.main and
    FastAPI to explain the layering rule, and a text search would flag the
    explanation as the violation.
    """
    import ast

    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_factory_module_pulls_in_no_web_framework():
    """Importing the factory must stay free of FastAPI, or the layering fix is undone."""
    imported = _imported_modules(REPO_ROOT / "pipeline_client" / "backend" / "gcs_client.py")
    for module in imported:
        assert not module.startswith(("fastapi", "starlette")), f"factory imports a web framework: {module}"
        assert "backend.main" not in module, f"factory imports the debug app: {module}"


def test_no_production_module_imports_the_debug_app():
    """backend/main.py is local-debug only; run.py is the one legitimate consumer."""
    offenders = []
    for path in REPO_ROOT.joinpath("pipeline_client").rglob("*.py"):
        if path.name == "run.py" or (path.name == "main.py" and path.parent.name == "backend"):
            continue
        for module in _imported_modules(path):
            if module.endswith("backend.main"):
                offenders.append(f"{path.relative_to(REPO_ROOT)} -> {module}")
    assert not offenders, f"production modules importing the debug app: {offenders}"
