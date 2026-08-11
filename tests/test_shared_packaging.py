"""Guards for the installable shared schema distribution."""

from pathlib import Path

import shared

try:
    import tomllib
except ImportError:  # pragma: no cover - project runtime is Python 3.11+
    import tomli as tomllib


def test_shared_package_metadata_matches_runtime_version():
    pyproject = tomllib.loads((Path(__file__).parents[1] / "shared" / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == shared.__version__
    assert pyproject["tool"]["setuptools"]["packages"] == ["shared", "shared.data"]
