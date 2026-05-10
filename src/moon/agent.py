import json
import logging
import anthropic
from moon import config, tool_registry
from moon.models import Guideline, ResourceSelection, Skill, StepResult, Tool, ToolCall

log = logging.getLogger(__name__)


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=config.LLM_TIMEOUT)
    return _client


def _build_system_prompt(skills: list[Skill], guidelines: list[Guideline], tools: list[Tool]) -> str:
    parts = []
    if skills:
        parts.append("# Persona\n" + "\n\n---\n\n".join(s.content for s in skills))
    if guidelines:
        parts.append("# Guidelines\n" + "\n\n---\n\n".join(g.content for g in guidelines))
    if tools:
        parts.append("# Available Tools\n" + "\n".join(f"- **{t.name}**: {t.description}" for t in tools))
    return "\n\n".join(parts)


def execute_step(
    step_index: int,
    step_text: str,
    tools: list[Tool],
    skills: list[Skill],
    guidelines: list[Guideline],
    resources: ResourceSelection,
    prior_context: list[StepResult],
    task_description: str = "",
    tool_cache: dict[str, str] | None = None,
) -> StepResult:
    system_prompt = _build_system_prompt(skills, guidelines, tools)

    context_block = ""
    if prior_context:
        entries = []
        for r in prior_context:
            parts = [f"Step {r.step_index + 1} ({r.step_text}):"]
            for tc in r.tool_calls:
                parts.append(f"[Tool result: {tc.tool_name}]\n{tc.output}")
            parts.append(r.output)
            entries.append("\n".join(parts))
        context_block = "## Prior Step Outputs\n\n" + "\n\n".join(entries) + "\n\n"

    task_block = f"## Task\n\n{task_description}\n\n" if task_description else ""
    messages: list[dict] = [{"role": "user", "content": f"{task_block}{context_block}## Current Step\n\n{step_text}"}]
    tool_defs = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]
    tools_by_name = {t.name: t for t in tools}
    tool_calls_made: list[ToolCall] = []

    create_kwargs: dict = dict(
        model=config.AGENT_MODEL,
        max_tokens=config.MAX_TOKENS,
        system=system_prompt,
        messages=messages,
    )
    if tool_defs:
        create_kwargs["tools"] = tool_defs

    output = ""
    while True:
        response = _get_client().messages.create(**create_kwargs)

        if response.stop_reason == "end_turn":
            output = next((b.text for b in response.content if b.type == "text"), "")
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    cache_key = f"{block.name}:{json.dumps(dict(block.input), sort_keys=True)}"
                    if tool_cache is not None and cache_key in tool_cache:
                        result = tool_cache[cache_key]
                        log.debug("tool cache hit: %s %s", block.name, dict(block.input))
                    else:
                        log.info("tool call: %s %s", block.name, dict(block.input))
                        handler = tool_registry.get_handler(block.name)
                        if handler:
                            try:
                                result = handler(**block.input)
                            except Exception as e:
                                result = f"Tool error: {e}"
                                log.warning("tool error: %s — %s", block.name, e)
                        elif config.MOCK_TOOLS:
                            result = tools_by_name[block.name].mock_response
                            log.debug("tool mock: %s", block.name)
                        else:
                            result = f"Error: tool '{block.name}' is not implemented"
                            log.warning("unimplemented tool called: %s", block.name)
                        if tool_cache is not None:
                            tool_cache[cache_key] = result
                        log.debug("tool result: %s", result[:200])
                    tool_calls_made.append(ToolCall(
                        tool_name=block.name,
                        input=dict(block.input),
                        output=result,
                    ))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
            create_kwargs["messages"] = messages
            continue

        output = next((b.text for b in response.content if b.type == "text"), "")
        break

    return StepResult(
        step_index=step_index,
        step_text=step_text,
        output=output,
        resources_used=resources,
        tool_calls=tool_calls_made,
    )
