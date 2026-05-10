# Moon

Multi-agent security orchestration system. Given a natural language task, Moon selects the right runbook, assembles the right tools and skills, and executes each step using Claude — producing structured security findings.

## How it works

1. **Coordinator** receives a task description and selects the appropriate runbook. It uses tag matching first (fast, no LLM call) and falls back to a Haiku LLM call when ambiguous.
2. **Agent** executes each step in the runbook using Claude Sonnet, with the tools, skills, and guidelines defined for that step. Tool results are cached and passed as context to every subsequent step so nothing is re-fetched.
3. **Output** is a structured report following the output format guideline: summary, findings with severity ratings, risk assessment, and next steps with owners.

```
Task description
      ↓
  Coordinator  →  selects runbook (tag match or LLM)
      ↓
  Agent × N steps  →  calls tools, reasons over results
      ↓
  Structured report
```

## Runbooks

| Runbook | Description | Tools |
|---|---|---|
| `pr_security_review` | Review a GitHub pull request for security vulnerabilities | `get_pr_diff` |
| `malicious_ip_investigation` | Investigate a suspicious IP across threat intel, geolocation, and passive DNS | `query_threat_intel`, `get_ip_geo`, `get_passive_dns` |
| `security_alert_triage` | Triage a security alert for lateral movement or host compromise | `get_alert_details`, `query_threat_intel` |

## Tools

| Tool | Status | Description |
|---|---|---|
| `get_pr_diff` | Live | Fetches PR metadata, file list, and diff from GitHub |
| `get_ip_geo` | Mock | Geolocation, ASN, hosting provider, Tor/VPN flags |
| `get_passive_dns` | Mock | Passive DNS history — domains, first/last seen, infrastructure overlap |
| `query_threat_intel` | Mock | IOC lookup across threat intel databases |
| `get_alert_details` | Mock | Alert enrichment with host and process context |

Mock tools return realistic canned responses. Set `MOON_MOCK_TOOLS=false` to disable mocks — unimplemented tools will return an error instead of silently returning fake data.

## Skills and Guidelines

**Skills** define the agent persona for each runbook:
- `security_analyst` — vulnerability assessment, risk rating, OWASP familiarity
- `code_reviewer` — secure code review, language-agnostic, SAST-style analysis
- `threat_intel_analyst` — IP attribution, passive DNS pivoting, threat actor profiling, VirusTotal/Shodan/AbuseIPDB

**Guidelines** are injected into every step that uses them:
- `escalation_policy` — when to page on-call vs file a ticket vs log and monitor
- `output_format` — structured report format: summary, findings, risk assessment, next steps

## Running Moon

### Prerequisites

```bash
# Install dependencies
uv pip install -e ".[aws]"

# Required
export ANTHROPIC_API_KEY=sk-ant-...

# For PR security review
export GITHUB_TOKEN=ghp_...

# For DynamoDB persistence (optional — defaults to in-memory)
export MOON_DYNAMO_TABLE=moon-cases
```

### CLI — single task

```bash
moon run "investigate IP 185.220.101.47 — repeated VPN auth failures"
moon run "review PR #42 in acme/backend for security issues"
moon run "triage alert CS-001 — lateral movement detected"
```

With a JSON input file:

```bash
moon run "investigate malicious IP" --input tasks/examples/investigate_ip.json
moon run "review PR" --input tasks/examples/pr_review.json --verbose
```

### CLI — batch

```bash
moon batch tasks/batch.json --workers 5 --output-dir results/
```

The batch file is a JSON array of task objects:

```json
[
  {"description": "investigate IP 1.2.3.4", "input_data": {"ip": "1.2.3.4"}},
  {"description": "review PR #10 in org/repo", "input_data": {}}
]
```

### Web UI

```bash
moon serve
# → http://127.0.0.1:8000
```

Submit tasks, watch step-by-step progress in real time via server-sent events, and review completed case reports. Cases persist to DynamoDB if configured, or stay in memory for the lifetime of the process.

### Docker

```bash
# Local dev with DynamoDB Local
ANTHROPIC_API_KEY=sk-ant-... docker compose up --build

# Moon UI → http://localhost:8000
# DynamoDB Local → http://localhost:8001
```

For production, set `MOON_MOCK_TOOLS=false` and provide real AWS credentials. The Docker image installs `boto3` and auto-creates the DynamoDB table on first startup if it doesn't exist.

## Configuration

All config is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required |
| `GITHUB_TOKEN` | — | Required for `get_pr_diff` |
| `MOON_COORDINATOR_MODEL` | `claude-haiku-4-5-20251001` | Model for runbook selection |
| `MOON_AGENT_MODEL` | `claude-sonnet-4-6` | Model for step execution |
| `MOON_CATALOGS_PATH` | `catalogs` | Path to runbooks/tools/skills/guidelines |
| `MOON_MOCK_TOOLS` | `true` | Return mock responses for unregistered tools |
| `MOON_DYNAMO_TABLE` | — | DynamoDB table name (in-memory if unset) |
| `MOON_DYNAMO_ENDPOINT_URL` | — | Override DynamoDB endpoint (for local dev) |
| `AWS_REGION` | `us-east-1` | AWS region for DynamoDB |
| `MOON_MAX_TOKENS` | `4096` | Max tokens per agent response |
| `MOON_LLM_TIMEOUT` | `90` | LLM request timeout in seconds |
| `MOON_MAX_WORKERS` | `5` | Max parallel tasks (batch / web server) |

## Adding a runbook

Create a YAML file in `catalogs/runbooks/`:

```yaml
id: my_runbook
description: What this runbook does — used for LLM-based routing
tags:
  - keyword1   # used for fast tag-match routing
  - keyword2
skills: [security_analyst]
guidelines: [escalation_policy, output_format]
steps:
  - text: First step — plain text, no tools needed
  - text: Second step — calls a tool
    tools: [my_tool]
  - text: Third step — synthesise findings and produce a report
```

## Adding a tool

**1. Define the interface** in `catalogs/tools/my_tool.yaml`:

```yaml
name: my_tool
description: What the tool does — shown to the agent
parameters:
  type: object
  properties:
    param_one:
      type: string
      description: What this parameter is
  required: [param_one]
mock_response: |
  Realistic canned response used when MOON_MOCK_TOOLS=true
```

**2. Implement it** in `src/moon/tools/my_tool.py`:

```python
import httpx
from moon import config

def my_tool(param_one: str) -> str:
    with httpx.Client(timeout=30) as client:
        resp = client.get("https://api.example.com/lookup", params={"q": param_one},
                          headers={"Authorization": f"Bearer {config.MY_API_KEY}"})
        resp.raise_for_status()
    return resp.text
```

**3. Register it** in `src/moon/tool_registry.py`:

```python
from moon.tools.my_tool import my_tool

_REGISTRY = {
    "get_pr_diff": get_pr_diff,
    "my_tool": my_tool,
}
```

Once registered, the real function runs instead of the mock. The YAML `mock_response` is ignored.

## Architecture

```
src/moon/
  coordinator.py   — runbook selection (tag match → LLM fallback)
  agent.py         — step execution, tool call loop, caching
  executor.py      — orchestrates coordinator + agent across all steps
  catalog.py       — loads runbooks/tools/skills/guidelines from disk
  models.py        — Pydantic models for all data structures
  store.py         — case store (InMemory or DynamoDB)
  server.py        — FastAPI web server + SSE streaming
  cli.py           — Typer CLI (run / batch / serve)
  tool_registry.py — maps tool names to real handler functions
  tools/           — real tool implementations

catalogs/
  runbooks/        — YAML runbook definitions
  tools/           — YAML tool schemas + mock responses
  skills/          — Markdown agent personas
  guidelines/      — Markdown output and escalation rules
```

## Development

```bash
uv run pytest tests/          # run all 106 tests
uv run moon run "..." --debug  # verbose logging to stderr
```
