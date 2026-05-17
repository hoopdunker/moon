from typing import Callable
from moon.tools.github import get_pr_diff
from moon.tools.threat_intel import fetch_latest_cves, fetch_security_news, fetch_threat_feeds
from moon.tools.environment import get_environment_profile

# Maps tool name → callable(**tool_input) -> str
_REGISTRY: dict[str, Callable[..., str]] = {
    "get_pr_diff": get_pr_diff,
    "fetch_security_news": fetch_security_news,
    "fetch_latest_cves": fetch_latest_cves,
    "fetch_threat_feeds": fetch_threat_feeds,
    "get_environment_profile": get_environment_profile,
}


def get_handler(tool_name: str) -> Callable[..., str] | None:
    return _REGISTRY.get(tool_name)
