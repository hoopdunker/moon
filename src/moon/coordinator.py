import logging
import anthropic
from moon import config
from moon.models import Guideline, ResourceSelection, Runbook, RunbookSelection, Skill, Tool

log = logging.getLogger(__name__)


_client: anthropic.AnthropicBedrock | None = None


def _get_client() -> anthropic.AnthropicBedrock:
    global _client
    if _client is None:
        _client = anthropic.AnthropicBedrock(aws_region=config.BEDROCK_REGION)
    return _client


def _tag_match(task_description: str, runbooks: list[Runbook]) -> RunbookSelection | None:
    """Score runbooks by tag/id keyword overlap. Returns a match only when one runbook
    clearly wins (score >= 2 and at least 2x the second-best score)."""
    words = set(task_description.lower().replace("_", " ").split())

    scores: list[tuple[int, Runbook]] = []
    for r in runbooks:
        keywords = set(r.tags) | set(r.id.replace("_", " ").split())
        score = sum(1 for kw in keywords if kw in words)
        scores.append((score, r))

    scores.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else 0

    if best_score >= 2 and best_score >= second_score * 2:
        return RunbookSelection(runbook_id=best.id, via_llm=False)
    return None


def select_runbook(task_description: str, runbooks: list[Runbook]) -> RunbookSelection:
    if len(runbooks) == 1:
        log.debug("runbook selected (only one): %s", runbooks[0].id)
        return RunbookSelection(runbook_id=runbooks[0].id, via_llm=False)

    match = _tag_match(task_description, runbooks)
    if match:
        log.debug("runbook selected (tag match): %s", match.runbook_id)
        return match

    runbook_index = "\n".join(
        f"- id: {r.id}\n  description: {r.description}\n  tags: {', '.join(r.tags)}"
        for r in runbooks
    )

    response = _get_client().messages.create(
        model=config.COORDINATOR_MODEL,
        max_tokens=512,
        tools=[{
            "name": "select_runbook",
            "description": "Select the most appropriate runbook for the given task",
            "input_schema": {
                "type": "object",
                "properties": {
                    "runbook_id": {"type": "string", "description": "ID of the selected runbook"},
                    "reasoning": {"type": "string", "description": "Why this runbook was selected"},
                },
                "required": ["runbook_id", "reasoning"],
            },
        }],
        tool_choice={"type": "tool", "name": "select_runbook"},
        messages=[{
            "role": "user",
            "content": f"Task: {task_description}\n\nAvailable runbooks:\n{runbook_index}\n\nSelect the most appropriate runbook.",
        }],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "select_runbook":
            selection = RunbookSelection(**block.input, via_llm=True)
            log.debug("runbook selected (LLM): %s — %s", selection.runbook_id, selection.reasoning)
            return selection

    raise RuntimeError("Coordinator failed to select a runbook")


_MODEL_MENU = "\n".join(
    f"- {name}: {info['use_for']}"
    for name, info in config.MODEL_REGISTRY.items()
)


def select_resources(
    step_text: str,
    step_index: int,
    task_description: str,
    tools: list[Tool],
    skills: list[Skill],
    guidelines: list[Guideline],
) -> ResourceSelection:
    resource_index = (
        "TOOLS:\n" + "\n".join(f"- {t.name}: {t.description}" for t in tools)
        + "\n\nSKILLS:\n" + "\n".join(f"- {s.name}" for s in skills)
        + "\n\nGUIDELINES:\n" + "\n".join(f"- {g.name}" for g in guidelines)
    )

    response = _get_client().messages.create(
        model=config.COORDINATOR_MODEL,
        max_tokens=512,
        tools=[{
            "name": "select_resources",
            "description": "Select the tools, skills, guidelines, and model needed for this step",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of tools to use (can be empty)",
                    },
                    "skill_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of skills/personas to apply",
                    },
                    "guideline_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of guidelines to follow",
                    },
                    "agent_model": {
                        "type": "string",
                        "enum": list(config.MODEL_REGISTRY.keys()),
                        "description": f"Model tier for the agent executing this step:\n{_MODEL_MENU}",
                    },
                    "reasoning": {"type": "string", "description": "Why these resources and model were selected"},
                },
                "required": ["tool_names", "skill_names", "guideline_names", "agent_model", "reasoning"],
            },
        }],
        tool_choice={"type": "tool", "name": "select_resources"},
        messages=[{
            "role": "user",
            "content": (
                f"Task: {task_description}\n"
                f"Step {step_index + 1}: {step_text}\n\n"
                f"Available resources:\n{resource_index}\n\n"
                "Select the resources and model tier needed for this step."
            ),
        }],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "select_resources":
            return ResourceSelection(**block.input)

    raise RuntimeError(f"Coordinator failed to select resources for step {step_index}")
