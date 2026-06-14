"""Tests for model-aware agent context budgeting."""

from pipeline_client.agent.context import AgentContext, AgentContextBudget, estimate_tokens


def _budget(**overrides):
    values = {
        "context_window_tokens": 32_000,
        "target_input_tokens": 12_000,
        "maximum_input_tokens": 16_000,
        "reserved_output_tokens": 4_000,
        "minimum_context_headroom": 4_000,
        "max_single_tool_result_tokens": 6_000,
        "max_search_results": 3,
        "max_retained_tool_turns": 3,
        "max_iterations": 10,
        "max_output_tokens": 4_000,
        "narrow_phase": False,
    }
    values.update(overrides)
    return AgentContextBudget(**values)


def _tool_round(index, content):
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": f"call-{index}", "function": {"name": "fetch_page", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": f"call-{index}", "content": content},
    ]


def test_model_budget_uses_large_catalog_window():
    budget = AgentContextBudget.for_model(
        "openai/gpt-5.4-mini",
        phase_name="discovery",
        max_iterations=15,
        max_output_tokens=16_384,
    )

    assert budget.context_window_tokens == 400_000
    assert budget.target_input_tokens == 300_000
    assert budget.maximum_input_tokens < budget.context_window_tokens
    assert budget.maximum_input_tokens + budget.reserved_output_tokens <= budget.context_window_tokens


def test_ten_large_tool_rounds_stay_below_hard_maximum():
    context = AgentContext(_budget(), task_text="Jane Doe healthcare policy")
    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "user"}]
    for index in range(10):
        raw = (
            f"Source https://example.com/{index}\n\n"
            + ("Unrelated background material. " * 2_000)
            + "\n\nJane Doe healthcare policy details and dated evidence. "
            + ("Relevant evidence. " * 1_000)
        )
        content = context.prepare_tool_result("fetch_page", raw, source_url=f"https://example.com/{index}")
        messages.extend(_tool_round(index, content))

    prepared = context.prepare_messages(messages)

    assert prepared.estimated_input_tokens <= context.budget.maximum_input_tokens
    assert prepared.compacted_results > 0 or prepared.dropped_tool_turns > 0
    assert "https://example.com/0" in prepared.messages[2]["content"]


def test_duplicate_sources_are_omitted_after_first_fetch():
    context = AgentContext(_budget(), task_text="candidate issue")
    first = context.prepare_tool_result(
        "fetch_page",
        "candidate issue evidence",
        source_url="https://example.com/source",
    )
    duplicate = context.prepare_tool_result(
        "fetch_page",
        "changed wrapper but same source",
        source_url="https://example.com/source",
    )

    assert first == "candidate issue evidence"
    assert duplicate.startswith("Duplicate result omitted")
    assert context.deduplicated_results == 1


def test_relevant_excerpt_and_url_survive_truncation():
    context = AgentContext(
        _budget(max_single_tool_result_tokens=100),
        task_text="Jane Doe healthcare",
    )
    raw = ("generic material " * 500) + "\n\nJane Doe healthcare plan is documented here."

    result = context.prepare_tool_result("fetch_page", raw, source_url="https://example.com/health")
    prepared = context.prepare_messages(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
            *_tool_round(1, result),
        ]
    )

    assert "Jane Doe healthcare plan" in result
    assert "https://example.com/health" in prepared.messages[2]["content"]
    assert context.truncated_results == 1


def test_search_results_are_compact_and_bounded():
    context = AgentContext(_budget(max_search_results=2), task_text="race")
    result = context.prepare_tool_result(
        "web_search",
        [
            {"title": "One", "url": "https://one.example", "snippet": "a" * 2_000, "extra": "drop"},
            {"title": "Two", "url": "https://two.example", "snippet": "two"},
            {"title": "Three", "url": "https://three.example", "snippet": "three"},
        ],
    )

    assert result.count('"url"') == 2
    assert "extra" not in result
    assert estimate_tokens(result) < 2_000
