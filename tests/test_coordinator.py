import pytest
from unittest.mock import patch
from moon.coordinator import select_resources, select_runbook
from moon.llm import ConverseResult, ToolUse
from moon.models import Guideline, Runbook, Skill, Tool


def _tool_result(name, input_data):
    return ConverseResult(
        stop_reason="tool_use",
        text="",
        tool_uses=[ToolUse(id="call_1", name=name, input=input_data)],
        raw_content=[{"toolUse": {"toolUseId": "call_1", "name": name, "input": input_data}}],
    )


def _text_result():
    return ConverseResult(stop_reason="end_turn", text="", tool_uses=[], raw_content=[])


RUNBOOKS = [
    Runbook(id="rb1", description="First runbook", tags=["a"], steps=["step 1"]),
    Runbook(id="rb2", description="Second runbook", tags=["b"], steps=["step 1"]),
]


# ── select_runbook ────────────────────────────────────────────────────────────

def test_select_runbook_returns_selection():
    with patch("moon.llm.converse", return_value=_tool_result("select_runbook", {"runbook_id": "rb1", "reasoning": "Best match"})):
        result = select_runbook("test task", RUNBOOKS)

    assert result.runbook_id == "rb1"
    assert result.reasoning == "Best match"


def test_select_runbook_calls_converse_once():
    with patch("moon.llm.converse", return_value=_tool_result("select_runbook", {"runbook_id": "rb2", "reasoning": "Good fit"})) as mock:
        select_runbook("task", RUNBOOKS)

    mock.assert_called_once()


def test_select_runbook_includes_all_runbook_ids_in_prompt():
    with patch("moon.llm.converse", return_value=_tool_result("select_runbook", {"runbook_id": "rb1", "reasoning": ""})) as mock:
        select_runbook("task", RUNBOOKS)

    messages = mock.call_args.kwargs["messages"]
    content = messages[0]["content"][0]["text"]
    assert "rb1" in content
    assert "rb2" in content


def test_select_runbook_no_tool_use_raises():
    with patch("moon.llm.converse", return_value=_text_result()):
        with pytest.raises(RuntimeError, match="failed to select a runbook"):
            select_runbook("task", RUNBOOKS)


def test_select_runbook_uses_forced_tool():
    with patch("moon.llm.converse", return_value=_tool_result("select_runbook", {"runbook_id": "rb1", "reasoning": ""})) as mock:
        select_runbook("task", RUNBOOKS)

    assert mock.call_args.kwargs["force_tool"] == "select_runbook"


def test_select_runbook_single_runbook_skips_llm():
    runbooks = [Runbook(id="rb1", description="Only runbook", tags=["test"], steps=["step 1"])]
    with patch("moon.llm.converse") as mock:
        result = select_runbook("any task", runbooks)

    mock.assert_not_called()
    assert result.runbook_id == "rb1"
    assert result.via_llm is False


def test_select_runbook_tag_match_skips_llm():
    runbooks = [
        Runbook(id="pr_security_review", description="Review PRs", tags=["security", "pr"], steps=["s"]),
        Runbook(id="alert_triage", description="Triage alerts", tags=["alert", "triage"], steps=["s"]),
    ]
    with patch("moon.llm.converse") as mock:
        result = select_runbook("review the security pr", runbooks)

    mock.assert_not_called()
    assert result.runbook_id == "pr_security_review"
    assert result.via_llm is False


def test_select_runbook_ambiguous_tags_falls_back_to_llm():
    runbooks = [
        Runbook(id="rb1", description="First", tags=["security"], steps=["s"]),
        Runbook(id="rb2", description="Second", tags=["security"], steps=["s"]),
    ]
    with patch("moon.llm.converse", return_value=_tool_result("select_runbook", {"runbook_id": "rb1", "reasoning": "Best fit"})) as mock:
        result = select_runbook("security task", runbooks)

    mock.assert_called_once()
    assert result.via_llm is True


def test_select_runbook_tag_match_requires_score_at_least_2():
    runbooks = [
        Runbook(id="rb1", description="First", tags=["security"], steps=["s"]),
        Runbook(id="rb2", description="Second", tags=["other"], steps=["s"]),
    ]
    with patch("moon.llm.converse", return_value=_tool_result("select_runbook", {"runbook_id": "rb1", "reasoning": ""})) as mock:
        select_runbook("a security thing", runbooks)

    mock.assert_called_once()


# ── select_resources ──────────────────────────────────────────────────────────

def _resources_result(agent_model="sonnet", **kwargs):
    data = {"tool_names": [], "skill_names": [], "guideline_names": [], "agent_model": agent_model, "reasoning": "", **kwargs}
    return _tool_result("select_resources", data)


def test_select_resources_returns_selection():
    with patch("moon.llm.converse", return_value=_resources_result(tool_names=["tool_a"], skill_names=["skill_a"], agent_model="claude-sonnet")):
        result = select_resources("step text", 0, "task", [], [], [])

    assert result.tool_names == ["tool_a"]
    assert result.skill_names == ["skill_a"]
    assert result.agent_model == "claude-sonnet"


def test_select_resources_includes_step_index_in_prompt():
    with patch("moon.llm.converse", return_value=_resources_result()) as mock:
        select_resources("step text", 2, "task", [], [], [])

    content = mock.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert "Step 3" in content


def test_select_resources_no_tool_use_raises():
    with patch("moon.llm.converse", return_value=_text_result()):
        with pytest.raises(RuntimeError, match="failed to select resources"):
            select_resources("step", 0, "task", [], [], [])


def test_select_resources_uses_forced_tool():
    with patch("moon.llm.converse", return_value=_resources_result()) as mock:
        select_resources("step", 0, "task", [], [], [])

    assert mock.call_args.kwargs["force_tool"] == "select_resources"


def test_select_resources_tool_schema_includes_model_enum():
    from moon import config
    with patch("moon.llm.converse", return_value=_resources_result()) as mock:
        select_resources("step", 0, "task", [], [], [])

    tools = mock.call_args.kwargs["tools"]
    model_prop = tools[0]["toolSpec"]["inputSchema"]["json"]["properties"]["agent_model"]
    assert "enum" in model_prop
    assert set(model_prop["enum"]) == set(config.MODEL_REGISTRY.keys())


def test_select_resources_prompt_includes_model_descriptions():
    with patch("moon.llm.converse", return_value=_resources_result()) as mock:
        select_resources("step", 0, "task", [], [], [])

    from moon import config
    tools = mock.call_args.kwargs["tools"]
    desc = tools[0]["toolSpec"]["inputSchema"]["json"]["properties"]["agent_model"]["description"]
    for name in config.MODEL_REGISTRY:
        assert name in desc


def test_select_resources_returns_coordinator_chosen_model():
    with patch("moon.llm.converse", return_value=_resources_result(agent_model="claude-opus")):
        result = select_resources("synthesise report", 0, "task", [], [], [])

    assert result.agent_model == "claude-opus"


def test_select_resources_defaults_agent_model_when_omitted():
    data = {"tool_names": [], "skill_names": [], "guideline_names": [], "reasoning": ""}
    with patch("moon.llm.converse", return_value=_tool_result("select_resources", data)):
        result = select_resources("simple step", 0, "task", [], [], [])

    assert result.agent_model == "sonnet"
