"""Tests for Bedrock model resolution, coordinator model selection, and agent model dispatch."""
import pytest
from unittest.mock import MagicMock, patch
from moon import config
from moon.coordinator import select_resources
from moon.agent import execute_step
from moon.models import Guideline, ResourceSelection, Skill, Tool


# ── config.resolve_model ──────────────────────────────────────────────────────

def test_resolve_model_haiku():
    assert config.resolve_model("haiku") == "anthropic.claude-3-haiku-20240307-v1:0"


def test_resolve_model_sonnet():
    assert config.resolve_model("sonnet") == "anthropic.claude-3-5-sonnet-20241022-v2:0"


def test_resolve_model_opus():
    assert config.resolve_model("opus") == "anthropic.claude-3-opus-20240229-v1:0"


def test_resolve_model_unknown_falls_back_to_agent_model():
    result = config.resolve_model("unknown-model-xyz")
    assert result == config.AGENT_MODEL


def test_model_registry_all_entries_have_bedrock_id_and_use_for():
    for name, info in config.MODEL_REGISTRY.items():
        assert "bedrock_id" in info, f"{name} missing bedrock_id"
        assert "use_for" in info, f"{name} missing use_for"
        assert info["bedrock_id"].startswith("anthropic."), f"{name} bedrock_id unexpected format"


# ── ResourceSelection.agent_model ────────────────────────────────────────────

def test_resource_selection_default_agent_model():
    rs = ResourceSelection(tool_names=[], skill_names=[], guideline_names=[])
    assert rs.agent_model == "sonnet"


def test_resource_selection_explicit_agent_model():
    rs = ResourceSelection(tool_names=[], skill_names=[], guideline_names=[], agent_model="haiku")
    assert rs.agent_model == "haiku"


# ── coordinator select_resources returns agent_model ─────────────────────────

def _tool_use_response(name, input_data):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_data
    response = MagicMock()
    response.content = [block]
    return response


def test_select_resources_returns_coordinator_chosen_model():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_resources",
        {"tool_names": [], "skill_names": [], "guideline_names": [], "agent_model": "opus", "reasoning": "complex"},
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        result = select_resources("synthesise report", 0, "task", [], [], [])

    assert result.agent_model == "opus"


def test_select_resources_defaults_agent_model_when_omitted():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_resources",
        {"tool_names": [], "skill_names": [], "guideline_names": [], "reasoning": ""},
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        result = select_resources("simple step", 0, "task", [], [], [])

    assert result.agent_model == "sonnet"  # model default


def test_select_resources_tool_schema_includes_model_enum():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_resources",
        {"tool_names": [], "skill_names": [], "guideline_names": [], "agent_model": "haiku", "reasoning": ""},
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        select_resources("step", 0, "task", [], [], [])

    call_kwargs = mock_client.messages.create.call_args.kwargs
    tool_schema = call_kwargs["tools"][0]["input_schema"]
    model_prop = tool_schema["properties"]["agent_model"]
    assert "enum" in model_prop
    assert set(model_prop["enum"]) == set(config.MODEL_REGISTRY.keys())


def test_select_resources_prompt_includes_model_descriptions():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_resources",
        {"tool_names": [], "skill_names": [], "guideline_names": [], "agent_model": "sonnet", "reasoning": ""},
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        select_resources("step", 0, "task", [], [], [])

    # The model menu is baked into the tool description, not the user message
    call_kwargs = mock_client.messages.create.call_args.kwargs
    tool_schema = call_kwargs["tools"][0]
    model_desc = tool_schema["input_schema"]["properties"]["agent_model"]["description"]
    for name in config.MODEL_REGISTRY:
        assert name in model_desc


# ── agent uses resolved Bedrock model ID ─────────────────────────────────────

def _end_turn(text="Done."):
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    return response


def _resources(agent_model="sonnet", **kwargs):
    defaults = dict(tool_names=[], skill_names=[], guideline_names=[], reasoning="")
    defaults.update(kwargs)
    return ResourceSelection(agent_model=agent_model, **defaults)


def test_agent_uses_bedrock_model_id_not_friendly_name():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _end_turn()

    with patch("moon.agent._get_client", return_value=mock_client):
        execute_step(0, "step", [], [], [], _resources(agent_model="haiku"), [])

    model_used = mock_client.messages.create.call_args.kwargs["model"]
    assert model_used == config.MODEL_REGISTRY["haiku"]["bedrock_id"]
    assert model_used != "haiku"  # full Bedrock ID sent, not bare friendly name


def test_agent_sonnet_resolves_to_sonnet_bedrock_id():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _end_turn()

    with patch("moon.agent._get_client", return_value=mock_client):
        execute_step(0, "step", [], [], [], _resources(agent_model="sonnet"), [])

    model_used = mock_client.messages.create.call_args.kwargs["model"]
    assert model_used == config.MODEL_REGISTRY["sonnet"]["bedrock_id"]


def test_agent_opus_resolves_to_opus_bedrock_id():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _end_turn()

    with patch("moon.agent._get_client", return_value=mock_client):
        execute_step(0, "step", [], [], [], _resources(agent_model="opus"), [])

    model_used = mock_client.messages.create.call_args.kwargs["model"]
    assert model_used == config.MODEL_REGISTRY["opus"]["bedrock_id"]


def test_agent_unknown_model_falls_back_to_agent_model_default():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _end_turn()

    with patch("moon.agent._get_client", return_value=mock_client):
        execute_step(0, "step", [], [], [], _resources(agent_model="nonexistent"), [])

    model_used = mock_client.messages.create.call_args.kwargs["model"]
    assert model_used == config.AGENT_MODEL
