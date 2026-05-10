import pytest
from moon.models import (
    Catalog, Guideline, ResourceSelection, RunResult, Runbook,
    RunbookSelection, Skill, StepResult, Task, Tool, ToolCall,
)


def test_task_defaults():
    t = Task(description="test task")
    assert t.description == "test task"
    assert t.input_data == {}


def test_task_with_input():
    t = Task(description="test", input_data={"key": "value"})
    assert t.input_data == {"key": "value"}


def test_runbook():
    r = Runbook(id="rb1", description="A runbook", tags=["a", "b"], steps=["step 1", "step 2"])
    assert r.id == "rb1"
    assert len(r.steps) == 2
    assert "a" in r.tags


def test_tool():
    t = Tool(
        name="my_tool",
        description="Does stuff",
        parameters={"type": "object", "properties": {}, "required": []},
        mock_response="mock output",
    )
    assert t.name == "my_tool"
    assert t.mock_response == "mock output"


def test_skill():
    s = Skill(name="analyst", content="You are an analyst.")
    assert s.name == "analyst"
    assert s.content == "You are an analyst."


def test_guideline():
    g = Guideline(name="policy", content="Follow this policy.")
    assert g.name == "policy"


def test_resource_selection():
    rs = ResourceSelection(
        tool_names=["tool_a"],
        skill_names=["skill_b"],
        guideline_names=[],
        reasoning="Because",
    )
    assert rs.tool_names == ["tool_a"]
    assert rs.guideline_names == []


def test_runbook_selection():
    rs = RunbookSelection(runbook_id="rb1", reasoning="Best match")
    assert rs.runbook_id == "rb1"


def test_tool_call():
    tc = ToolCall(tool_name="lookup", input={"id": "abc"}, output="result")
    assert tc.tool_name == "lookup"
    assert tc.output == "result"


def test_step_result_defaults():
    rs = ResourceSelection(tool_names=[], skill_names=[], guideline_names=[], reasoning="")
    sr = StepResult(step_index=0, step_text="Do something", output="Done.", resources_used=rs)
    assert sr.tool_calls == []
    assert sr.step_index == 0


def test_step_result_with_tool_calls():
    rs = ResourceSelection(tool_names=["t"], skill_names=[], guideline_names=[], reasoning="")
    tc = ToolCall(tool_name="t", input={}, output="out")
    sr = StepResult(step_index=1, step_text="step", output="result", resources_used=rs, tool_calls=[tc])
    assert len(sr.tool_calls) == 1
    assert sr.tool_calls[0].tool_name == "t"


def test_run_result():
    task = Task(description="test")
    rs = ResourceSelection(tool_names=[], skill_names=[], guideline_names=[], reasoning="")
    sr = StepResult(step_index=0, step_text="step", output="output", resources_used=rs)
    rr = RunResult(
        task=task,
        runbook_id="rb1",
        runbook_description="desc",
        step_results=[sr],
        final_output="output",
    )
    assert rr.runbook_id == "rb1"
    assert len(rr.step_results) == 1
    assert rr.final_output == "output"


def test_catalog():
    cat = Catalog(
        runbooks=[Runbook(id="r", description="d", tags=[], steps=["s"])],
        tools=[Tool(name="t", description="d", parameters={}, mock_response="m")],
        skills=[Skill(name="s", content="c")],
        guidelines=[Guideline(name="g", content="c")],
    )
    assert len(cat.runbooks) == 1
    assert len(cat.tools) == 1
