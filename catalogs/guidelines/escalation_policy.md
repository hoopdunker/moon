# Escalation Policy

## Immediate Escalation — Page On-Call Now
Escalate immediately if any of the following are confirmed:
- Active data exfiltration in progress
- Compromised privileged account (domain admin, root, or service account with broad access)
- Lateral movement reaching production databases or secrets stores
- Critical vulnerability with a public exploit present in production-facing code

## Standard Escalation — File P2 Ticket, Notify Team Lead
- High-severity vulnerability in code pending merge to main
- Suspicious activity without confirmed compromise (investigate within 2h)
- Alerts with medium-confidence indicators of compromise

## Documentation Only — Log and Monitor
- Low-severity or informational findings with no immediate risk
- False positive detections
- Activity that is anomalous but has a confirmed benign explanation

Always include the following when escalating: alert or PR ID, affected systems or files, your confidence level (High / Medium / Low), and the specific indicator or finding that triggered escalation.
