"""Thin wrapper around the Bedrock Converse API.

Provides a single converse() function that works with any Bedrock model
(Claude, Amazon Nova, Llama, etc.) using a unified interface.
"""
import logging
from dataclasses import dataclass, field

import boto3
from botocore.exceptions import ClientError

from moon import config

log = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=config.BEDROCK_REGION)
    return _client


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict


@dataclass
class ConverseResult:
    stop_reason: str     # "end_turn" | "tool_use" | "max_tokens"
    text: str
    tool_uses: list[ToolUse] = field(default_factory=list)
    raw_content: list[dict] = field(default_factory=list)  # for appending to message history


def probe_model(model_id: str) -> bool:
    """Return True if model_id responds on Bedrock, False if EOL or unavailable."""
    try:
        _get_client().converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "hi"}]}],
            inferenceConfig={"maxTokens": 1},
        )
        config.LIVE_MODELS.add(model_id)
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDeniedException":
            raise  # IAM misconfiguration — don't swallow
        log.debug("probe_model %s: %s", model_id, code)
        return False


def resolve_live_model(candidates: list[str]) -> str:
    """Return the first candidate model that is live on Bedrock."""
    for model_id in candidates:
        if probe_model(model_id):
            log.info("live model selected: %s", model_id)
            return model_id
    raise RuntimeError(f"No live Bedrock models found in candidates: {candidates}")


def init_models() -> None:
    """Probe candidates and set config.COORDINATOR_MODEL / config.AGENT_MODEL to live models."""
    config.COORDINATOR_MODEL = resolve_live_model(config.COORDINATOR_MODEL_CANDIDATES)
    config.AGENT_MODEL = resolve_live_model(config.AGENT_MODEL_CANDIDATES)
    log.info("models ready — coordinator=%s agent=%s", config.COORDINATOR_MODEL, config.AGENT_MODEL)


def make_tool(name: str, description: str, input_schema: dict) -> dict:
    return {
        "toolSpec": {
            "name": name,
            "description": description,
            "inputSchema": {"json": input_schema},
        }
    }


def converse(
    model_id: str,
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    force_tool: str | None = None,
    max_tokens: int | None = None,
) -> ConverseResult:
    kwargs: dict = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens or config.MAX_TOKENS},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    if tools:
        tool_config: dict = {"tools": tools}
        if force_tool:
            tool_config["toolChoice"] = {"tool": {"name": force_tool}}
        kwargs["toolConfig"] = tool_config

    log.debug("converse: model=%s messages=%d", model_id, len(messages))
    response = _get_client().converse(**kwargs)

    stop_reason = response["stopReason"]
    raw_content = response["output"]["message"]["content"]

    text = ""
    tool_uses: list[ToolUse] = []
    for block in raw_content:
        if "text" in block:
            text = block["text"]
        elif "toolUse" in block:
            tu = block["toolUse"]
            tool_uses.append(ToolUse(id=tu["toolUseId"], name=tu["name"], input=tu["input"]))

    return ConverseResult(
        stop_reason=stop_reason,
        text=text,
        tool_uses=tool_uses,
        raw_content=raw_content,
    )
