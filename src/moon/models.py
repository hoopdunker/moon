from __future__ import annotations
from typing import Any
from pydantic import BaseModel, field_validator


class Task(BaseModel):
    description: str
    input_data: dict[str, Any] = {}


class RunbookStep(BaseModel):
    text: str
    tools: list[str] = []
    skills: list[str] = []
    guidelines: list[str] = []

    @property
    def has_resources(self) -> bool:
        return bool(self.tools or self.skills or self.guidelines)


class Runbook(BaseModel):
    id: str
    description: str
    tags: list[str]
    skills: list[str] = []
    guidelines: list[str] = []
    steps: list[RunbookStep]

    @field_validator("steps", mode="before")
    @classmethod
    def coerce_steps(cls, v: list) -> list:
        return [{"text": s} if isinstance(s, str) else s for s in v]


class Tool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    mock_response: str


class Skill(BaseModel):
    name: str
    content: str


class Guideline(BaseModel):
    name: str
    content: str


class Catalog(BaseModel):
    runbooks: list[Runbook]
    tools: list[Tool]
    skills: list[Skill]
    guidelines: list[Guideline]


class RunbookSelection(BaseModel):
    runbook_id: str
    reasoning: str = ""
    via_llm: bool = False


class ResourceSelection(BaseModel):
    tool_names: list[str]
    skill_names: list[str]
    guideline_names: list[str]
    reasoning: str = ""


class ToolCall(BaseModel):
    tool_name: str
    input: dict[str, Any]
    output: str


class StepResult(BaseModel):
    step_index: int
    step_text: str
    output: str
    resources_used: ResourceSelection
    tool_calls: list[ToolCall] = []


class RunResult(BaseModel):
    task: Task
    runbook_id: str
    runbook_description: str
    step_results: list[StepResult]
    final_output: str
