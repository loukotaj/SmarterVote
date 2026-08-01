"""Contract tests for the GitHub issue templates.

The templates are consumed by two things that break silently if the templates drift:

* ``web/src/lib/components/NoDataFallback.svelte`` deep-links to ``missing-data.yml`` and
  prefills the ``race-id`` and ``candidate-name`` field IDs.
* ``scripts/triage_race_issues.py`` parses the rendered issue body by field label and by the
  "What type of data is missing?" checkbox labels.

These tests pin that contract. They also guard against the two failures the templates already
shipped with once: labels that don't exist in the repo (GitHub drops them silently) and links
to the pre-rename ``loukotaj/SmarterVote`` URL.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"

MODULE_PATH = REPO_ROOT / "scripts" / "triage_race_issues.py"
_spec = importlib.util.spec_from_file_location("triage_race_issues_contract", MODULE_PATH)
triage = importlib.util.module_from_spec(_spec)
sys.modules["triage_race_issues_contract"] = triage
_spec.loader.exec_module(triage)

# Labels the templates are allowed to apply. Anything else is dropped silently by GitHub
# unless it is also created in scripts/triage_race_issues.py::ensure_labels.
DECLARABLE_LABELS = {"bug", "data-request", "race-request", "community-contribution"}

FORM_TEMPLATES = ["bug_report.yml", "missing-data.yml", "race-request.yml"]


def load(name: str) -> dict:
    return yaml.safe_load((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def fields(template: dict) -> dict[str, dict]:
    return {block["id"]: block for block in template["body"] if "id" in block and block["type"] != "markdown"}


def all_template_text() -> str:
    return "\n".join((TEMPLATE_DIR / path.name).read_text(encoding="utf-8") for path in TEMPLATE_DIR.glob("*.yml"))


@pytest.mark.parametrize("name", FORM_TEMPLATES)
class TestTemplateStructure:
    def test_parses_and_has_required_top_level_keys(self, name):
        template = load(name)
        assert template["name"] and template["description"]
        assert isinstance(template["body"], list) and template["body"]

    def test_only_declares_labels_that_exist(self, name):
        for label in load(name).get("labels", []):
            assert label in DECLARABLE_LABELS, f"{name} declares '{label}', which GitHub will drop"

    def test_required_fields_are_marked_required(self, name):
        for field in fields(load(name)).values():
            if field["type"] in {"input", "textarea", "dropdown"}:
                assert isinstance(field.get("validations", {}).get("required", False), bool)


class TestNoStaleRepoUrls:
    def test_no_pre_rename_org_links(self):
        # The repo was renamed loukotaj/SmarterVote -> SmarterVote/SmarterVote. The old path
        # only works via GitHub's redirect and breaks if anyone ever claims it.
        assert "loukotaj/SmarterVote" not in all_template_text()

    def test_github_links_use_canonical_repo(self):
        for url in re.findall(r"https://github\.com/([\w.-]+/[\w.-]+)", all_template_text()):
            assert url == "SmarterVote/SmarterVote", f"unexpected repo link: {url}"


class TestMissingDataContract:
    """Pins what NoDataFallback.svelte and the triage script depend on."""

    def test_title_prefix_matches_triage_matcher(self):
        title = load("missing-data.yml")["title"]
        assert title.startswith("[Data]")
        assert any(title.startswith(prefix) for prefix in triage.RACE_ISSUE_TITLE_PREFIXES)

    def test_prefilled_field_ids_exist(self):
        # NoDataFallback.svelte sends ?race-id=...&candidate-name=...
        assert {"race-id", "candidate-name"} <= set(fields(self.template()))

    def test_svelte_component_still_targets_this_template(self):
        component = (REPO_ROOT / "web" / "src" / "lib" / "components" / "NoDataFallback.svelte").read_text(encoding="utf-8")
        assert 'template: "missing-data.yml"' in component
        assert '"race-id": raceId' in component
        assert '"candidate-name": candidateName' in component

    def test_checkbox_labels_match_triage_concern_map(self):
        options = fields(self.template())["data-type"]["attributes"]["options"]
        labels = {option["label"].strip().lower() for option in options}
        unmapped = labels - set(triage.REPORTED_TYPE_CONCERNS) - {"other"}
        assert not unmapped, f"triage script has no concern mapping for: {sorted(unmapped)}"
        assert set(triage.REPORTED_TYPE_CONCERNS) <= labels, "triage maps a checkbox the template no longer offers"

    def test_body_round_trips_through_the_triage_parser(self):
        rendered = "### Race ID\n\nnj-senate-2026\n\n### Candidate Name\n\nJane Smith\n"
        assert triage.resolve_race_id({"body": rendered}) == "nj-senate-2026"
        assert triage.extract_field(rendered, "Candidate Name") == "Jane Smith"


class TestRaceRequestContract:
    def test_title_prefix_matches_triage_matcher(self):
        title = load("race-request.yml")["title"]
        assert any(title.startswith(prefix) for prefix in triage.RACE_ISSUE_TITLE_PREFIXES)

    def test_race_id_label_is_parseable(self):
        label = fields(load("race-request.yml"))["race-id"]["attributes"]["label"]
        rendered = f"### {label}\n\ntx-governor-2026\n"
        assert triage.resolve_race_id({"body": rendered}) == "tx-governor-2026"

    def test_documented_id_examples_are_valid_race_ids(self):
        description = fields(load("race-request.yml"))["race-id"]["attributes"]["description"]
        examples = re.findall(r"`([a-z]{2}-[a-z0-9-]+-\d{4}(?:-special)?)`", description)
        assert len(examples) >= 5, "race ID guidance lost its worked examples"
        for example in examples:
            assert triage.RACE_ID_PATTERN.match(example), f"{example} violates the race ID pattern"

    def test_house_examples_use_zero_padded_districts(self):
        description = fields(load("race-request.yml"))["race-id"]["attributes"]["description"]
        for example in re.findall(r"`([a-z]{2}-house-\d+-\d{4})`", description):
            district = example.split("-")[2]
            assert len(district) == 2, f"{example} should zero-pad the district"


class TestConfig:
    def test_blank_issues_disabled_and_links_resolve_to_known_paths(self):
        config = yaml.safe_load((TEMPLATE_DIR / "config.yml").read_text(encoding="utf-8"))
        assert config["blank_issues_enabled"] is False
        for link in config["contact_links"]:
            assert link["name"] and link["about"]
            assert link["url"].startswith("https://")

    def test_contributing_guide_link_points_at_a_real_file(self):
        config = yaml.safe_load((TEMPLATE_DIR / "config.yml").read_text(encoding="utf-8"))
        contributing = [link for link in config["contact_links"] if "CONTRIBUTING" in link["url"]]
        assert contributing, "config.yml should link the contributing guide"
        assert (REPO_ROOT / "CONTRIBUTING.md").exists()
