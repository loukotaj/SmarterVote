"""The phases package re-exports a monkeypatch seam; prove it still conducts.

Phase submodules reach a few helpers through a lazy ``from . import <name>``
*inside* the calling function rather than a top-level import. That indirection is
the only reason patching ``pipeline_client.agent.phases.<name>`` reaches every
submodule.

This is the failure worth guarding: if one of these bindings is dropped from
``__init__``, submodules fall back to their own import and the patch silently
stops taking effect. Nothing fails — the suite goes green while exercising the
real implementation, including real network calls. These tests assert the patch
is actually observed.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "pipeline_client" / "agent" / "phases"


def _lazily_imported_names() -> set[str]:
    """Names any phase submodule pulls from the package namespace at call time."""
    names: set[str] = set()
    for path in PHASES_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            # `from . import x, y` -> module is None at level 1
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
                names.update(alias.name for alias in node.names)
    return names


def test_every_lazily_imported_name_is_bound_in_the_package():
    """A submodule importing a name the package does not expose is an ImportError
    waiting for the first run that reaches that line."""
    from pipeline_client.agent import phases

    missing = sorted(name for name in _lazily_imported_names() if not hasattr(phases, name))
    assert not missing, f"phase submodules lazily import names the package does not bind: {missing}"


def test_the_seam_is_not_empty():
    """Guards against this file passing because the detector found nothing."""
    assert len(_lazily_imported_names()) >= 4


@pytest.mark.parametrize("name", sorted(_lazily_imported_names()))
def test_patching_the_package_reaches_submodules(monkeypatch, name):
    """Patch the package attribute; every submodule that uses it must see the patch."""
    from pipeline_client.agent import phases

    sentinel = object()
    monkeypatch.setattr(phases, name, sentinel, raising=True)

    # Re-run the same lazy import a submodule performs and confirm it resolves
    # to the patched object rather than the original.
    resolved = getattr(__import__("pipeline_client.agent.phases", fromlist=[name]), name)
    assert resolved is sentinel, f"patching phases.{name} did not take effect"


def test_declared_exports_all_resolve():
    """__all__ must not promise a name the module does not actually bind."""
    from pipeline_client.agent import phases

    missing = [name for name in phases.__all__ if not hasattr(phases, name)]
    assert not missing, f"__all__ lists unbound names: {missing}"


def test_package_does_not_re_export_dead_weight():
    """It carried 110 names, 100 referenced nowhere. Keep it to what is used."""
    from pipeline_client.agent import phases

    exported = {
        name for name in vars(phases) if not name.startswith("__") and not isinstance(vars(phases)[name], type(pathlib))
    }
    assert len(exported) <= 30, f"re-export surface is growing again: {len(exported)} names"
