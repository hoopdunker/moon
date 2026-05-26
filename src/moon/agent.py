import json
import logging
from moon import config, llm, tool_registry
from moon.models import Guideline, ResourceSelection, Skill, StepResult, Tool, ToolCall

log = logging.getLogger(__name__)


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
    user_text = f"{task_block}{context_block}## Current Step\n\n{step_text}"

    messages: list[dict] = [{"role": "user", "content": [{"text": user_text}]}]
    tool_defs = [
        llm.make_tool(name=t.name, description=t.description, input_schema=t.parameters)
        for t in tools
    ]
    tools_by_name = {t.name: t for t in tools}
    tool_calls_made: list[ToolCall] = []

    model_id = config.resolve_model(resources.agent_model)

    output = ""
    while True:
        result = llm.converse(
            model_id=model_id,
            messages=messages,
            system=system_prompt,
            tools=tool_defs or None,
        )

        if result.stop_reason == "end_turn":
            output = result.text
            break

        if result.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": result.raw_content})
            tool_results = []
            for tu in result.tool_uses:
                cache_key = f"{tu.name}:{json.dumps(tu.input, sort_keys=True)}"
                if tool_cache is not None and cache_key in tool_cache:
                    tool_result = tool_cache[cache_key]
                    log.debug("tool cache hit: %s %s", tu.name, tu.input)
                else:
                    log.info("tool call: %s %s", tu.name, tu.input)
                    handler = tool_registry.get_handler(tu.name)
                    if handler:
                        try:
                            tool_result = handler(**tu.input)
                        except Exception as e:
                            tool_result = f"Tool error: {e}"
                            log.warning("tool error: %s — %s", tu.name, e)
                    elif config.MOCK_TOOLS:
                        tool_result = tools_by_name[tu.name].mock_response
                        log.debug("tool mock: %s", tu.name)
                    else:
                        tool_result = f"Error: tool '{tu.name}' is not implemented"
                        log.warning("unimplemented tool called: %s", tu.name)
                    if tool_cache is not None:
                        tool_cache[cache_key] = tool_result
                    log.debug("tool result: %s", tool_result[:200])
                tool_calls_made.append(ToolCall(
                    tool_name=tu.name,
                    input=tu.input,
                    output=tool_result,
                ))
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tu.id,
                        "content": [{"text": tool_result}],
                    }
                })
            messages.append({"role": "user", "content": tool_results})
            continue

        output = result.text
        break

    return StepResult(
        step_index=step_index,
        step_text=step_text,
        output=output,
        resources_used=resources,
        tool_calls=tool_calls_made,
    )
