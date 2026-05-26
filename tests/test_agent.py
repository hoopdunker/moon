import pytest
from unittest.mock import patch
from moon.agent import _build_system_prompt, execute_step
from moon.llm import ConverseResult, ToolUse
from moon.models import Guideline, ResourceSelection, Skill, StepResult, Tool


def _resources(**kwargs):
    defaults = dict(tool_names=[], skill_names=[], guideline_names=[], agent_model="claude-sonnet", reasoning="")
    defaults.update(kwargs)
    return ResourceSelection(**defaults)


def _end_turn(text="Done."):
    return ConverseResult(
        stop_reason="end_turn",
        text=text,
        tool_uses=[],
        raw_content=[{"text": text}],
    )


def _tool_use(tool_name, tool_id, input_data):
    return ConverseResult(
        stop_reason="tool_use",
        text="",
        tool_uses=[ToolUse(id=tool_id, name=tool_name, input=input_data)],
        raw_content=[{"toolUse": {"toolUseId": tool_id, "name": tool_name, "input": input_data}}],
    )


# ── _build_system_prompt ──────────────────────────────────────────────────────

def test_build_system_prompt_empty():
    assert _build_system_prompt([], [], []) == ""


def test_build_system_prompt_with_skill():
    skills = [Skill(name="analyst", content="You are an analyst.")]
    result = _build_system_prompt(skills, [], [])
    assert "# Persona" in result
    assert "You are an analyst." in result


def test_build_system_prompt_multiple_skills_separated():
    skills = [Skill(name="a", content="Skill A"), Skill(name="b", content="Skill B")]
    result = _build_system_prompt(skills, [], [])
    assert "Skill A" in result
    assert "Skill B" in result
    assert "---" in result


def test_build_system_prompt_with_guideline():
    guidelines = [Guideline(name="policy", content="Follow the rules.")]
    result = _build_system_prompt([], guidelines, [])
    assert "# Guidelines" in result
    assert "Follow the rules." in result


def test_build_system_prompt_with_tool():
    tools = [Tool(name="my_tool", description="Does stuff", parameters={}, mock_response="m")]
    result = _build_system_prompt([], [], tools)
    assert "# Available Tools" in result
    assert "my_tool" in result
    assert "Does stuff" in result


def test_build_system_prompt_all_sections():
    result = _build_system_prompt(
        [Skill(name="s", content="skill")],
        [Guideline(name="g", content="guideline")],
        [Tool(name="t", description="tool", parameters={}, mock_response="m")],
    )
    assert "# Persona" in result
    assert "# Guidelines" in result
    assert "# Available Tools" in result


# ── execute_step ──────────────────────────────────────────────────────────────

def test_execute_step_plain_completion():
    with patch("moon.llm.converse", return_value=_end_turn("Step done.")) as mock:
        result = execute_step(0, "Do the thing", [], [], [], _resources(), [])

    assert result.step_index == 0
    assert result.output == "Step done."
    assert result.tool_calls == []
    mock.assert_called_once()


def test_execute_step_no_tools_passes_none_tools():
    with patch("moon.llm.converse", return_value=_end_turn()) as mock:
        execute_step(0, "step", [], [], [], _resources(), [])

    assert mock.call_args.kwargs["tools"] is None


def test_execute_step_with_tools_passes_tool_specs():
    mock_tool = Tool(name="lookup", description="Looks up", parameters={"type": "object"}, mock_response="m")
    with patch("moon.llm.converse", return_value=_end_turn()) as mock:
        execute_step(0, "step", [mock_tool], [], [], _resources(tool_names=["lookup"]), [])

    tools = mock.call_args.kwargs["tools"]
    assert tools is not None
    assert tools[0]["toolSpec"]["name"] == "lookup"


def test_execute_step_task_description_in_message():
    with patch("moon.llm.converse", return_value=_end_turn()) as mock:
        execute_step(0, "step", [], [], [], _resources(), [], task_description="Triage alert CS-001")

    content = mock.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert "Triage alert CS-001" in content


def test_execute_step_prior_context_in_message():
    prior = [StepResult(step_index=0, step_text="prior step", output="prior output", resources_used=_resources())]
    with patch("moon.llm.converse", return_value=_end_turn()) as mock:
        execute_step(1, "next step", [], [], [], _resources(), prior)

    content = mock.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert "prior output" in content


def test_execute_step_tool_use_loop():
    mock_tool = Tool(
        name="get_data",
        description="Gets data",
        parameters={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        mock_response="data retrieved",
    )
    with patch("moon.llm.converse", side_effect=[
        _tool_use("get_data", "call_123", {"id": "abc"}),
        _end_turn("Analysis complete."),
    ]):
        result = execute_step(0, "Retrieve and analyze", [mock_tool], [], [], _resources(tool_names=["get_data"]), [])

    assert result.output == "Analysis complete."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "get_data"
    assert result.tool_calls[0].input == {"id": "abc"}
    assert result.tool_calls[0].output == "data retrieved"


def test_execute_step_tool_result_appended_as_user_message():
    mock_tool = Tool(name="lookup", description="d", parameters={"type": "object"}, mock_response="the mock result")
    with patch("moon.llm.converse", side_effect=[
        _tool_use("lookup", "id_1", {}),
        _end_turn("done"),
    ]) as mock:
        execute_step(0, "step", [mock_tool], [], [], _resources(tool_names=["lookup"]), [])

    second_call_messages = mock.call_args_list[1].kwargs["messages"]
    tool_result_msg = second_call_messages[-1]
    assert tool_result_msg["role"] == "user"
    content = tool_result_msg["content"][0]
    assert "toolResult" in content
    assert content["toolResult"]["toolUseId"] == "id_1"
    assert content["toolResult"]["content"][0]["text"] == "the mock result"


def test_execute_step_multiple_tool_calls():
    mock_tool = Tool(name="lookup", description="d", parameters={"type": "object"}, mock_response="result")
    with patch("moon.llm.converse", side_effect=[
        _tool_use("lookup", "id_1", {"q": "first"}),
        _tool_use("lookup", "id_2", {"q": "second"}),
        _end_turn("final"),
    ]):
        result = execute_step(0, "step", [mock_tool], [], [], _resources(tool_names=["lookup"]), [])

    assert len(result.tool_calls) == 2
    assert result.output == "final"


def test_execute_step_resources_stored_on_result():
    resources = _resources(tool_names=["t"], skill_names=["s"])
    with patch("moon.llm.converse", return_value=_end_turn()):
        result = execute_step(0, "step", [], [], [], resources, [])

    assert result.resources_used is resources


def test_execute_step_uses_resolved_bedrock_model_id():
    from moon import config
    with patch("moon.llm.converse", return_value=_end_turn()) as mock:
        execute_step(0, "step", [], [], [], _resources(agent_model="claude-haiku"), [])

    model_used = mock.call_args.kwargs["model_id"]
    assert model_used == config.MODEL_REGISTRY["claude-haiku"]["bedrock_id"]
    assert model_used != "claude-haiku"


def test_execute_step_nova_pro_resolves_to_bedrock_id():
    from moon import config
    with patch("moon.llm.converse", return_value=_end_turn()) as mock:
        execute_step(0, "step", [], [], [], _resources(agent_model="nova-pro"), [])

    model_used = mock.call_args.kwargs["model_id"]
    assert model_used == config.MODEL_REGISTRY["nova-pro"]["bedrock_id"]


def test_execute_step_unimplemented_tool_returns_error_when_mocks_disabled():
    import moon.config as cfg
    mock_tool = Tool(name="some_tool", description="d", parameters={"type": "object"}, mock_response="mock data")
    original = cfg.MOCK_TOOLS
    try:
        cfg.MOCK_TOOLS = False
        with patch("moon.llm.converse", side_effect=[_tool_use("some_tool", "call_1", {}), _end_turn("done")]), \
             patch("moon.tool_registry.get_handler", return_value=None):
            result = execute_step(0, "step", [mock_tool], [], [], _resources(tool_names=["some_tool"]), [])
    finally:
        cfg.MOCK_TOOLS = original

    assert "not implemented" in result.tool_calls[0].output.lower()


def test_execute_step_tool_cache_hit_skips_handler():
    call_count = {"n": 0}

    def real_handler(**kwargs):
        call_count["n"] += 1
        return "real result"

    mock_tool = Tool(name="lookup", description="d", parameters={"type": "object"}, mock_response="m")
    cache: dict = {}
    with patch("moon.llm.converse", side_effect=[
        _tool_use("lookup", "id1", {"q": "same"}),
        _end_turn("first done"),
        _tool_use("lookup", "id2", {"q": "same"}),
        _end_turn("second done"),
    ]), patch("moon.tool_registry.get_handler", return_value=real_handler):
        execute_step(0, "step", [mock_tool], [], [], _resources(), [], tool_cache=cache)
        execute_step(1, "step", [mock_tool], [], [], _resources(), [], tool_cache=cache)

    assert call_count["n"] == 1


def test_execute_step_no_cache_calls_handler_each_time():
    call_count = {"n": 0}

    def real_handler(**kwargs):
        call_count["n"] += 1
        return "result"

    mock_tool = Tool(name="lookup", description="d", parameters={"type": "object"}, mock_response="m")
    with patch("moon.llm.converse", side_effect=[
        _tool_use("lookup", "id1", {"q": "x"}),
        _end_turn("done"),
        _tool_use("lookup", "id2", {"q": "x"}),
        _end_turn("done"),
    ]), patch("moon.tool_registry.get_handler", return_value=real_handler):
        execute_step(0, "step", [mock_tool], [], [], _resources(), [], tool_cache=None)
        execute_step(1, "step", [mock_tool], [], [], _resources(), [], tool_cache=None)

    assert call_count["n"] == 2
