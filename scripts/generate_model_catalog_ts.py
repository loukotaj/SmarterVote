"""Generate the frontend's model catalog from ``shared/model_catalog.py``.

The admin UI needs the same facts the pipeline does — which models exist, what
they are called, which one each profile runs — and TypeScript cannot import
Python. Before this script, the frontend kept its own copies in
``web/src/lib/config/pipelineOptions.ts`` and ``web/src/lib/utils/format.ts``.
They drifted, badly and silently: the model picker was still offering
``openai/gpt-5.4``, ``google/gemini-3.1-pro-preview`` and ``x-ai/grok-4.20``
long after every one of them left the pipeline, so an admin could dispatch a run
against a model the backend no longer had a price for.

``web/src/lib/config/modelCatalog.ts`` is now generated from the Python catalog
and committed. CI runs ``--check`` to prove it is current, the same way the
tracked-artifact gate works.

    python scripts/generate_model_catalog_ts.py           # write the file
    python scripts/generate_model_catalog_ts.py --check   # exit 1 if stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.model_catalog import (  # noqa: E402
    DEFAULT_CHAMBER_FORECAST_MODEL,
    LEGACY_MODEL_ALIASES,
    MODEL_CATALOG,
    MODEL_PROFILES,
    PROFILE_DEFAULTS,
    RETIRED_MODEL_LABELS,
)

TARGET = REPO_ROOT / "web" / "src" / "lib" / "config" / "modelCatalog.ts"

HEADER = """// GENERATED FILE -- DO NOT EDIT.
// Source: shared/model_catalog.py
// Regenerate: python scripts/generate_model_catalog_ts.py
//
// The frontend used to keep its own hand-written copy of these facts, which
// drifted onto models the pipeline had already retired. Change the Python
// catalog and re-run the generator instead.
"""


def _ts(value: Any, indent: int = 0) -> str:
    """Render a Python value as TypeScript source (JSON is a close-enough subset)."""
    return json.dumps(value, indent=2, sort_keys=False).replace("\n", "\n" + " " * indent)


def render() -> str:
    catalog: Dict[str, Dict[str, Any]] = {
        model_id: {
            "id": spec.id,
            "label": spec.label,
            "inputPerM": spec.input_per_m,
            "outputPerM": spec.output_per_m,
            "cachedInputPerM": spec.cached_input_per_m,
            "contextWindowTokens": spec.context_window_tokens,
            "intelligence": spec.intelligence,
            "maxCompletionTokens": spec.max_completion_tokens,
        }
        for model_id, spec in MODEL_CATALOG.items()
    }
    labels: Dict[str, str] = {model_id: spec.label for model_id, spec in MODEL_CATALOG.items()}
    labels.update(RETIRED_MODEL_LABELS)

    # Each review seat offers exactly what the two profiles would pick for it.
    # Deriving the picker from the profiles is what keeps a retired model from
    # lingering in a dropdown.
    reviewer_defs: List[Dict[str, Any]] = []
    for key, role, name in (
        ("claude", "review_claude", "Claude"),
        ("gemini", "review_gemini", "Gemini"),
        ("grok", "review_grok", "Grok"),
    ):
        seen: List[str] = []
        for profile in ("default", "premium"):
            model_id = PROFILE_DEFAULTS[profile][role]
            if model_id not in seen:
                seen.append(model_id)
        reviewer_defs.append(
            {
                "key": key,
                "name": name,
                "options": [{"value": model_id, "label": labels[model_id]} for model_id in seen],
            }
        )

    research_models = [{"value": "", "label": "Auto (profile selects)"}]
    for profile in ("default", "premium"):
        model_id = PROFILE_DEFAULTS[profile]["primary"]
        if all(option["value"] != model_id for option in research_models):
            research_models.append({"value": model_id, "label": f"{labels[model_id]} ({profile})"})

    default_reviewer_models = {
        key: PROFILE_DEFAULTS["default"][role]
        for key, role in (("claude", "review_claude"), ("gemini", "review_gemini"), ("grok", "review_grok"))
    }

    return f"""{HEADER}
export interface ModelSpec {{
  id: string;
  label: string;
  inputPerM: number;
  outputPerM: number;
  cachedInputPerM: number | null;
  contextWindowTokens: number;
  intelligence: number;
  maxCompletionTokens: number | null;
}}

export const MODEL_CATALOG: Record<string, ModelSpec> = {_ts(catalog)};

/** Display names, including models we have retired but still have runs for. */
export const MODEL_LABELS: Record<string, string> = {_ts(labels)};

/** Old model IDs mapped onto their current equivalent. */
export const LEGACY_MODEL_ALIASES: Record<string, string> = {_ts(LEGACY_MODEL_ALIASES)};

export const MODEL_PROFILES: string[] = {_ts(sorted(MODEL_PROFILES))};

export const PROFILE_DEFAULTS: Record<string, Record<string, string>> = {_ts(PROFILE_DEFAULTS)};

export const DEFAULT_CHAMBER_FORECAST_MODEL = {json.dumps(DEFAULT_CHAMBER_FORECAST_MODEL)};

export type ReviewerKey = "claude" | "gemini" | "grok";

export const REVIEWER_DEFS: {{
  key: ReviewerKey;
  name: string;
  options: {{ value: string; label: string }}[];
}}[] = {_ts(reviewer_defs)};

export const RESEARCH_MODELS: {{ value: string; label: string }}[] = {_ts(research_models)};

export const DEFAULT_REVIEWER_MODELS: Record<ReviewerKey, string> = {_ts(default_reviewer_models)};
"""


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed file is stale")
    args = parser.parse_args(argv[1:])

    generated = render()
    current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else None

    if args.check:
        if current == generated:
            print(f"ok    {TARGET.relative_to(REPO_ROOT).as_posix()} is current")
            return 0
        print(
            f"FAIL  {TARGET.relative_to(REPO_ROOT).as_posix()} is stale.\n"
            f"      Run: python scripts/generate_model_catalog_ts.py"
        )
        return 1

    if current == generated:
        print(f"unchanged  {TARGET.relative_to(REPO_ROOT).as_posix()}")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(generated, encoding="utf-8")
    print(f"wrote      {TARGET.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
