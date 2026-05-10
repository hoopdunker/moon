import pytest
from unittest.mock import MagicMock, call, patch
from moon.executor import execute_task
from moon.models import (
    Catalog, Guideline, ResourceSelection, RunResult, Runbook,
    RunbookSelection, Skill, StepResult, Task, Tool,
)


def _catalog(runbook_id="rb1", steps=None, tools=None):
    return Catalog(
        runbooks=[Runbook(
            id=runbook_id,
            description="Test runbook",
            tags=["test"],
            steps=steps or ["step 1"],
        )],
        tools=tools or [],
        skills=[],
        guidelines=[],
    )


def _resources(**kwargs):
    defaults = dict(tool_names=[], skill_names=[], guideline_names=[], reasoning="")
    defaults.update(kwargs)
    return ResourceSelection(**defaults)


def _step_result(index=0, text="step 1", output="done"):
    return StepResult(step_index=index, step_text=text, output=output, resources_used=_resources())


def test_execute_task_returns_run_result():
    with patch("moon.executor.load_catalog", return_value=_catalog()), \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="rb1", via_llm=False)), \
         patch("moon.executor.execute_step", return_value=_step_result()):
        result = execute_task(Task(description="test task"))

    assert isinstance(result, RunResult)
    assert result.runbook_id == "rb1"
    assert result.final_output == "done"


def test_execute_task_final_output_from_last_step():
    with patch("moon.executor.load_catalog", return_value=_catalog(steps=["step 1", "step 2"])), \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="rb1", via_llm=False)), \
         patch("moon.executor.execute_step", side_effect=[
             _step_result(0, "step 1", "first output"),
             _step_result(1, "step 2", "final output"),
         ]):
        result = execute_task(Task(description="test"))

    assert result.final_output == "final output"
    assert len(result.step_results) == 2


def test_execute_task_fires_all_event_types():
    events = []

    with patch("moon.executor.load_catalog", return_value=_catalog()), \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="rb1", via_llm=False)), \
         patch("moon.executor.execute_step", return_value=_step_result()):
        execute_task(Task(description="test"), on_event=lambda t, d: events.append(t))

    assert events == ["task_started", "runbook_selected", "step_started", "step_completed", "task_completed"]


def test_execute_task_no_on_event_does_not_crash():
    with patch("moon.executor.load_catalog", return_value=_catalog()), \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="rb1", via_llm=False)), \
         patch("moon.executor.execute_step", return_value=_step_result()):
        result = execute_task(Task(description="test"), on_event=None)

    assert result.runbook_id == "rb1"


def test_execute_task_unknown_runbook_raises():
    with patch("moon.executor.load_catalog", return_value=_catalog(runbook_id="real_rb")), \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="nonexistent", via_llm=False)):
        with pytest.raises(ValueError, match="Unknown runbook: nonexistent"):
            execute_task(Task(description="test"))


def test_execute_task_pre_declared_resources_skip_select_resources():
    catalog = Catalog(
        runbooks=[Runbook(
            id="rb1", description="d", tags=[],
            steps=[{"text": "step 1", "tools": ["tool_a"]}],
        )],
        tools=[Tool(name="tool_a", description="d", parameters={}, mock_response="m")],
        skills=[],
        guidelines=[],
    )
    with patch("moon.executor.load_catalog", return_value=catalog), \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="rb1", via_llm=False)), \
         patch("moon.executor.select_resources") as mock_select, \
         patch("moon.executor.execute_step", return_value=_step_result()):
        execute_task(Task(description="test"))

    mock_select.assert_not_called()


def test_execute_task_no_predeclared_calls_select_resources():
    resources = _resources()
    with patch("moon.executor.load_catalog", return_value=_catalog()), \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="rb1", via_llm=False)), \
         patch("moon.executor.select_resources", return_value=resources) as mock_select, \
         patch("moon.executor.execute_step", return_value=_step_result()):
        execute_task(Task(description="test"))

    mock_select.assert_called_once()


def test_execute_task_prior_context_grows_across_steps():
    captured_prior = []

    def fake_execute_step(**kwargs):
        captured_prior.append(len(kwargs["prior_context"]))
        idx = kwargs["step_index"]
        return _step_result(idx, f"step {idx + 1}", f"output {idx}")

    with patch("moon.executor.load_catalog", return_value=_catalog(steps=["step 1", "step 2", "step 3"])), \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="rb1", via_llm=False)), \
         patch("moon.executor.execute_step", side_effect=fake_execute_step):
        execute_task(Task(description="test"))

    assert captured_prior == [0, 1, 2]


def test_execute_task_passes_custom_catalogs_path(tmp_path):
    with patch("moon.executor.load_catalog", return_value=_catalog()) as mock_load, \
         patch("moon.executor.select_runbook", return_value=RunbookSelection(runbook_id="rb1", via_llm=False)), \
         patch("moon.executor.execute_step", return_value=_step_result()):
        execute_task(Task(description="test"), catalogs_path=tmp_path)

    mock_load.assert_called_once_with(tmp_path)
