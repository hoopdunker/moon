import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from moon import config
from moon.agent import execute_step
from moon.catalog import load_catalog
from moon.coordinator import select_resources, select_runbook
from moon.models import ResourceSelection, RunResult, Task

log = logging.getLogger(__name__)

OnEvent = Callable[[str, dict[str, Any]], None]


def execute_task(
    task: Task,
    catalogs_path: Path | None = None,
    on_event: OnEvent | None = None,
) -> RunResult:
    def emit(event_type: str, **data: Any) -> None:
        if on_event:
            on_event(event_type, data)

    catalog = load_catalog(catalogs_path)
    t_task = time.monotonic()
    emit("task_started", description=task.description)
    log.info("[%s] task started", task.description[:60])

    t0 = time.monotonic()
    selection = select_runbook(task.description, catalog.runbooks)
    runbook_select_ms = int((time.monotonic() - t0) * 1000)

    runbook = next((r for r in catalog.runbooks if r.id == selection.runbook_id), None)
    if not runbook:
        log.error("[%s] runbook not found: %s", task.description[:40], selection.runbook_id)
        raise ValueError(f"Unknown runbook: {selection.runbook_id}")

    source = f"LLM ({runbook_select_ms}ms)" if selection.via_llm else "tag match"
    emit("runbook_selected", runbook_id=runbook.id, source=source, total_steps=len(runbook.steps),
         step_texts=[s.text for s in runbook.steps])
    log.info("[%s] runbook selected: %s (%s)", task.description[:40], runbook.id, source)

    step_results = []
    tool_cache: dict[str, str] = {}

    for i, step in enumerate(runbook.steps):
        step_text = step.text
        emit("step_started", step_index=i, step_text=step_text)
        log.info("[%s] step %d/%d started: %s", task.description[:40], i + 1, len(runbook.steps), step_text)

        t0 = time.monotonic()
        resolved_skills = step.skills or runbook.skills
        resolved_guidelines = step.guidelines or runbook.guidelines
        if step.tools or resolved_skills or resolved_guidelines:
            resources = ResourceSelection(
                tool_names=step.tools,
                skill_names=resolved_skills,
                guideline_names=resolved_guidelines,
            )
        else:
            resources = select_resources(
                step_text=step_text,
                step_index=i,
                task_description=task.description,
                tools=catalog.tools,
                skills=catalog.skills,
                guidelines=catalog.guidelines,
            )

        log.debug(
            "[%s] step %d resources: tools=%s skills=%s guidelines=%s",
            task.description[:40], i + 1, resources.tool_names, resources.skill_names, resources.guideline_names,
        )

        result = execute_step(
            step_index=i,
            step_text=step_text,
            tools=[t for t in catalog.tools if t.name in resources.tool_names],
            skills=[s for s in catalog.skills if s.name in resources.skill_names],
            guidelines=[g for g in catalog.guidelines if g.name in resources.guideline_names],
            resources=resources,
            prior_context=step_results,
            task_description=task.description,
            tool_cache=tool_cache,
        )
        step_ms = int((time.monotonic() - t0) * 1000)
        emit("step_completed",
             step_index=i,
             step_text=step_text,
             duration_ms=step_ms,
             tools_used=resources.tool_names,
             output=result.output)
        log.info("[%s] step %d/%d completed in %dms", task.description[:40], i + 1, len(runbook.steps), step_ms)
        step_results.append(result)

    run_result = RunResult(
        task=task,
        runbook_id=runbook.id,
        runbook_description=runbook.description,
        step_results=step_results,
        final_output=step_results[-1].output if step_results else "",
    )
    total_ms = int((time.monotonic() - t_task) * 1000)
    emit("task_completed", runbook_id=runbook.id, final_output=run_result.final_output, duration_ms=total_ms)
    log.info("[%s] task completed in %dms", task.description[:40], total_ms)
    return run_result
