from typing import Callable
from moon.tools.github import get_pr_diff

# Maps tool name → callable(**tool_input) -> str
_REGISTRY: dict[str, Callable[..., str]] = {
    "get_pr_diff": get_pr_diff,
}


def get_handler(tool_name: str) -> Callable[..., str] | None:
    return _REGISTRY.get(tool_name)
