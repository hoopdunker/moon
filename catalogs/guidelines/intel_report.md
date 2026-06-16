# Threat Intelligence Report Format

**Tone**: factual, direct, no filler. Write for a technical CISO who reads quickly.
**Confidence levels**: High / Medium / Low on any inferred claim.
**IOC safety**: never write a clickable URL or undefanged domain — always defang.
**Data integrity**: only report findings that came from the tool results provided to you. Do NOT invent, infer, or extrapolate CVE IDs, package names, threat actors, breach victims, or IOCs. If a section has no data from the tools, write "None observed this period." — do not fill it with guesses.

Structure every threat intelligence brief exactly as follows. Do not skip sections — if there is no data for a section, write "None observed this period."

---

## Metrics Snapshot

A single summary line showing counts for the period covered:

**{N}-day snapshot** — {N} CVEs ({N} KEV) · {N} nation-state campaigns · {N} malware families · {N} breaches · {N} MITRE TTPs observed

---

## Executive Summary

2–3 sentences: the dominant threat theme this period, who is most at risk, and the single most urgent action required.

---

## Top Nation-State Actors

Table of active threat groups observed this period, ranked by activity level:

| Actor | Origin | Active Campaigns | Target Sectors | Key TTPs | Confidence |
|-------|--------|-----------------|----------------|----------|------------|

- **Actor**: Threat group name (e.g. Lazarus Group, APT29, Sandworm)
- **Origin**: Attributed nation-state or "Unknown"
- **Active Campaigns**: Campaign name or brief description
- **Target Sectors**: Industries or org types targeted
- **Key TTPs**: MITRE ATT&CK IDs (e.g. T1566.001, T1059.003) — list up to 3
- **Confidence**: High / Medium / Low based on source quality and corroboration

---

## Top Vulnerabilities

Top vulnerabilities ranked by real-world urgency (KEV status + CVSS + exploitability), not CVSS alone:

| CVE | CVSS | Product | Versions Affected | Fix Version | KEV | Exploited In Wild | Risk to Our Env |
|-----|------|---------|-------------------|-------------|-----|-------------------|-----------------|

- **Risk to Our Env**: High / Medium / Low / Not Applicable — based on whether the product is in the organisation's asset inventory
- **KEV**: Yes (deadline: YYYY-MM-DD) or No
- Flag where the KEV deadline falls inside or outside the organisation's patch SLA

---

## Top Malware Families

Active malware families observed in threat feeds this period:

| Family | Type | First Seen | IOC Count | Delivery Method | C2 / Infrastructure | Notable Targets |
|--------|------|------------|-----------|-----------------|--------------------|-|

- **Type**: Ransomware / Infostealer / RAT / Loader / Wiper / Botnet / Other
- **Delivery Method**: Phishing / Drive-by / Supply chain / Exploit / Other
- Keep all IOCs defanged: replace `.` with `[.]` and `://` with `[://]`

---

## Top Breaches

Notable breaches and incidents reported this period:

| Target | Sector | Date | Attack Vector | Data / Impact | Amount Lost | Source |
|--------|--------|------|---------------|---------------|-------------|--------|

- For crypto incidents include amount lost in USD
- For enterprise breaches include data type affected (PII, credentials, source code, etc.)
- Note if the breach is confirmed, alleged, or under investigation

---

## Top Affected Packages

Open-source packages with confirmed malicious activity or critical vulnerabilities this period:

| Package | Registry | Versions Affected | Threat Type | Severity | Action |
|---------|----------|-------------------|-------------|----------|--------|

- **Registry**: npm / PyPI / Maven / RubyGems / crates.io / Other
- **Threat Type**: Malicious publish / Dependency confusion / CVE / Typosquat
- **Action**: Remove immediately / Pin to safe version / Monitor / No action needed

---

## Top MITRE ATT&CK TTPs

Most frequently observed tactics and techniques across all intelligence this period:

| TTP ID | Name | Tactic | Actors Using | Detectable With Our Controls | Hunt in Log Source |
|--------|------|--------|-------------|------------------------------|-------------------|

- Map each TTP to a specific log source from the organisation's environment profile where evidence can be found
- **Detectable**: Yes / Partial / No — based on controls defined in the environment profile
- Link TTPs back to the nation-state actors and malware families listed above where applicable

---

## CVE Patching Priorities

Full patching table ordered by urgency (KEV first, then CVSS descending):

| CVE ID | CVSS | Product | Versions Affected | Fix Version | KEV Deadline | Our SLA | Action |
|--------|------|---------|-------------------|-------------|--------------|---------|--------|

- **Our SLA**: pull from the environment profile patch_slas field
- **Action**: Patch immediately / Patch within SLA / Apply hotfix (no patch) / Not in inventory — monitor

---

## Active IOCs

Defang all indicators: replace `.` with `[.]` and `://` with `[://]`.
Group by type:

**IP Addresses**
**Domains**
**File Hashes (SHA256)**
**URLs**

For each IOC include: source feed, associated malware family or campaign, and which log source to hunt in.

---

## Recommended Actions

Ordered by urgency. Each item must specify:
- **Owner**: Security team / IT ops / Dev team / Leadership
- **Timeframe**: Immediate / 24h / 7 days / 30 days
- **Action**: Specific and concrete — reference the exact control, log source, CVE ID, or IOC involved. No vague directives.

Where a control gap exists (from the environment profile), flag it explicitly and recommend either an interim compensating control or escalation.

---

## Intelligence Gaps

List areas where data was unavailable, feeds were unreachable, or confidence is low. Flag any attribution that is inferred rather than directly confirmed.

---

**Tone**: factual, direct, no filler. Write for a technical CISO who reads quickly.
**Confidence levels**: High / Medium / Low on any inferred claim.
**IOC safety**: never write a clickable URL or undefanged domain — always defang.
