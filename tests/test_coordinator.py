import pytest
from unittest.mock import MagicMock, patch
from moon.coordinator import select_resources, select_runbook
from moon.models import Guideline, Runbook, Skill, Tool


def _tool_use_response(name, input_data):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_data
    response = MagicMock()
    response.content = [block]
    return response


def _text_response():
    block = MagicMock()
    block.type = "text"
    response = MagicMock()
    response.content = [block]
    return response


RUNBOOKS = [
    Runbook(id="rb1", description="First runbook", tags=["a"], steps=["step 1"]),
    Runbook(id="rb2", description="Second runbook", tags=["b"], steps=["step 1"]),
]


def test_select_runbook_returns_selection():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_runbook", {"runbook_id": "rb1", "reasoning": "Best match"}
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        result = select_runbook("test task", RUNBOOKS)

    assert result.runbook_id == "rb1"
    assert result.reasoning == "Best match"


def test_select_runbook_calls_api_once():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_runbook", {"runbook_id": "rb2", "reasoning": "Good fit"}
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        select_runbook("task", RUNBOOKS)

    mock_client.messages.create.assert_called_once()


def test_select_runbook_includes_all_runbook_ids_in_prompt():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_runbook", {"runbook_id": "rb1", "reasoning": ""}
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        select_runbook("task", RUNBOOKS)

    content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "rb1" in content
    assert "rb2" in content


def test_select_runbook_no_tool_use_raises():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _text_response()
    with patch("moon.coordinator._get_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="failed to select a runbook"):
            select_runbook("task", RUNBOOKS)


def test_select_runbook_uses_forced_tool_choice():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_runbook", {"runbook_id": "rb1", "reasoning": ""}
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        select_runbook("task", RUNBOOKS)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "select_runbook"}


def test_select_resources_returns_selection():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_resources",
        {"tool_names": ["tool_a"], "skill_names": ["skill_a"], "guideline_names": [], "reasoning": "Needed"},
    )
    tools = [Tool(name="tool_a", description="A tool", parameters={"type": "object"}, mock_response="m")]
    skills = [Skill(name="skill_a", content="content")]
    guidelines = [Guideline(name="guide_a", content="content")]

    with patch("moon.coordinator._get_client", return_value=mock_client):
        result = select_resources("step text", 0, "task", tools, skills, guidelines)

    assert result.tool_names == ["tool_a"]
    assert result.skill_names == ["skill_a"]
    assert result.guideline_names == []


def test_select_resources_includes_step_index_in_prompt():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_resources",
        {"tool_names": [], "skill_names": [], "guideline_names": [], "reasoning": ""},
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        select_resources("step text", 2, "task", [], [], [])

    content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Step 3" in content  # 0-indexed → displayed as 1-indexed


def test_select_resources_no_tool_use_raises():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _text_response()
    with patch("moon.coordinator._get_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="failed to select resources"):
            select_resources("step", 0, "task", [], [], [])


def test_select_resources_uses_forced_tool_choice():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_resources",
        {"tool_names": [], "skill_names": [], "guideline_names": [], "reasoning": ""},
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        select_resources("step", 0, "task", [], [], [])

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "select_resources"}


# --- _tag_match / fast-path ---

def test_select_runbook_single_runbook_skips_llm():
    runbooks = [Runbook(id="rb1", description="Only runbook", tags=["test"], steps=["step 1"])]
    mock_client = MagicMock()
    with patch("moon.coordinator._get_client", return_value=mock_client):
        result = select_runbook("any task", runbooks)

    mock_client.messages.create.assert_not_called()
    assert result.runbook_id == "rb1"
    assert result.via_llm is False


def test_select_runbook_tag_match_skips_llm():
    runbooks = [
        Runbook(id="pr_security_review", description="Review PRs", tags=["security", "pr"], steps=["s"]),
        Runbook(id="alert_triage", description="Triage alerts", tags=["alert", "triage"], steps=["s"]),
    ]
    mock_client = MagicMock()
    with patch("moon.coordinator._get_client", return_value=mock_client):
        result = select_runbook("review the security pr", runbooks)

    mock_client.messages.create.assert_not_called()
    assert result.runbook_id == "pr_security_review"
    assert result.via_llm is False


def test_select_runbook_ambiguous_tags_falls_back_to_llm():
    # Both runbooks score 1 — no clear winner, should call LLM
    runbooks = [
        Runbook(id="rb1", description="First", tags=["security"], steps=["s"]),
        Runbook(id="rb2", description="Second", tags=["security"], steps=["s"]),
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_runbook", {"runbook_id": "rb1", "reasoning": "Best fit"}
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        result = select_runbook("security task", runbooks)

    mock_client.messages.create.assert_called_once()
    assert result.via_llm is True


def test_select_runbook_tag_match_requires_score_at_least_2():
    # Score of 1 should not be enough for tag match
    runbooks = [
        Runbook(id="rb1", description="First", tags=["security"], steps=["s"]),
        Runbook(id="rb2", description="Second", tags=["other"], steps=["s"]),
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(
        "select_runbook", {"runbook_id": "rb1", "reasoning": ""}
    )
    with patch("moon.coordinator._get_client", return_value=mock_client):
        result = select_runbook("a security thing", runbooks)

    mock_client.messages.create.assert_called_once()
