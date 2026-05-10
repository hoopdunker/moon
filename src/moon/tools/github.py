import httpx
from moon import config

MAX_DIFF_CHARS = 8_000


def get_pr_diff(pr_number: int, repo: str) -> str:
    if not config.GITHUB_TOKEN:
        return "Error: GITHUB_TOKEN not set"

    base_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    json_headers = {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    diff_headers = {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff",
    }

    try:
        with httpx.Client(timeout=30) as client:
            pr = client.get(base_url, headers=json_headers)
            pr.raise_for_status()
            pr_data = pr.json()

            files = client.get(f"{base_url}/files", headers=json_headers)
            files.raise_for_status()
            files_data = files.json()

            diff = client.get(base_url, headers=diff_headers)
            diff.raise_for_status()
            diff_text = diff.text

    except httpx.HTTPStatusError as e:
        return f"GitHub API error {e.response.status_code}: {e.response.text[:500]}"
    except httpx.RequestError as e:
        return f"Network error contacting GitHub: {e}"

    file_list = "\n".join(
        f"  {f['filename']} (+{f['additions']} -{f['deletions']})" for f in files_data
    )

    truncation_note = ""
    if len(diff_text) > MAX_DIFF_CHARS:
        diff_text = diff_text[:MAX_DIFF_CHARS]
        truncation_note = f"\n[Diff truncated at {MAX_DIFF_CHARS} chars]"

    return (
        f"PR #{pr_number}: {pr_data['title']}\n"
        f"Author: {pr_data['user']['login']}\n"
        f"Branch: {pr_data['head']['ref']} → {pr_data['base']['ref']}\n"
        f"State: {pr_data['state']}\n"
        f"Files changed ({len(files_data)}):\n{file_list}\n\n"
        f"Diff:\n{diff_text}{truncation_note}"
    )
