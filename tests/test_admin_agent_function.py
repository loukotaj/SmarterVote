import importlib
import sys
import types

import pytest


@pytest.fixture
def admin_agent_main(monkeypatch):
    functions_framework = types.ModuleType("functions_framework")
    functions_framework.cloud_event = lambda func: func
    cloudevents = types.ModuleType("cloudevents")
    cloudevents_http = types.ModuleType("cloudevents.http")
    cloudevents_http.CloudEvent = object
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)
    monkeypatch.setitem(sys.modules, "cloudevents", cloudevents)
    monkeypatch.setitem(sys.modules, "cloudevents.http", cloudevents_http)
    return importlib.import_module("functions.admin_agent.main")


def test_admin_agent_run_options_default_to_cheap_mode(admin_agent_main):
    assert admin_agent_main._options({"note": "refresh"}) == {"cheap_mode": True, "note": "refresh"}


def test_admin_agent_run_options_require_explicit_false_for_quality_profile(admin_agent_main):
    with pytest.raises(ValueError, match="requires explicit cheap_mode=false"):
        admin_agent_main._options({"model_profile": "quality"})

    assert admin_agent_main._options({"cheap_mode": False, "model_profile": "quality"}) == {
        "cheap_mode": False,
        "model_profile": "quality",
    }
