import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
COORDINATOR_MODEL: str = os.environ.get("MOON_COORDINATOR_MODEL", "claude-haiku-4-5-20251001")
AGENT_MODEL: str = os.environ.get("MOON_AGENT_MODEL", "claude-sonnet-4-6")
CATALOGS_PATH: Path = Path(os.environ.get("MOON_CATALOGS_PATH", "catalogs"))
MAX_TOKENS: int = int(os.environ.get("MOON_MAX_TOKENS", "4096"))
LLM_TIMEOUT: float = float(os.environ.get("MOON_LLM_TIMEOUT", "90"))
MAX_WORKERS: int = int(os.environ.get("MOON_MAX_WORKERS", "5"))
MOCK_TOOLS: bool = os.environ.get("MOON_MOCK_TOOLS", "true").lower() == "true"
DYNAMO_TABLE: str = os.environ.get("MOON_DYNAMO_TABLE", "")
DYNAMO_REGION: str = os.environ.get("AWS_REGION", "us-east-1")
DYNAMO_ENDPOINT_URL: str = os.environ.get("MOON_DYNAMO_ENDPOINT_URL", "")
