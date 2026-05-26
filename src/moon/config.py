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

# Model registry: friendly name → Bedrock model ID + metadata for coordinator reasoning
MODEL_REGISTRY: dict[str, dict] = {
    "haiku": {
        "bedrock_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "use_for": "data fetching, summarization, simple extraction, fast tasks",
    },
    "sonnet": {
        "bedrock_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "use_for": "analysis, correlation, tool-heavy tasks, most agent work",
    },
    "opus": {
        "bedrock_id": "anthropic.claude-3-opus-20240229-v1:0",
        "use_for": "complex multi-source synthesis, executive reports, nuanced reasoning",
    },
}

def resolve_model(name: str) -> str:
    """Resolve a friendly model name to its Bedrock model ID. Falls back to AGENT_MODEL."""
    entry = MODEL_REGISTRY.get(name)
    return entry["bedrock_id"] if entry else AGENT_MODEL
