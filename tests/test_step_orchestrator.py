from pipeline_client.backend.step_orchestrator import (
    PIPELINE_ORDER,
    build_payload,
    remaining_steps,
    state_from_artifact,
    update_state,
)


def test_state_from_artifact_and_updates():
    artifact = {
        "step": "step01a_metadata",
        "input": {"race_id": "xy"},
        "output": {"id": "xy"},
    }

    step, state = state_from_artifact(artifact)
    assert step == "step01a_metadata"
    assert state["race_id"] == "xy"
    assert state["race_json"] == {"id": "xy"}

    state = update_state("step01b_discovery", state, [1, 2])
    assert state["sources"] == [1, 2]


def test_build_payload_and_remaining_steps():
    state = {
        "race_id": "r1",
        "race_json": {"foo": 1},
        "sources": [{"url": "a"}],
        "raw_content": [{"text": "hi"}],
    }

    payload = build_payload("step01b_discovery", state)
    assert payload == {"race_id": "r1", "race_json": {"foo": 1}}

    payload = build_payload("step01c_fetch", state)
    assert payload == {"sources": [{"url": "a"}]}

    payload = build_payload("step01d_extract", state)
    assert payload == {"raw_content": [{"text": "hi"}]}

    nxt = remaining_steps("step01a_metadata", None)
    assert nxt == [PIPELINE_ORDER[1]]

    all_steps = remaining_steps("step01a_metadata", ["all"])
    assert all_steps == PIPELINE_ORDER[1:]
