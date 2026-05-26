import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
BEDROCK_REGION: str = os.environ.get("AWS_REGION", os.environ.get("MOON_DYNAMO_REGION", "us-east-1"))
COORDINATOR_MODEL: str = os.environ.get("MOON_COORDINATOR_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
AGENT_MODEL: str = os.environ.get("MOON_AGENT_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")
CATALOGS_PATH: Path = Path(os.environ.get("MOON_CATALOGS_PATH", "catalogs"))
MAX_TOKENS: int = int(os.environ.get("MOON_MAX_TOKENS", "4096"))
LLM_TIMEOUT: float = float(os.environ.get("MOON_LLM_TIMEOUT", "90"))
MAX_WORKERS: int = int(os.environ.get("MOON_MAX_WORKERS", "5"))
MOCK_TOOLS: bool = os.environ.get("MOON_MOCK_TOOLS", "true").lower() == "true"
DYNAMO_TABLE: str = os.environ.get("MOON_DYNAMO_TABLE", "")
DYNAMO_REGION: str = os.environ.get("AWS_REGION", "us-east-1")
DYNAMO_ENDPOINT_URL: str = os.environ.get("MOON_DYNAMO_ENDPOINT_URL", "")

# Model registry: friendly name → Bedrock model ID + coordinator guidance
MODEL_REGISTRY: dict[str, dict] = {
    "nova-micro": {
        "bedrock_id": "amazon.nova-micro-v1:0",
        "use_for": "cheapest, simple classification, boolean decisions, routing",
    },
    "nova-lite": {
        "bedrock_id": "amazon.nova-lite-v1:0",
        "use_for": "fast and cheap, data fetching, summarization, simple extraction",
    },
    "nova-pro": {
        "bedrock_id": "amazon.nova-pro-v1:0",
        "use_for": "balanced Nova, multi-step reasoning, tool-heavy tasks, analysis",
    },
    "claude-haiku": {
        "bedrock_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "use_for": "best-in-class cheap/fast, structured extraction, security triage",
    },
    "claude-sonnet": {
        "bedrock_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "use_for": "strong reasoning and tool use, correlation, most agent work",
    },
    "claude-opus": {
        "bedrock_id": "anthropic.claude-3-opus-20240229-v1:0",
        "use_for": "hardest synthesis tasks, executive reports, nuanced multi-source reasoning",
    },
}


def resolve_model(name: str) -> str:
    """Resolve a friendly model name to its Bedrock model ID. Falls back to AGENT_MODEL."""
    entry = MODEL_REGISTRY.get(name)
    return entry["bedrock_id"] if entry else AGENT_MODEL
