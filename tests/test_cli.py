import json
import pytest
from unittest.mock import patch
from typer.testing import CliRunner
from moon.cli import app
from moon.models import ResourceSelection, RunResult, Skill, StepResult, Task


runner = CliRunner()


def _make_run_result(final_output="final output"):
    task = Task(description="test task")
    rs = ResourceSelection(tool_names=[], skill_names=[], guideline_names=[], reasoning="")
    sr = StepResult(step_index=0, step_text="step", output=final_output, resources_used=rs)
    return RunResult(
        task=task,
        runbook_id="test_rb",
        runbook_description="Test runbook description",
        step_results=[sr],
        final_output=final_output,
    )


def test_run_command_success():
    with patch("moon.cli.run_task", return_value=_make_run_result()):
        result = runner.invoke(app, ["run", "test task"])

    assert result.exit_code == 0
    assert "test_rb" in result.output
    assert "final output" in result.output


def test_run_command_passes_task_description():
    with patch("moon.cli.run_task", return_value=_make_run_result()) as mock_run:
        runner.invoke(app, ["run", "my specific task"])

    called_task = mock_run.call_args[0][0]
    assert called_task.description == "my specific task"


def test_run_command_verbose_shows_step_detail():
    with patch("moon.cli.run_task", return_value=_make_run_result()):
        result = runner.invoke(app, ["run", "test task", "--verbose"])

    assert result.exit_code == 0
    assert "step" in result.output


def test_run_command_with_input_file(tmp_path):
    input_data = {"alert_id": "CS-001"}
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(input_data))

    with patch("moon.cli.run_task", return_value=_make_run_result()) as mock_run:
        result = runner.invoke(app, ["run", "test task", "--input", str(input_file)])

    assert result.exit_code == 0
    called_task = mock_run.call_args[0][0]
    assert called_task.input_data == input_data


def test_run_command_saves_output_file(tmp_path):
    output_file = tmp_path / "result.json"

    with patch("moon.cli.run_task", return_value=_make_run_result()):
        result = runner.invoke(app, ["run", "test task", "--output", str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()
    data = json.loads(output_file.read_text())
    assert data["runbook_id"] == "test_rb"
    assert data["final_output"] == "final output"


def test_run_command_output_file_contains_step_results(tmp_path):
    output_file = tmp_path / "result.json"

    with patch("moon.cli.run_task", return_value=_make_run_result()):
        runner.invoke(app, ["run", "test task", "--output", str(output_file)])

    data = json.loads(output_file.read_text())
    assert len(data["step_results"]) == 1
    assert data["step_results"][0]["step_index"] == 0


def test_run_command_no_output_file_by_default(tmp_path):
    with patch("moon.cli.run_task", return_value=_make_run_result()):
        runner.invoke(app, ["run", "test task"])

    assert not any(tmp_path.iterdir())


def test_run_command_passes_catalogs_path(tmp_path):
    with patch("moon.cli.run_task", return_value=_make_run_result()) as mock_run:
        runner.invoke(app, ["run", "test task", "--catalogs", str(tmp_path)])

    called_path = mock_run.call_args[0][1]
    assert called_path == tmp_path
