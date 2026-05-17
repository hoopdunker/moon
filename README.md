# Moon

Multi-agent security orchestration system. Given a natural language task, Moon selects the right runbook, assembles the right tools and skills, and executes each step using Claude — producing structured security findings.

---

## Architecture

```
  ┌─────────────────────────────────────────────────────────┐
  │                          Moon                           │
  └─────────────────────────────────────────────────────────┘
          │ CLI                           │ Web UI
    moon run / batch              moon serve :8000
          │                              │
          └──────────────┬───────────────┘
                         ▼
               ┌──────────────────┐
               │   Coordinator    │  (claude-haiku)
               │                  │
               │  1. tag match    │  fast, no LLM call
               │  2. LLM fallback │  when ambiguous
               └────────┬─────────┘
                        │ selects runbook
                        ▼
               ┌──────────────────┐
               │     Runbook      │  YAML in catalogs/runbooks/
               │                  │
               │  steps[]         │
               │  tools[]         │
               │  skills[]        │
               │  guidelines[]    │
               └────────┬─────────┘
                        │
          ┌─────────────┼──────────────┐
          ▼             ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Agent    │  │ Agent    │  │ Agent    │  (claude-sonnet)
    │ Step 1   │  │ Step 2   │  │ Step N   │
    └────┬─────┘  └────┬─────┘  └────┬─────┘
         │              │              │
     tool calls     tool calls     synthesis
         │
  ┌──────┴──────────────────────────────────────┐
  │               Tool Registry                 │
  │                                             │
  │  get_pr_diff         → GitHub API           │
  │  fetch_security_news → 57 RSS/Atom feeds    │
  │  fetch_latest_cves   → NVD API v2 + CISA KEV│
  │  fetch_threat_feeds  → MalwareBazaar,URLhaus │
  │  query_threat_intel  → mock                 │
  │  get_ip_geo          → mock                 │
  │  get_passive_dns     → mock                 │
  │  get_alert_details   → mock                 │
  └─────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────┐
  │   Final Report   │  markdown, rendered in Web UI
  │   (structured)   │  or printed to terminal
  └──────────────────┘
         │
  ┌──────┴──────────────────────────────────────┐
  │                  Case Store                  │
  │  InMemory (default) or DynamoDB             │
  │  SSE stream → browser dashboard             │
  └─────────────────────────────────────────────┘
```

---

## Runbooks

| Runbook | Description | Tools |
|---|---|---|
| `pr_security_review` | Review a GitHub pull request for security vulnerabilities | `get_pr_diff` |
| `malicious_ip_investigation` | Investigate a suspicious IP across threat intel, geolocation, and passive DNS | `query_threat_intel`, `get_ip_geo`, `get_passive_dns` |
| `security_alert_triage` | Triage a security alert for lateral movement or host compromise | `get_alert_details`, `query_threat_intel` |
| `threat_intel_digest` | Pull headlines, CVEs, threat feeds, and supply chain intel from 57+ sources; synthesise a structured CISO brief with metrics, top-N tables, and environment-aware recommendations | `fetch_security_news`, `fetch_latest_cves`, `fetch_threat_feeds`, `get_environment_profile` |

---

## Tools

| Tool | Status | Description |
|---|---|---|
| `get_pr_diff` | Live | Fetches PR metadata, file list, and full diff from GitHub |
| `fetch_security_news` | Live | RSS/Atom headlines from 57 sources across 9 categories |
| `fetch_latest_cves` | Live | Recent CVEs from NVD API v2 + CISA KEV, with affected versions and fix versions |
| `fetch_threat_feeds` | Live | MalwareBazaar hashes/families, URLhaus IOCs (defanged), CISA advisories |
| `get_environment_profile` | Live | Reads `catalogs/environment.yaml` — controls, log sources, assets, patch SLAs |
| `get_ip_geo` | Mock | Geolocation, ASN, hosting provider, Tor/VPN flags |
| `get_passive_dns` | Mock | Passive DNS history — domains, first/last seen, infrastructure overlap |
| `query_threat_intel` | Mock | IOC lookup across threat intel databases |
| `get_alert_details` | Mock | Alert enrichment with host and process context |

Mock tools return realistic canned responses. Set `MOON_MOCK_TOOLS=false` to run real implementations — unregistered tools return an error instead of silently returning fake data.

### Threat Intel sources (`fetch_security_news`)

57 RSS/Atom feeds across 9 categories:

| Category | Sources |
|---|---|
| General security news | Krebs on Security, Schneier, Dark Reading, The Hacker News, Bleeping Computer, Ars Technica Security, Security Week, SANS ISC, Threatpost |
| Nation-state / APT | Mandiant, CrowdStrike, Recorded Future, Secureworks, Microsoft MSRC, Cyberscoop, The Record |
| Crypto / Web3 breaches | Rekt News, CoinDesk Security, Cointelegraph Security, DeFi Llama News, Decrypt |
| Vendor security blogs | Google Project Zero, Cloudflare Blog, AWS Security, Microsoft Security, GitHub Security, Rapid7, Qualys |
| Vulnerability research | Exploit-DB, Zero Day Initiative, NCC Group Research, Portswigger Research, Synacktiv |
| Supply chain | Socket.dev Blog, Snyk Security, Sonatype Blog, CISA Supply Chain, OpenSSF Blog |
| Cloud bulletins | AWS Security Bulletins, GCP Security Bulletins, Azure Security Updates, Kubernetes Security |
| Patch advisories | CISA Advisories, US-CERT, Adobe Security, Oracle Security Alerts |
| AI security | AI security research feeds |

### Safety guards

- **Content-type allowlist** — only `text/*`, `application/xml`, `application/json`, and related MIME types are processed; executables are rejected before any bytes are read
- **5 MB response cap** — oversized responses are truncated before parsing
- **No binary downloads** — MalwareBazaar returns JSON metadata only (hashes, tags, family names) — never the malware binary
- **Defanged URLs** — all URLhaus output replaces `.` with `[.]` and `://` with `[://]` so IOCs cannot be accidentally clicked
- `follow_redirects=False` on all abuse.ch requests

---

## Skills

**Skills** define the agent persona for each runbook step, injected as a system-level instruction.

| Skill | Description |
|---|---|
| `security_analyst` | Vulnerability assessment, risk rating, OWASP familiarity |
| `code_reviewer` | Secure code review, language-agnostic, SAST-style analysis |
| `threat_intel_analyst` | IP attribution, passive DNS pivoting, threat actor profiling, VirusTotal/Shodan/AbuseIPDB |
| `intel_editor` | Synthesis persona — extract and rank top-N findings, map TTPs to MITRE ATT&CK, cross-reference environment profile, connect dots across sections, write for a CISO with 10 minutes and zero tolerance for vague language |

---

## Guidelines

**Guidelines** are injected into every step that declares them.

| Guideline | Description |
|---|---|
| `output_format` | Structured report: summary, findings with severity, risk assessment, next steps with owners |
| `escalation_policy` | When to page on-call vs file a ticket vs log and monitor |
| `intel_report` | Full CISO brief structure: Metrics Snapshot, Executive Summary, Top Nation-State Actors, Top Vulnerabilities, Top Malware Families, Top Breaches, Top Affected Packages, Top MITRE ATT&CK TTPs, CVE Patching Priorities, Active IOCs (defanged), Recommended Actions, Intelligence Gaps |

---

## Running Moon

### Prerequisites

```bash
# Install dependencies
uv pip install -e ".[aws]"

# Required
export ANTHROPIC_API_KEY=sk-ant-...

# For PR security review
export GITHUB_TOKEN=ghp_...

# For threat intel feeds (abuse.ch APIs)
export ABUSECH_API_KEY=...

# For DynamoDB persistence (optional — defaults to in-memory)
export MOON_DYNAMO_TABLE=moon-cases
```

### CLI — single task

```bash
moon run "threat intel digest last 24 hours"
moon run "investigate IP 185.220.101.47 — repeated VPN auth failures"
moon run "review PR #42 in acme/backend for security issues"
moon run "triage alert CS-001 — lateral movement detected"
```

With a JSON input file:

```bash
moon run "review PR" --input tasks/examples/pr_review.json --verbose
```

### CLI — batch

```bash
moon batch tasks/batch.json --workers 5 --output-dir results/
```

### Web UI

```bash
MOON_MOCK_TOOLS=false moon serve
# → http://127.0.0.1:8000
```

The dashboard has two tabs:

**Cases tab** — submit tasks, watch step-by-step progress in real time via server-sent events, inspect per-step tool outputs, and read the final report.

**Intel tab** — dedicated threat intel digest view. Shows the latest completed digest rendered as formatted markdown (tables, headings, IOC sections). Features:
- **Run Digest** — submits a new `threat intel digest last 24 hours` case with one click
- **Live progress** — step-by-step indicator while a digest is running; previous report stays visible below it
- **View Case** — jumps to the underlying case in the Cases tab
- **Copy** — copies the report text to clipboard

### Docker

```bash
ANTHROPIC_API_KEY=sk-ant-... docker compose up --build
# Moon UI → http://localhost:8000
# DynamoDB Local → http://localhost:8001
```

For production set `MOON_MOCK_TOOLS=false` and provide real AWS credentials. The Docker image installs `boto3` and auto-creates the DynamoDB table on first startup.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required |
| `GITHUB_TOKEN` | — | Required for `get_pr_diff` |
| `ABUSECH_API_KEY` | — | Required for MalwareBazaar and URLhaus feeds |
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

---

## Extending Moon

### Adding a runbook

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
  - text: Third step — synthesise findings into a report
```

### Adding a tool

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

def my_tool(param_one: str) -> str:
    with httpx.Client(timeout=30) as client:
        resp = client.get("https://api.example.com/lookup", params={"q": param_one})
        resp.raise_for_status()
    return resp.text
```

**3. Register it** in `src/moon/tool_registry.py`:

```python
from moon.tools.my_tool import my_tool

_REGISTRY = {
    ...
    "my_tool": my_tool,
}
```

Once registered, the real function runs instead of the mock.

### Configuring your environment profile

Edit `catalogs/environment.yaml` to describe your infrastructure. The threat intel digest uses this to produce targeted recommendations — no generic advice.

```yaml
org: Acme Corp
industry: technology
controls:
  endpoint:
    - name: CrowdStrike Falcon
      coverage: all workstations and servers
  network:
    - name: Cloudflare WAF
      coverage: all public endpoints
  gaps:
    - No dark web monitoring
log_sources:
  - AWS CloudTrail
  - CrowdStrike Falcon telemetry
assets:
  cloud:
    provider: AWS
    regions: [us-east-1, us-west-2]
  critical_systems:
    - name: Payment processing
      notes: PCI DSS in scope
compliance: [SOC 2 Type II, PCI DSS 4.0]
patch_slas:
  critical: 24 hours
  high: 7 days
```

With this populated, the digest will:
- Skip CVEs for products not in your inventory
- Name the exact log source to hunt each IOC in
- Reference your specific controls for each mitigation
- Flag control gaps that increase your exposure
- Compare KEV deadlines against your patch SLAs

### Adding a skill or guideline

Drop a Markdown file in `catalogs/skills/` or `catalogs/guidelines/` and reference it by filename (without `.md`) in any runbook step.

---

## Project layout

```
src/moon/
  coordinator.py    — runbook selection (tag match → LLM fallback)
  agent.py          — step execution, tool call loop, result caching
  executor.py       — orchestrates coordinator + agent across all steps
  catalog.py        — loads runbooks/tools/skills/guidelines from disk
  models.py         — Pydantic models for all data structures
  store.py          — case store (InMemory or DynamoDB)
  server.py         — FastAPI web server + SSE streaming
  cli.py            — Typer CLI (run / batch / serve)
  tool_registry.py  — maps tool names to real handler functions
  tools/
    github.py         — get_pr_diff (live)
    threat_intel.py   — fetch_security_news, fetch_latest_cves, fetch_threat_feeds (live)
    environment.py    — get_environment_profile (live)
  static/
    index.html        — single-page dashboard (Cases tab + Intel tab)

catalogs/
  runbooks/         — YAML runbook definitions
  tools/            — YAML tool schemas + mock responses
  skills/           — Markdown agent personas
  guidelines/       — Markdown output and escalation rules
  environment.yaml  — your infrastructure profile (controls, logs, assets, patch SLAs)

tests/
  test_coordinator.py
  test_agent.py
  test_executor.py
  test_store.py
  test_tools_github.py
  test_tools_threat_intel.py   — 58 tests covering RSS/NVD/KEV/abuse.ch/version-fix logic
  test_tools_environment.py    — 21 tests for environment profile parsing
```

---

## Development

```bash
uv run pytest tests/           # run all tests
uv run moon run "..." --debug  # verbose logging to stderr
```
