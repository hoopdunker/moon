import pytest
from unittest.mock import patch
from moon import tool_registry
from moon.agent import execute_step
from moon.llm import ConverseResult, ToolUse
from moon.models import ResourceSelection, Tool


def _tool_use(name, tool_id, input_data):
    return ConverseResult(
        stop_reason="tool_use",
        text="",
        tool_uses=[ToolUse(id=tool_id, name=name, input=input_data)],
        raw_content=[{"toolUse": {"toolUseId": tool_id, "name": name, "input": input_data}}],
    )


def _end_turn(text="done"):
    return ConverseResult(stop_reason="end_turn", text=text, tool_uses=[], raw_content=[{"text": text}])


def _resources(tool_names=None):
    return ResourceSelection(tool_names=tool_names or [], skill_names=[], guideline_names=[], reasoning="")


def test_get_handler_returns_callable_for_known_tool():
    handler = tool_registry.get_handler("get_pr_diff")
    assert callable(handler)


def test_get_handler_returns_none_for_unknown_tool():
    handler = tool_registry.get_handler("nonexistent_tool")
    assert handler is None


def test_get_handler_returns_none_for_mock_only_tools():
    handler = tool_registry.get_handler("get_alert_details")
    assert handler is None


def test_agent_uses_real_handler_when_registered():
    mock_tool = Tool(
        name="get_pr_diff",
        description="Gets PR diff",
        parameters={"type": "object", "properties": {}, "required": []},
        mock_response="THIS IS THE MOCK — should not appear",
    )
    fake_result = "real GitHub result"

    with patch("moon.llm.converse", side_effect=[
        _tool_use("get_pr_diff", "call_1", {"pr_number": 42, "repo": "acme/backend"}),
        _end_turn("review complete"),
    ]), patch("moon.tool_registry.get_handler", return_value=lambda **kw: fake_result):
        result = execute_step(0, "review the PR", [mock_tool], [], [], _resources(["get_pr_diff"]), [])

    assert result.tool_calls[0].output == fake_result
    assert result.tool_calls[0].output != "THIS IS THE MOCK — should not appear"


def test_agent_falls_back_to_mock_when_no_handler():
    mock_tool = Tool(
        name="get_alert_details",
        description="Gets alert",
        parameters={"type": "object", "properties": {}, "required": []},
        mock_response="mock alert data",
    )

    with patch("moon.llm.converse", side_effect=[
        _tool_use("get_alert_details", "call_1", {"alert_id": "CS-001"}),
        _end_turn("done"),
    ]), patch("moon.tool_registry.get_handler", return_value=None):
        result = execute_step(0, "triage alert", [mock_tool], [], [], _resources(["get_alert_details"]), [])

    assert result.tool_calls[0].output == "mock alert data"
