import pytest
from unittest.mock import patch, MagicMock
from moon import tool_registry


def test_get_handler_returns_callable_for_known_tool():
    handler = tool_registry.get_handler("get_pr_diff")
    assert callable(handler)


def test_get_handler_returns_none_for_unknown_tool():
    handler = tool_registry.get_handler("nonexistent_tool")
    assert handler is None


def test_get_handler_returns_none_for_mock_only_tools():
    # Tools like get_alert_details have no real handler yet — should fall back to mock
    handler = tool_registry.get_handler("get_alert_details")
    assert handler is None


def test_agent_uses_real_handler_when_registered():
    from moon.agent import execute_step
    from moon.models import Tool, ResourceSelection

    mock_tool = Tool(
        name="get_pr_diff",
        description="Gets PR diff",
        parameters={"type": "object", "properties": {}, "required": []},
        mock_response="THIS IS THE MOCK — should not appear",
    )

    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "get_pr_diff"
    tool_use_block.id = "call_1"
    tool_use_block.input = {"pr_number": 42, "repo": "acme/backend"}

    tool_use_response = MagicMock()
    tool_use_response.content = [tool_use_block]
    tool_use_response.stop_reason = "tool_use"

    end_turn_block = MagicMock()
    end_turn_block.type = "text"
    end_turn_block.text = "review complete"
    end_turn_response = MagicMock()
    end_turn_response.content = [end_turn_block]
    end_turn_response.stop_reason = "end_turn"

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [tool_use_response, end_turn_response]

    resources = ResourceSelection(tool_names=["get_pr_diff"], skill_names=[], guideline_names=[], reasoning="")

    fake_result = "real GitHub result"

    with patch("moon.agent._get_client", return_value=mock_client), \
         patch("moon.tool_registry.get_handler", return_value=lambda **kw: fake_result):
        result = execute_step(0, "review the PR", [mock_tool], [], [], resources, [])

    assert result.tool_calls[0].output == fake_result
    assert result.tool_calls[0].output != "THIS IS THE MOCK — should not appear"


def test_agent_falls_back_to_mock_when_no_handler():
    from moon.agent import execute_step
    from moon.models import Tool, ResourceSelection

    mock_tool = Tool(
        name="get_alert_details",
        description="Gets alert",
        parameters={"type": "object", "properties": {}, "required": []},
        mock_response="mock alert data",
    )

    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "get_alert_details"
    tool_use_block.id = "call_1"
    tool_use_block.input = {"alert_id": "CS-001"}

    tool_use_response = MagicMock()
    tool_use_response.content = [tool_use_block]
    tool_use_response.stop_reason = "tool_use"

    end_turn_block = MagicMock()
    end_turn_block.type = "text"
    end_turn_block.text = "done"
    end_turn_response = MagicMock()
    end_turn_response.content = [end_turn_block]
    end_turn_response.stop_reason = "end_turn"

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [tool_use_response, end_turn_response]

    resources = ResourceSelection(tool_names=["get_alert_details"], skill_names=[], guideline_names=[], reasoning="")

    with patch("moon.agent._get_client", return_value=mock_client), \
         patch("moon.tool_registry.get_handler", return_value=None):
        result = execute_step(0, "triage alert", [mock_tool], [], [], resources, [])

    assert result.tool_calls[0].output == "mock alert data"
