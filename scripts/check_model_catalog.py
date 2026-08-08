"""Check ``shared/model_catalog.py`` against OpenRouter's live model list.

Why this exists
---------------
The catalog hardcodes prices, cache prices, context windows, capability scores
and per-role model choices. All of it is written by hand, against a provider
catalog that changes weekly. Three classes of bug have shipped from this:

- **Stale prices.** deepseek-v4-flash sat at $0.077/$0.154 long after repricing
  to $0.14/$0.28. Every "cheapest capable model" judgment built on it was wrong.
- **Version strings read as integers.** Grok sorts by decimal, so 4.20
  (2026-03-31) is *older* than 4.3 (2026-04-30). Reading it the other way put
  the premium reviewer on an older model than the default one.
- **Price mistaken for capability.** The escalation map sent
  deepseek-v4-flash-0731 (intelligence 49.9) to nemotron-3-ultra (37.8) at 6.7x
  the input price. The old version of this script checked that an escalation
  target cost *more* and reported that downgrade as healthy for months. Open
  weights broke the price/capability correlation that check depended on; the
  capability check below replaces it.

None of it is catchable by the test suite, because ``tests/conftest.py`` mocks
all network access by design. So this is a script, run deliberately, not a test.

    python scripts/check_model_catalog.py           # report + exit 1 on drift
    python scripts/check_model_catalog.py --quiet   # errors only

What is checked (these fail)
----------------------------
1. Every catalog entry is still served by OpenRouter.
2. Catalog input, output and cached-input prices match live prices exactly.
3. Context windows match live, where OpenRouter reports one.
4. Every model named by a profile role or the escalation map is catalogued.
5. Every escalation edge climbs the **intelligence index**. A lateral or
   downward edge means a stalled model "escalates" into something no better.
6. For each role, `premium` is not worse than `default` — never a lower
   intelligence score, and never older when both come from the same provider.
7. The roster adjudicator differs from the `primary` and `roster` model of every
   profile. That separation is the gate's entire claim to independence, and it
   is load-bearing on a publish path.
8. No model ID is hardcoded anywhere outside the catalog. This is the structural
   fix for the drift that produced four separate copies of the chamber-forecast
   model, two of which were stale.

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
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.model_catalog import (  # noqa: E402
    ADJUDICATOR_MODEL,
    MODEL_CATALOG,
    MODEL_ESCALATION,
    MODEL_ROLES,
    PROFILE_DEFAULTS,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Tolerance for float comparison of per-million prices. OpenRouter reports
# per-token strings like "0.0000001"; scaling to per-million reintroduces binary
# float error well below a hundredth of a cent, which is not real drift.
PRICE_EPSILON = 1e-6

# Files that may legitimately spell out a model ID: the catalog defines them,
# and the generated frontend copy is derived from it by build script.
_HARDCODE_EXEMPT = (
    Path("shared/model_catalog.py"),
    Path("scripts/check_model_catalog.py"),
    Path("web/src/lib/config/modelCatalog.ts"),
)
# Tests assert on concrete model IDs on purpose — that is the point of them.
_HARDCODE_EXEMPT_PATTERNS = ("test_", "_test.", ".test.", ".spec.", "conftest.py")
_HARDCODE_SEARCH_DIRS = ("shared", "pipeline_client", "services", "smartervote_mcp", "web/src", "infra")
_HARDCODE_SUFFIXES = {".py", ".ts", ".svelte", ".tf", ".yaml", ".yml"}
# `provider/model-name` inside a string literal. Deliberately anchored on the
# providers we actually use rather than any slash-separated pair, so ordinary
# paths and URLs do not trip it.
_MODEL_ID_PATTERN = re.compile(
    r"""["'](openai|anthropic|google|deepseek|x-ai|nvidia|meta-llama|mistralai|qwen)/[a-z0-9][\w.\-]*["']"""
)


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
    if raw in (None, ""):
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
            ("input_cache_read", spec.cached_input_per_m, "cached input"),
        ):
            actual = _per_million(record, field)
            if actual is None:
                if recorded is not None:
                    errors.append(
                        f"{model_id}: catalog records a {label} price of ${recorded:g}/M but OpenRouter reports none"
                    )
                continue
            if recorded is None:
                errors.append(f"{model_id}: OpenRouter reports a {label} price of ${actual:g}/M but the catalog records none")
                continue
            if abs(actual - recorded) > PRICE_EPSILON:
                errors.append(f"{model_id}: {label} price is ${actual:g}/M live, catalog says ${recorded:g}/M")
        live_ctx = record.get("context_length")
        if live_ctx and spec.context_window_tokens and int(live_ctx) != int(spec.context_window_tokens):
            errors.append(f"{model_id}: context window is {live_ctx} live, catalog says {spec.context_window_tokens}")
        if spec.intelligence is None:
            errors.append(f"{model_id}: no intelligence score recorded")
    return errors


def _check_profiles(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """Every role must name a model we have a spec for and that is actually served."""
    errors: List[str] = []
    for profile, roles in sorted(PROFILE_DEFAULTS.items()):
        for role in sorted(MODEL_ROLES):
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
    """An escalation must buy capability.

    Intelligence, not price. This check used to compare output price, which is
    what let a 12-point downgrade read as an upgrade for months.
    """
    errors: List[str] = []
    for source, target in sorted(MODEL_ESCALATION.items()):
        missing = [label for label, mid in (("source", source), ("target", target)) if mid not in MODEL_CATALOG]
        for label in missing:
            mid = source if label == "source" else target
            errors.append(f"escalation {source} -> {target}: {label} {mid} is not in MODEL_CATALOG")
        if missing:
            continue
        source_iq = MODEL_CATALOG[source].intelligence
        target_iq = MODEL_CATALOG[target].intelligence
        if target_iq <= source_iq:
            errors.append(
                f"escalation {source} -> {target}: target is not more capable "
                f"({target_iq} vs {source_iq} on the intelligence index) -- escalating here buys nothing"
            )
    return errors


def _check_premium_not_worse(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """Paying for `premium` must not hand you something worse than `default` gives away.

    Checked two ways, because neither signal is sufficient alone:

    - **Capability**, always. A premium role scoring below the default role for
      the same job is flagged regardless of vintage or price.
    - **Recency, within one provider only.** Release dates only compare when the
      models come from the same family; gpt-5.6-terra being older than
      deepseek-v4-flash-0731 says nothing about which is stronger. Restricting
      to one provider is exactly the shape of the grok bug, where 4.20 and 4.3
      were the same price from the same provider and only the date revealed it.
    """
    errors: List[str] = []
    default, premium = PROFILE_DEFAULTS.get("default", {}), PROFILE_DEFAULTS.get("premium", {})
    for role in sorted(MODEL_ROLES):
        cheap_id, good_id = default.get(role), premium.get(role)
        if not cheap_id or not good_id or cheap_id == good_id:
            continue
        if cheap_id in MODEL_CATALOG and good_id in MODEL_CATALOG:
            cheap_iq, good_iq = MODEL_CATALOG[cheap_id].intelligence, MODEL_CATALOG[good_id].intelligence
            if good_iq < cheap_iq:
                errors.append(
                    f"role {role!r}: premium uses {good_id} ({good_iq}) which is LESS capable "
                    f"than default's {cheap_id} ({cheap_iq})"
                )
        if _provider(cheap_id) != _provider(good_id):
            continue
        cheap_date, good_date = _released(live.get(cheap_id)), _released(live.get(good_id))
        if cheap_date and good_date and good_date < cheap_date:
            errors.append(
                f"role {role!r}: premium uses {good_id} ({good_date}) which is OLDER than "
                f"default's same-provider {cheap_id} ({cheap_date})"
            )
    return errors


def _check_adjudicator(live: Dict[str, Dict[str, Any]]) -> List[str]:
    """The roster gate must not be judged by the model that produced the evidence.

    Roster edits are made from roster-phase loops (the `roster` model) and from
    metadata/refinement loops (the `primary` model), so the adjudicator has to
    differ from both, in every profile.
    """
    errors: List[str] = []
    if ADJUDICATOR_MODEL not in MODEL_CATALOG:
        errors.append(f"adjudicator {ADJUDICATOR_MODEL} is not in MODEL_CATALOG")
    if ADJUDICATOR_MODEL not in live:
        errors.append(f"adjudicator {ADJUDICATOR_MODEL} is not served by OpenRouter")
    for profile, roles in sorted(PROFILE_DEFAULTS.items()):
        for role in ("primary", "roster"):
            if roles.get(role) == ADJUDICATOR_MODEL:
                errors.append(
                    f"adjudicator {ADJUDICATOR_MODEL} is also profile {profile!r} role {role!r} -- "
                    f"the gate would be judging evidence it produced itself"
                )
    return errors


def _check_no_hardcoded_models() -> List[str]:
    """No model ID may be written down outside the catalog.

    Every drift bug this script exists to catch started as a second copy of a
    model ID. Deleting the possibility beats detecting the consequence.
    """
    errors: List[str] = []
    exempt = {(REPO_ROOT / path).resolve() for path in _HARDCODE_EXEMPT}
    for directory in _HARDCODE_SEARCH_DIRS:
        root = REPO_ROOT / directory
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in _HARDCODE_SUFFIXES or not path.is_file():
                continue
            if path.resolve() in exempt or "node_modules" in path.parts or ".svelte-kit" in path.parts:
                continue
            if any(marker in path.name for marker in _HARDCODE_EXEMPT_PATTERNS):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                match = _MODEL_ID_PATTERN.search(line)
                if match:
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    errors.append(
                        f"{rel}:{lineno}: hardcoded model ID {match.group(0)} -- import it from shared.model_catalog"
                    )
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
            # `:batch` variants price like a discount but settle asynchronously,
            # which no inline pipeline call can wait for; `:free` is rate-limited
            # and trains on the prompt. Neither is a substitute for the paid
            # synchronous endpoint, so neither belongs in this advice.
            if other_id.endswith((":free", ":batch")) or other_id.startswith("~") or _is_specialized(other_id):
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
        ("escalation climbs", _check_escalation()),
        ("premium not worse than default", _check_premium_not_worse(live)),
        ("adjudicator independence", _check_adjudicator(live)),
        ("no hardcoded model IDs", _check_no_hardcoded_models()),
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
