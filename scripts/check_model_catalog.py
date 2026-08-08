"""Check the hand-maintained model catalog and profiles against OpenRouter's live model list.

Why this exists
---------------
`pipeline_client/agent/model_registry.py` hardcodes prices, context windows and
per-role model choices. All of that is written down by hand and none of it is
verified by anything, so it drifts silently against a provider catalog that
changes weekly. Two separate classes of bug have already shipped from this:

- **Stale prices.** deepseek-v4-flash was recorded at $0.077/$0.154 long after it
  repriced to $0.14/$0.28, and two nemotron entries were similarly wrong. Cost
  estimates and every "cheapest capable model" judgment built on them were off.
- **Version strings read as integers.** Grok sorts by decimal, so 4.20
  (2026-03-31) is *older* than 4.3 (2026-04-30). Reading it the other way put the
  quality profile's reviewer on an older model than economy's, and made the
  escalation map fall back to something worse than what it escaped from.

Neither is catchable by the normal test suite, because `tests/conftest.py` mocks
all network access by design. So this is a script, run deliberately, not a test.

    python scripts/check_model_catalog.py           # report + exit 1 on drift
    python scripts/check_model_catalog.py --quiet   # errors only

What is checked (these fail)
----------------------------
1. Every catalog entry is still served by OpenRouter.
2. Catalog prices match live prices exactly.
3. Context windows match live, where OpenRouter reports one.
4. Every model named by a profile role or the escalation map exists in the catalog.
5. Every escalation edge moves *up* a capability tier, using output price as the
   proxy. A lateral or downward edge means a stalled model "escalates" into
   something no better, which is the failure mode that made the grok bug invisible.
6. For each role, the quality profile's model is not worse than economy's — never a
   lower output-price tier, and never older when both come from the same provider.
   This is the grok inversion stated directly, so it cannot come back by another
   route. Recency is only compared within a provider because dates do not rank
   across families: gpt-5.6-terra is older than deepseek-v4-flash and far stronger.
7. The two hardcoded chamber-forecast models agree with each other. They live
   outside the profile system (races-api router + MCP tool signature) and nothing
   sweeps them forward, so they can only be kept honest by comparison.

What is only advised (these never fail)
---------------------------------------
For every model in use, any strictly-better alternative from the same provider —
newer *and* no more expensive on output. "Better" is genuinely a judgment call
(a newer Flash is not automatically stronger than an older Pro), so this prints
and moves on rather than blocking.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline_client.agent.llm import CHEAP_TO_DEFAULT_MODEL_FALLBACK  # noqa: E402
from pipeline_client.agent.model_registry import MODEL_CATALOG, PROFILE_DEFAULTS  # noqa: E402
from shared.pipeline_config import MODEL_ROLES  # noqa: E402

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# The chamber-forecast model is the one choice outside PROFILE_DEFAULTS. It is
# written in two places that must agree; see the comments on both sides.
CHAMBER_FORECAST_SITES = (
    (Path("services/races-api/routers/races_admin/forecasts.py"), r'DEFAULT_CHAMBER_FORECAST_MODEL\s*=\s*"([^"]+)"'),
    (Path("smartervote_mcp/server.py"), r'model:\s*str\s*=\s*"(google/[^"]+)",\s*\n\) -> Dict\[str, Any\]:'),
)

# Tolerance for float comparison of per-million prices. OpenRouter reports
# per-token strings like "0.0000001"; scaling to per-million reintroduces binary
# float error well below a hundredth of a cent, which is not real drift.
PRICE_EPSILON = 1e-6


def _fetch_live_models() -> Dict[str, Dict[str, Any]]:
    """Return {model_id: openrouter_record}. The key is optional for this endpoint
    but sending it keeps us on the account's rate limit rather than a shared one."""
    headers = {}
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(OPENROUTER_MODELS_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"OpenRouter returned HTTP {exc.code}: {exc.read().decode()[:200]}")
    except Exception as exc:  # network down, DNS, timeout
        raise SystemExit(f"Could not reach OpenRouter ({type(exc).__name__}: {exc})")
    return {m["id"]: m for m in payload.get("data", [])}


def _per_million(record: Dict[str, Any], field: str) -> Optional[float]:
    raw = (record.get("pricing") or {}).get(field)
    if raw is None:
        return None
    try:
        return float(raw) * 1_000_000
    except (TypeError, ValueError):
        return None


def _released(record: Optional[Dict[str, Any]]) -> Optional[datetime.date]:
    if not record or not record.get("created"):
        return None
    # utcfromtimestamp() is deprecated from 3.12 and slated for removal; the
    # aware form yields the same calendar date.
    return datetime.datetime.fromtimestamp(record["created"], datetime.timezone.utc).date()


def _provider(model_id: str) -> str:
    return model_id.split("/", 1)[0]


def _read_literal(path: Path, pattern: str) -> Optional[str]:
    full = REPO_ROOT / path
    if not full.exists():
        return None
    match = re.search(pattern, full.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _check_catalog(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """Catalog entries must still exist and still cost what we say they cost."""
    errors: List[str] = []
    for model_id, spec in sorted(MODEL_CATALOG.items()):
        record = live.get(model_id)
        if record is None:
            errors.append(f"{model_id}: in MODEL_CATALOG but no longer served by OpenRouter")
            continue
        for field, recorded, label in (
            ("prompt", spec.input_per_m, "input"),
            ("completion", spec.output_per_m, "output"),
        ):
            actual = _per_million(record, field)
            if actual is None:
                continue
            if abs(actual - recorded) > PRICE_EPSILON:
                errors.append(f"{model_id}: {label} price is ${actual:g}/M live, catalog says ${recorded:g}/M")
        live_ctx = record.get("context_length")
        if live_ctx and spec.context_window_tokens and int(live_ctx) != int(spec.context_window_tokens):
            errors.append(f"{model_id}: context window is {live_ctx} live, catalog says {spec.context_window_tokens}")
    return errors


def _check_profiles(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """Every role must name a model we have a spec for and that is actually served."""
    errors: List[str] = []
    for profile, roles in sorted(PROFILE_DEFAULTS.items()):
        for role in MODEL_ROLES:
            model_id = roles.get(role)
            if model_id is None:
                errors.append(f"profile {profile!r}: no model for role {role!r}")
                continue
            if model_id not in MODEL_CATALOG:
                errors.append(f"profile {profile!r} role {role!r}: {model_id} is not in MODEL_CATALOG")
            if model_id not in live:
                errors.append(f"profile {profile!r} role {role!r}: {model_id} is not served by OpenRouter")
    return errors


def _check_escalation() -> List[str]:
    """An escalation must buy something. Output price stands in for capability:
    a fallback into an equal-or-cheaper tier is the bug, not the price."""
    errors: List[str] = []
    for source, target in CHEAP_TO_DEFAULT_MODEL_FALLBACK.items():
        for label, model_id in (("source", source), ("target", target)):
            if model_id not in MODEL_CATALOG:
                errors.append(f"escalation {source} -> {target}: {label} {model_id} is not in MODEL_CATALOG")
        if source in MODEL_CATALOG and target in MODEL_CATALOG:
            if MODEL_CATALOG[target].output_per_m <= MODEL_CATALOG[source].output_per_m:
                errors.append(
                    f"escalation {source} -> {target}: target is not a higher tier "
                    f"(${MODEL_CATALOG[target].output_per_m:g}/M out vs ${MODEL_CATALOG[source].output_per_m:g}/M) "
                    f"-- escalating here buys nothing"
                )
    return errors


def _check_quality_not_worse(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """Paying for `quality` must not hand you something worse than `economy` gives away.

    "Worse" is checked two ways, because neither signal is sufficient alone:

    - **Tier**, always. Output price is the proxy, so a quality role priced below
      the economy role for the same job is flagged regardless of vintage.
    - **Recency, within one provider only.** Release dates only compare when the
      models are from the same family; gpt-5.6-terra being older than
      deepseek-v4-flash says nothing about which is stronger. Restricting to a
      single provider is what makes this precise enough to act on — and it is
      exactly the shape of the grok bug, where 4.20 and 4.3 were the same price
      from the same provider and only the date revealed the inversion.
    """
    errors: List[str] = []
    economy, quality = PROFILE_DEFAULTS.get("economy", {}), PROFILE_DEFAULTS.get("quality", {})
    for role in MODEL_ROLES:
        cheap_id, good_id = economy.get(role), quality.get(role)
        if not cheap_id or not good_id or cheap_id == good_id:
            continue
        if cheap_id in MODEL_CATALOG and good_id in MODEL_CATALOG:
            cheap_out, good_out = MODEL_CATALOG[cheap_id].output_per_m, MODEL_CATALOG[good_id].output_per_m
            if good_out < cheap_out:
                errors.append(
                    f"role {role!r}: quality uses {good_id} (${good_out:g}/M out) which is a LOWER tier "
                    f"than economy's {cheap_id} (${cheap_out:g}/M out)"
                )
        if _provider(cheap_id) != _provider(good_id):
            continue
        cheap_date, good_date = _released(live.get(cheap_id)), _released(live.get(good_id))
        if cheap_date and good_date and good_date < cheap_date:
            errors.append(
                f"role {role!r}: quality uses {good_id} ({good_date}) which is OLDER than "
                f"economy's same-provider {cheap_id} ({cheap_date})"
            )
    return errors


def _check_chamber_forecast(live: Dict[str, Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    found: List[Tuple[Path, Optional[str]]] = [
        (path, _read_literal(path, pattern)) for path, pattern in CHAMBER_FORECAST_SITES
    ]
    missing = [str(path) for path, value in found if value is None]
    if missing:
        errors.append(f"chamber-forecast model literal not found in: {', '.join(missing)} (did the declaration move?)")
        return errors
    values = {value for _, value in found}
    if len(values) > 1:
        detail = ", ".join(f"{path}={value}" for path, value in found)
        errors.append(f"chamber-forecast model disagrees between call sites: {detail}")
    for _, value in found:
        if value and value not in live:
            errors.append(f"chamber-forecast model {value} is not served by OpenRouter")
    return errors


# Task-specialized builds are newer and cheaper than the general models we use
# without being substitutes for them: an image variant cannot review prose, and a
# coding build is not a general reasoner. Suggesting them is how an advisory
# section turns into noise that gets skimmed past, so they are excluded by name.
SPECIALIZED_MARKERS = ("-image", "image-", "codex", "-code", "-build", "content-safety", "multi-agent", "-chat")


def _is_specialized(model_id: str) -> bool:
    return any(marker in model_id for marker in SPECIALIZED_MARKERS)


def _advise_newer(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """Same provider, newer, and no more expensive on output. Advisory only —
    a newer Flash is not automatically stronger than an older Pro."""
    in_use: Dict[str, List[str]] = {}
    for profile, roles in PROFILE_DEFAULTS.items():
        for role, model_id in roles.items():
            in_use.setdefault(model_id, []).append(f"{profile}.{role}")

    notes: List[str] = []
    for model_id, users in sorted(in_use.items()):
        record = live.get(model_id)
        current_date = _released(record)
        if not record or not current_date:
            continue
        current_out = _per_million(record, "completion")
        if current_out is None:
            continue
        better = []
        for other_id, other in live.items():
            if other_id == model_id or _provider(other_id) != _provider(model_id):
                continue
            if other_id.endswith(":free") or other_id.startswith("~") or _is_specialized(other_id):
                continue
            other_date, other_out = _released(other), _per_million(other, "completion")
            if not other_date or other_out is None:
                continue
            if other_date > current_date and other_out <= current_out:
                better.append((other_date, other_id, other_out))
        for other_date, other_id, other_out in sorted(better, reverse=True)[:2]:
            notes.append(
                f"{model_id} ({current_date}, ${current_out:g}/M out) used by {', '.join(users)}"
                f"  ->  {other_id} ({other_date}, ${other_out:g}/M out) is newer and no dearer"
            )
    return notes


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quiet", action="store_true", help="suppress the advisory section")
    args = parser.parse_args(argv[1:])

    live = _fetch_live_models()
    print(f"OpenRouter is serving {len(live)} models; catalog has {len(MODEL_CATALOG)}\n")

    sections = (
        ("catalog accuracy", _check_catalog(live)),
        ("profile roles", _check_profiles(live)),
        ("escalation tiers", _check_escalation()),
        ("quality not worse than economy", _check_quality_not_worse(live)),
        ("chamber forecast", _check_chamber_forecast(live)),
    )

    total = 0
    for name, errors in sections:
        total += len(errors)
        if errors:
            print(f"FAIL  {name}")
            for err in errors:
                print(f"        {err}")
        else:
            print(f"ok    {name}")

    if not args.quiet:
        notes = _advise_newer(live)
        print("\nadvisory -- newer, no dearer, same provider (judgment call, not a failure):")
        if notes:
            for note in notes:
                print(f"        {note}")
        else:
            print("        nothing newer and no dearer than what is already in use")

    print(f"\n{total} problem(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
