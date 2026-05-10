import pytest
from unittest.mock import MagicMock, patch
from moon.tools.github import MAX_DIFF_CHARS, get_pr_diff


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


def _mock_error_response(status_code, body="error"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body
    error = MagicMock()
    error.response = resp
    return error


PR_DATA = {
    "title": "Add feature X",
    "user": {"login": "dev-alice"},
    "head": {"ref": "feature/x"},
    "base": {"ref": "main"},
    "state": "open",
}

FILES_DATA = [
    {"filename": "src/foo.py", "additions": 10, "deletions": 2},
    {"filename": "src/bar.py", "additions": 3, "deletions": 0},
]

DIFF_TEXT = "diff --git a/src/foo.py b/src/foo.py\n+new line\n-old line\n"


def _make_client(pr=PR_DATA, files=FILES_DATA, diff=DIFF_TEXT):
    client = MagicMock()
    client.get.side_effect = [
        _mock_response(json_data=pr),
        _mock_response(json_data=files),
        _mock_response(text=diff),
    ]
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    return client


def test_get_pr_diff_returns_title():
    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=_make_client()):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=42, repo="acme/backend")

    assert "PR #42: Add feature X" in result


def test_get_pr_diff_returns_author():
    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=_make_client()):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=42, repo="acme/backend")

    assert "dev-alice" in result


def test_get_pr_diff_returns_branch_info():
    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=_make_client()):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=42, repo="acme/backend")

    assert "feature/x" in result
    assert "main" in result


def test_get_pr_diff_lists_files():
    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=_make_client()):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=42, repo="acme/backend")

    assert "src/foo.py" in result
    assert "src/bar.py" in result


def test_get_pr_diff_includes_diff_text():
    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=_make_client()):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=42, repo="acme/backend")

    assert "+new line" in result


def test_get_pr_diff_no_token():
    with patch("moon.tools.github.config") as mock_cfg:
        mock_cfg.GITHUB_TOKEN = ""
        result = get_pr_diff(pr_number=1, repo="acme/backend")

    assert "GITHUB_TOKEN not set" in result


def test_get_pr_diff_truncates_large_diff():
    large_diff = "x" * (MAX_DIFF_CHARS + 1000)
    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=_make_client(diff=large_diff)):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=1, repo="acme/backend")

    assert "truncated" in result


def test_get_pr_diff_no_truncation_for_small_diff():
    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=_make_client(diff=DIFF_TEXT)):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=1, repo="acme/backend")

    assert "truncated" not in result


def test_get_pr_diff_http_error():
    import httpx as real_httpx

    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)

    err_resp = MagicMock()
    err_resp.status_code = 404
    err_resp.text = "Not Found"
    client.get.side_effect = real_httpx.HTTPStatusError("404", request=MagicMock(), response=err_resp)

    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=client):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=999, repo="acme/backend")

    assert "404" in result


def test_get_pr_diff_network_error():
    import httpx as real_httpx

    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    client.get.side_effect = real_httpx.RequestError("connection refused", request=MagicMock())

    with patch("moon.tools.github.config") as mock_cfg, \
         patch("moon.tools.github.httpx.Client", return_value=client):
        mock_cfg.GITHUB_TOKEN = "ghp_test"
        result = get_pr_diff(pr_number=1, repo="acme/backend")

    assert "Network error" in result
