"""Format staged files, stage the fixes, then run commit-blocking checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTO_FIX_HOOKS = ("isort", "black", "trailing-whitespace", "end-of-file-fixer")


def git_paths(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args, "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def run(command: list[str], *, check: bool = True) -> int:
    return subprocess.run(command, cwd=ROOT, check=check).returncode


def main() -> int:
    staged = git_paths("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if not staged:
        return 0

    unstaged = set(git_paths("diff", "--name-only"))
    overlapping = sorted(set(staged) & unstaged)
    if overlapping:
        print("Cannot auto-fix files that also have unstaged edits:", file=sys.stderr)
        for path in overlapping:
            print(f"  {path}", file=sys.stderr)
        print("Stage or stash those edits, then retry the commit.", file=sys.stderr)
        return 1

    for hook in AUTO_FIX_HOOKS:
        subprocess.run(
            ["pre-commit", "run", hook, "--hook-stage", "manual", "--files", *staged],
            cwd=ROOT,
            check=False,
        )

    run(["git", "add", "--", *staged])

    # A second pass distinguishes expected formatter edits from actual failures.
    for hook in AUTO_FIX_HOOKS:
        if run(
            ["pre-commit", "run", hook, "--hook-stage", "manual", "--files", *staged],
            check=False,
        ):
            return 1

    return run(
        ["pre-commit", "run", "--hook-stage", "pre-commit", "--files", *staged],
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
