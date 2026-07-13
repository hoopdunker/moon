import html
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

TIMEOUT = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB hard cap — never buffer a binary
# abuse.ch bulk downloads (URLhaus json_recent) run ~11 MB of pure JSON from a
# pinned URL — allow more for those specific fetches only.
BULK_FEED_MAX_BYTES = 20 * 1024 * 1024

# Only these content-type prefixes are accepted. Anything else (octet-stream,
# application/zip, etc.) is rejected before the body is used.
_SAFE_CONTENT_PREFIXES = (
    "text/",
    "application/xml",
    "application/rss+xml",
    "application/atom+xml",
    "application/json",
    "application/feed+json",
)

RSS_SOURCES = {
    # General security news
    "bleepingcomputer": "https://www.bleepingcomputer.com/feed/",
    "hackernews": "https://feeds.feedburner.com/TheHackersNews",
    "krebsonsecurity": "https://krebsonsecurity.com/feed/",
    "sans_isc": "https://isc.sans.edu/rssfeed.xml",
    "darkreading": "https://www.darkreading.com/rss.xml",
    "securityweek": "https://feeds.feedburner.com/Securityweek",
    # Nation-state / APT threat intelligence
    "recorded_future": "https://www.recordedfuture.com/feed",
    "mandiant": "https://cloud.google.com/blog/topics/threat-intelligence/rss/",
    "crowdstrike": "https://www.crowdstrike.com/blog/feed/",
    "microsoft_security": "https://www.microsoft.com/en-us/security/blog/feed/",
    "ncsc_uk": "https://www.ncsc.gov.uk/api/1/services/v1/report-rss-feed.xml",
    "cisa_advisories": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
    # Crypto / blockchain breach tracking
    "chainalysis": "https://www.chainalysis.com/blog/feed/",
    "cointelegraph_security": "https://cointelegraph.com/rss/category/security",
    "the_block": "https://www.theblock.co/rss.xml",
    "slowmist": "https://slowmist.medium.com/feed",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "immunefi": "https://medium.com/feed/immunefi",
    "elliptic": "https://www.elliptic.co/blog/rss.xml",
    "peckshield": "https://peckshield.medium.com/feed",
    # Security vendor research blogs
    "unit42": "https://unit42.paloaltonetworks.com/feed/",
    "talos": "https://blog.talosintelligence.com/rss/",
    "checkpoint_research": "https://research.checkpoint.com/feed/",
    "welivesecurity": "https://www.welivesecurity.com/feed/",
    "securelist": "https://securelist.com/feed/",
    "sentinelone": "https://www.sentinelone.com/blog/feed/",
    "elastic_security": "https://www.elastic.co/security-labs/rss/feed.xml",
    "rapid7": "https://www.rapid7.com/blog/rss/",
    # Vulnerability research
    "project_zero": "https://googleprojectzero.blogspot.com/feeds/posts/default",
    "zdi": "https://www.zerodayinitiative.com/rss/published/",
    "exploit_db": "https://www.exploit-db.com/rss.xml",
    "portswigger_research": "https://portswigger.net/research/rss",
    "vuldb": "https://vuldb.com/?rss.recent",
    # Supply chain security
    "sonatype": "https://blog.sonatype.com/rss.xml",
    "snyk": "https://snyk.io/blog/feed/",
    "checkmarx": "https://checkmarx.com/blog/feed/",
    "openssf": "https://openssf.org/feed/",
    "chainguard": "https://www.chainguard.dev/unchained/rss.xml",
    "stepsecurity": "https://www.stepsecurity.io/blog/rss.xml",
    # Cloud provider security bulletins
    "aws_security": "https://aws.amazon.com/security/security-bulletins/rss/",
    "gcp_security": "https://cloud.google.com/security/resources/rss",
    "msrc_blog": "https://msrc.microsoft.com/blog/feed",
    # Vendor patch advisories
    "sap_security": "https://support.sap.com/content/dam/support/en_us/library/ssp/my-support/trust-center/sap-security-patch-day/rss-feed.xml",
    "ms_isac": "https://www.cisecurity.org/feed/advisories",
    # Breach tracking
    "databreaches_net": "https://www.databreaches.net/feed/",
    "securityaffairs": "https://securityaffairs.com/feed",
    "hipaa_journal": "https://www.hipaajournal.com/feed/",
    # Geopolitical & threat research
    "the_record": "https://therecord.media/feed/",
    "cyberscoop": "https://cyberscoop.com/feed/",
    "sekoia": "https://blog.sekoia.io/feed/",
    "huntress": "https://www.huntress.com/blog/rss.xml",
    "lumu": "https://lumu.io/blog/feed/",
    # AI security
    "trail_of_bits": "https://blog.trailofbits.com/feed",
    "wiz_research": "https://www.wiz.io/blog/rss",
    # Cloud & application security
    "upwind": "https://www.upwind.io/feed",
}

_HEADERS = {"User-Agent": "Moon-ThreatIntel/1.0"}

# Per-source header overrides. CISA's CDN rejects unknown agents (403) but
# accepts curl's, which is the documented way to pull their public feed.
_SOURCE_HEADERS: dict[str, dict] = {
    "cisa_advisories": {"User-Agent": "curl/8.7.1"},
}


def _safe_text(resp: httpx.Response) -> str:
    ct = resp.headers.get("content-type", "")
    if not any(ct.startswith(p) for p in _SAFE_CONTENT_PREFIXES):
        raise ValueError(f"Blocked response: unexpected content-type '{ct}'")
    if len(resp.content) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Blocked response: {len(resp.content)} bytes exceeds {MAX_RESPONSE_BYTES} limit")
    return resp.text


def _safe_json(resp: httpx.Response, max_bytes: int = MAX_RESPONSE_BYTES) -> dict | list:
    ct = resp.headers.get("content-type", "")
    if not any(ct.startswith(p) for p in _SAFE_CONTENT_PREFIXES):
        raise ValueError(f"Blocked response: unexpected content-type '{ct}'")
    if len(resp.content) > max_bytes:
        raise ValueError(f"Blocked response: {len(resp.content)} bytes exceeds {max_bytes} limit")
    return resp.json()


def _abusech_key() -> str:
    """abuse.ch Auth-Key (free — register at auth.abuse.ch). Enables ThreatFox."""
    return os.environ.get("MOON_ABUSECH_API_KEY", "")


def _defang(indicator: str) -> str:
    return (
        indicator.replace("https://", "hxxps[://]")
        .replace("http://", "hxxp[://]")
        .replace(".", "[.]")
    )


def _clean_desc(raw: str) -> str:
    """Strip HTML tags, unescape entities, collapse whitespace, cap length."""
    text = html.unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"\s+", " ", text).strip()[:500]


def _parse_feed(xml_text: str, max_items: int) -> list[dict]:
    root = ET.fromstring(xml_text)

    items = []
    for item in root.findall(".//item")[:max_items]:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        desc = _clean_desc(item.findtext("description", ""))
        items.append({"title": title, "link": link, "pubDate": pub_date, "description": desc})

    if not items:
        # Atom 1.0
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns)[:max_items]:
            title = entry.findtext("a:title", "", ns).strip()
            link_el = entry.find("a:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            pub_date = entry.findtext("a:published", entry.findtext("a:updated", "", ns), ns).strip()
            desc = _clean_desc(entry.findtext("a:summary", entry.findtext("a:content", "", ns), ns))
            items.append({"title": title, "link": link, "pubDate": pub_date, "description": desc})

    return items


def _parse_pub_date(date_str: str) -> datetime | None:
    """Parse publication dates from RSS (RFC 2822), Atom (ISO 8601), and abuse.ch formats."""
    if not date_str:
        return None
    # RFC 2822: "Tue, 14 Jan 2025 08:22:01 +0000"
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    # ISO 8601: "2025-01-14T08:22:01Z" or "2025-01-14T08:22:01+00:00"
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str[:19], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    # abuse.ch: "2025-01-14 08:22:01"
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        pass
    # CISA KEV: date-only "2025-01-14"
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _after_cutoff(date_str: str, cutoff: datetime) -> bool:
    """True if date_str is at or after cutoff. Unparseable dates are included by default."""
    dt = _parse_pub_date(date_str)
    if dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff


def fetch_security_news(
    sources: list[str] | None = None,
    max_items: int = 5,
    hours_back: int = 24,
) -> str:
    if not sources:
        sources = list(RSS_SOURCES.keys())
    # max_items=0 → no per-feed cap; the hours_back window does the filtering.
    max_items = None if max_items <= 0 else min(max_items, 20)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    results = []
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for source in sources:
            url = RSS_SOURCES.get(source)
            if not url:
                results.append(f"=== {source} ===\nUnknown source.\n")
                continue
            try:
                resp = client.get(url, headers={**_HEADERS, **_SOURCE_HEADERS.get(source, {})})
                resp.raise_for_status()
                # Fetch extra candidates so filtering by date still yields max_items
                parse_cap = max_items * 5 if max_items else 10_000
                all_items = _parse_feed(_safe_text(resp), parse_cap)
                feed_items = [i for i in all_items if _after_cutoff(i["pubDate"], cutoff)][:max_items]
                label = source.replace("_", " ").title()
                section = f"=== {label} ===\n"
                if not feed_items:
                    section += f"  No items in the last {hours_back}h.\n"
                else:
                    for item in feed_items:
                        date = item["pubDate"][:16] if item["pubDate"] else "?"
                        section += f"[{date}] {item['title']}\n"
                        if item["description"]:
                            section += f"  {item['description']}\n"
                        if item["link"]:
                            section += f"  {item['link']}\n"
                results.append(section)
            except Exception as e:
                results.append(f"=== {source} ===\nError: {e}\n")

    return "\n".join(results) or "No news items retrieved."


def fetch_latest_cves(
    severity: str = "critical_and_high",
    hours_back: int = 24,
    max_results: int = 10,
) -> str:
    hours_back = min(max(hours_back, 1), 720)  # cap at 30 days
    max_results = min(max(max_results, 1), 50)

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)
    pub_start = start.strftime("%Y-%m-%dT%H:%M:%S.000")
    pub_end = now.strftime("%Y-%m-%dT%H:%M:%S.000")

    # Load CISA KEV for cross-reference
    kev_cves: set[str] = set()
    kev_deadlines: dict[str, str] = {}
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(
                "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
                headers=_HEADERS,
            )
            resp.raise_for_status()
            for vuln in _safe_json(resp).get("vulnerabilities", []):
                cid = vuln.get("cveID", "")
                kev_cves.add(cid)
                kev_deadlines[cid] = vuln.get("dueDate", "")
    except Exception:
        pass  # KEV cross-reference is best-effort

    # NVD requires both pubStartDate and pubEndDate when either is used
    url = (
        f"https://services.nvd.nist.gov/rest/json/cves/2.0"
        f"?pubStartDate={pub_start}&pubEndDate={pub_end}&resultsPerPage={max_results}"
    )
    if severity == "critical":
        url += "&cvssV3Severity=CRITICAL"
    elif severity == "high":
        url += "&cvssV3Severity=HIGH"

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            cves = _safe_json(resp).get("vulnerabilities", [])
    except Exception as e:
        return f"Error fetching CVEs from NVD: {e}"

    if not cves:
        return f"No CVEs found in the last {hours_back}h matching criteria."

    def _sort_key(v: dict) -> tuple:
        cid = v["cve"]["id"]
        score = _cvss_score(v)
        return (cid not in kev_cves, -score)

    cves.sort(key=_sort_key)

    kev_count = sum(1 for v in cves if v["cve"]["id"] in kev_cves)
    lines = [f"Fetched {len(cves)} CVEs from NVD (last {hours_back}h). {kev_count} in CISA KEV.\n"]

    kev_items = [v for v in cves if v["cve"]["id"] in kev_cves]
    other_items = [v for v in cves if v["cve"]["id"] not in kev_cves]

    if kev_items:
        lines.append("★ CISA KEV (Actively Exploited):")
        for v in kev_items:
            lines.append(_format_cve(v, kev_deadlines))

    if other_items:
        if kev_items:
            lines.append("\nOther CVEs:")
        for v in other_items:
            lines.append(_format_cve(v, {}))

    return "\n".join(lines)


def _cvss_score(v: dict) -> float:
    metrics = v["cve"].get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        if key in metrics and metrics[key]:
            return metrics[key][0]["cvssData"].get("baseScore", 0.0)
    return 0.0


def _format_cve(v: dict, kev_deadlines: dict) -> str:
    cve = v["cve"]
    cid = cve["id"]
    desc = next(
        (d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"),
        "",
    )[:250]
    metrics = cve.get("metrics", {})
    score, severity = "N/A", ""
    for key in ("cvssMetricV31", "cvssMetricV30"):
        if key in metrics and metrics[key]:
            m = metrics[key][0]["cvssData"]
            score = m.get("baseScore", "N/A")
            severity = m.get("baseSeverity", "")
            break
    deadline = kev_deadlines.get(cid, "")
    deadline_str = f" | KEV deadline: {deadline}" if deadline else ""

    # Extract affected version ranges and fix versions from CPE configurations
    affected: list[str] = []
    fix_versions: list[str] = []
    for config in cve.get("configurations", []):
        for node in config.get("nodes", []):
            for match in node.get("cpeMatch", []):
                if not match.get("vulnerable", False):
                    continue
                parts = match.get("criteria", "").split(":")
                product = parts[4] if len(parts) > 4 else ""
                ver = parts[5] if len(parts) > 5 else ""
                v_start_inc = match.get("versionStartIncluding", "")
                v_start_exc = match.get("versionStartExcluding", "")
                v_end_inc = match.get("versionEndIncluding", "")
                v_end_exc = match.get("versionEndExcluding", "")

                if ver and ver not in ("*", "-"):
                    affected.append(f"{product} {ver}")
                else:
                    r = product
                    if v_start_inc:
                        r += f" >={v_start_inc}"
                    elif v_start_exc:
                        r += f" >{v_start_exc}"
                    if v_end_inc:
                        r += f" <={v_end_inc}"
                    elif v_end_exc:
                        r += f" <{v_end_exc}"
                    if r != product:
                        affected.append(r)

                if v_end_exc:
                    fix_versions.append(f"{product} {v_end_exc}")

    # Deduplicate, cap length
    affected = list(dict.fromkeys(affected))[:5]
    fix_versions = list(dict.fromkeys(fix_versions))[:3]

    # Patch/vendor advisory references as fallback
    patch_refs = [
        ref.get("url", "")
        for ref in cve.get("references", [])
        if any(t in ref.get("tags", []) for t in ("Patch", "Vendor Advisory", "Fix"))
    ]

    lines = [f"{cid} | CVSS {score} {severity}{deadline_str}", f"  {desc}"]
    if affected:
        lines.append(f"  Affected: {'; '.join(affected)}")
    if fix_versions:
        lines.append(f"  Fix: upgrade to {'; '.join(fix_versions)}")
    elif patch_refs:
        lines.append(f"  Fix: see vendor advisory — {patch_refs[0]}")
    else:
        lines.append(
            "  Fix: no patch available — isolate affected component, apply WAF/network-level"
            " controls, and monitor vendor advisory for emergency patch"
        )

    return "\n".join(lines) + "\n"


def fetch_threat_feeds(feed_type: str = "all", max_items: int = 10, hours_back: int = 168) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    results = []

    if feed_type in ("all", "cisa_alerts"):
        # CISA KEV (actively exploited vulnerabilities) — still works
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = client.get(
                    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                all_vulns = _safe_json(resp).get("vulnerabilities", [])
                recent = [
                    v for v in all_vulns
                    if _after_cutoff(v.get("dateAdded", ""), cutoff)
                ][:max_items]
            section = f"=== CISA KEV (Actively Exploited — last {hours_back}h) ===\n"
            if not recent:
                section += f"  No new KEV entries in the last {hours_back}h.\n"
            else:
                for v in recent:
                    section += (
                        f"{v.get('cveID', '?')} | {v.get('vendorProject', '?')} — {v.get('product', '?')}\n"
                        f"  {v.get('shortDescription', '')[:200]}\n"
                        f"  Added: {v.get('dateAdded', '?')} | Due: {v.get('dueDate', 'N/A')}\n"
                    )
            results.append(section)
        except Exception as e:
            results.append(f"=== CISA KEV ===\nError: {e}\n")

    if feed_type in ("all", "defi_hacks"):
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = client.get("https://api.llama.fi/hacks", headers=_HEADERS)
                resp.raise_for_status()
                all_hacks = _safe_json(resp)
            cutoff_ts = cutoff.timestamp()
            recent = [h for h in all_hacks if h.get("date", 0) >= cutoff_ts]
            recent.sort(key=lambda h: h.get("amount", 0), reverse=True)
            recent = recent[:max_items]
            section = f"=== DeFiLlama — DeFi/Web3 Hacks (last {hours_back}h) ===\n"
            if not recent:
                section += f"  No hacks recorded in the last {hours_back}h.\n"
            else:
                for h in recent:
                    amount = f"${h['amount']:,.0f}" if h.get("amount") else "unknown"
                    chains = ", ".join(h.get("chain", [])) or "unknown"
                    returned = f" (${h['returnedFunds']:,.0f} returned)" if h.get("returnedFunds") else ""
                    section += (
                        f"{h.get('name', '?')} | {amount}{returned}\n"
                        f"  Chain: {chains} | Type: {h.get('targetType', '?')}\n"
                        f"  Attack: {h.get('classification', '?')} — {h.get('technique', '?')}\n"
                    )
            results.append(section)
        except Exception as e:
            results.append(f"=== DeFiLlama Hacks ===\nError: {e}\n")

    if feed_type in ("all", "iocs"):
        # URLhaus — recent malicious URLs (no auth; ~11 MB bulk JSON, 30-day window)
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = client.get("https://urlhaus.abuse.ch/downloads/json_recent/", headers=_HEADERS)
                resp.raise_for_status()
                data = _safe_json(resp, max_bytes=BULK_FEED_MAX_BYTES)
            entries = [e for v in data.values() for e in (v if isinstance(v, list) else [v])]
            recent = [e for e in entries if _after_cutoff(e.get("dateadded", ""), cutoff)]
            recent.sort(key=lambda e: e.get("dateadded", ""), reverse=True)
            recent = recent[:max_items]
            section = f"=== URLhaus — Malicious URLs (last {hours_back}h) ===\n"
            if not recent:
                section += f"  No URLs in the last {hours_back}h.\n"
            else:
                for e in recent:
                    tags = ", ".join(e.get("tags") or []) or "untagged"
                    section += (
                        f"{_defang(e.get('url', '?'))}\n"
                        f"  Status: {e.get('url_status', '?')} | Threat: {e.get('threat', '?')} | Tags: {tags}\n"
                    )
            results.append(section)
        except Exception as e:
            results.append(f"=== URLhaus ===\nError: {e}\n")

        # Feodo Tracker — active botnet C2 servers (no auth; small snapshot)
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = client.get("https://feodotracker.abuse.ch/downloads/ipblocklist.json", headers=_HEADERS)
                resp.raise_for_status()
                c2s = _safe_json(resp)
            section = "=== Feodo Tracker — Botnet C2 Blocklist ===\n"
            if not c2s:
                section += "  No active C2s listed.\n"
            else:
                for c2 in c2s[:max_items]:
                    ip = _defang(str(c2.get("ip_address", "?")))
                    section += (
                        f"{ip}:{c2.get('port', '?')} | {c2.get('malware', '?')}\n"
                        f"  Status: {c2.get('status', '?')} | Country: {c2.get('country', '?')}"
                        f" | AS: {c2.get('as_name', '?')} | Last online: {c2.get('last_online', '?')}\n"
                    )
            results.append(section)
        except Exception as e:
            results.append(f"=== Feodo Tracker ===\nError: {e}\n")

        # ThreatFox — IOCs tagged with malware family + confidence (requires free Auth-Key)
        key = _abusech_key()
        if not key:
            results.append(
                "=== ThreatFox ===\nSkipped: set MOON_ABUSECH_API_KEY (free key from auth.abuse.ch)"
                " to enable IOCs with malware family and confidence.\n"
            )
        else:
            try:
                days = max(1, min(7, round(hours_back / 24)))
                with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                    resp = client.post(
                        "https://threatfox-api.abuse.ch/api/v1/",
                        json={"query": "get_iocs", "days": days},
                        headers={**_HEADERS, "Auth-Key": key},
                    )
                    resp.raise_for_status()
                    iocs = _safe_json(resp, max_bytes=BULK_FEED_MAX_BYTES).get("data", [])
                if not isinstance(iocs, list):
                    iocs = []
                iocs.sort(key=lambda i: i.get("confidence_level") or 0, reverse=True)
                iocs = iocs[:max_items]
                section = f"=== ThreatFox — IOCs (last {days}d) ===\n"
                if not iocs:
                    section += "  No IOCs returned.\n"
                else:
                    for i in iocs:
                        section += (
                            f"{_defang(str(i.get('ioc', '?')))} ({i.get('ioc_type', '?')})\n"
                            f"  Malware: {i.get('malware_printable', '?')} | Threat: {i.get('threat_type', '?')}"
                            f" | Confidence: {i.get('confidence_level', '?')} | First seen: {i.get('first_seen', '?')}\n"
                        )
                results.append(section)
            except Exception as e:
                results.append(f"=== ThreatFox ===\nError: {e}\n")

    return "\n".join(results) or "No threat feed data retrieved."
