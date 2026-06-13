import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
BEDROCK_REGION: str = os.environ.get("AWS_REGION", os.environ.get("MOON_DYNAMO_REGION", "us-east-1"))

# Ordered preference lists — first live model wins at startup.
# If MOON_COORDINATOR_MODEL / MOON_AGENT_MODEL env vars are set they are tried first.
COORDINATOR_MODEL_CANDIDATES: list[str] = [m for m in [
    os.environ.get("MOON_COORDINATOR_MODEL"),
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "us.amazon.nova-lite-v1:0",
    "amazon.nova-lite-v1:0",
] if m]

AGENT_MODEL_CANDIDATES: list[str] = [m for m in [
    os.environ.get("MOON_AGENT_MODEL"),
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "us.amazon.nova-pro-v1:0",
    "amazon.nova-pro-v1:0",
] if m]

# Set to first candidate; overwritten at startup by llm.init_models()
COORDINATOR_MODEL: str = COORDINATOR_MODEL_CANDIDATES[0]
AGENT_MODEL: str = AGENT_MODEL_CANDIDATES[0]
CATALOGS_PATH: Path = Path(os.environ.get("MOON_CATALOGS_PATH", "catalogs"))
MAX_TOKENS: int = int(os.environ.get("MOON_MAX_TOKENS", "4096"))
LLM_TIMEOUT: float = float(os.environ.get("MOON_LLM_TIMEOUT", "90"))
MAX_WORKERS: int = int(os.environ.get("MOON_MAX_WORKERS", "5"))
MOCK_TOOLS: bool = os.environ.get("MOON_MOCK_TOOLS", "true").lower() == "true"
DYNAMO_TABLE: str = os.environ.get("MOON_DYNAMO_TABLE", "")
DYNAMO_REGION: str = os.environ.get("AWS_REGION", "us-east-1")
DYNAMO_ENDPOINT_URL: str = os.environ.get("MOON_DYNAMO_ENDPOINT_URL", "")
INTEL_SCHEDULE_HOUR: int = int(os.environ.get("MOON_INTEL_SCHEDULE_HOUR", "6"))

# Populated by llm.init_models() — only models that passed probe_model() are in here.
# resolve_model() checks this before returning a registry entry, so a model that fails
# on-demand throughput (like newer Haiku/Sonnet without an inference profile) never gets
# used for actual inference even if the coordinator selects it by friendly name.
LIVE_MODELS: set[str] = set()

# Model registry: friendly name → Bedrock model ID + coordinator guidance
MODEL_REGISTRY: dict[str, dict] = {
    "nova-micro": {
        "bedrock_id": "us.amazon.nova-micro-v1:0",
        "use_for": "cheapest, simple classification, boolean decisions, routing",
    },
    "nova-lite": {
        "bedrock_id": "us.amazon.nova-lite-v1:0",
        "use_for": "fast and cheap, data fetching, summarization, simple extraction",
    },
    "nova-pro": {
        "bedrock_id": "us.amazon.nova-pro-v1:0",
        "use_for": "balanced Nova, multi-step reasoning, tool-heavy tasks, analysis",
    },
    "claude-haiku": {
        "bedrock_id": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "use_for": "best-in-class cheap/fast, structured extraction, security triage",
    },
    "claude-sonnet": {
        "bedrock_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "use_for": "strong reasoning and tool use, correlation, most agent work",
    },
    "claude-opus": {
        "bedrock_id": "us.anthropic.claude-3-opus-20240229-v1:0",
        "use_for": "hardest synthesis tasks, executive reports, nuanced multi-source reasoning",
    },
}


def resolve_model(name: str) -> str:
    """Resolve a friendly model name to its Bedrock model ID. Falls back to AGENT_MODEL."""
    entry = MODEL_REGISTRY.get(name)
    if entry:
        bedrock_id = entry["bedrock_id"]
        # If probing has run, only return this model if it's known-live.
        # This prevents a non-live registry entry from being used in actual inference
        # even if the coordinator selected it by friendly name.
        if not LIVE_MODELS or bedrock_id in LIVE_MODELS:
            return bedrock_id
    return AGENT_MODEL
