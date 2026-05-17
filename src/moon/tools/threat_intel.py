import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

TIMEOUT = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB hard cap — never buffer a binary

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
    # Crypto / blockchain breach tracking
    "rekt_news": "https://rekt.news/rss/",
    "chainalysis": "https://www.chainalysis.com/blog/feed/",
    "cointelegraph_security": "https://cointelegraph.com/rss/category/security",
    "the_block": "https://www.theblock.co/rss.xml",
    "slowmist": "https://slowmist.medium.com/feed",
    # Security vendor research blogs
    "unit42": "https://unit42.paloaltonetworks.com/feed/",
    "talos": "https://blog.talosintelligence.com/rss/",
    "checkpoint_research": "https://research.checkpoint.com/feed/",
    "welivesecurity": "https://www.welivesecurity.com/feed/",
    "sophos_news": "https://news.sophos.com/en-us/feed/",
    "securelist": "https://securelist.com/feed/",
    "sentinelone": "https://www.sentinelone.com/blog/feed/",
    "elastic_security": "https://www.elastic.co/security-labs/rss/feed.xml",
    "trend_micro": "https://feeds.trendmicro.com/Anti-MalwareBlog/",
    "rapid7": "https://www.rapid7.com/blog/feed/",
    # Vulnerability research
    "project_zero": "https://googleprojectzero.blogspot.com/feeds/posts/default",
    "zdi": "https://www.zerodayinitiative.com/rss/published/",
    "exploit_db": "https://www.exploit-db.com/rss.xml",
    "portswigger_research": "https://portswigger.net/research/rss",
    "synacktiv": "https://www.synacktiv.com/feed",
    "packetstorm": "https://rss.packetstormsecurity.com/",
    "vuldb": "https://vuldb.com/?rss.recent",
    # Supply chain security
    "socket_dev": "https://socket.dev/blog/rss.xml",
    "sonatype": "https://blog.sonatype.com/rss.xml",
    "snyk": "https://snyk.io/blog/feed/",
    "checkmarx": "https://checkmarx.com/blog/feed/",
    "openssf": "https://openssf.org/feed/",
    "chainguard": "https://www.chainguard.dev/unchained/rss.xml",
    # Cloud provider security bulletins
    "aws_security": "https://aws.amazon.com/security/security-bulletins/rss/",
    "gcp_security": "https://cloud.google.com/feeds/gcp-security-bulletins.xml",
    "msrc_blog": "https://msrc.microsoft.com/blog/feed",
    # Vendor patch advisories (Patch Tuesday, CPU cycles)
    "adobe_psirt": "https://helpx.adobe.com/security/rss.xml",
    "oracle_cpu": "https://www.oracle.com/technetwork/topics/security/alerts-086861.rss",
    "sap_security": "https://support.sap.com/content/dam/support/en_us/library/ssp/my-support/trust-center/sap-security-patch-day/rss-feed.xml",
    # Regulatory & breach disclosure
    "ftc_press": "https://www.ftc.gov/feeds/press-releases.xml",
    "ico_uk": "https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/rss.xml",
    "ms_isac": "https://www.cisecurity.org/ms-isac/advisories/rss",
    "hipaa_journal": "https://www.hipaajournal.com/feed/",
    # Geopolitical & policy
    "the_record": "https://therecord.media/feed/",
    "cyberscoop": "https://cyberscoop.com/feed/",
    "lawfare": "https://www.lawfaremedia.org/feeds/rss",
    "politico_cyber": "https://rss.politico.com/cybersecurity.xml",
    # AI security
    "hiddenlayer": "https://hiddenlayer.com/research/feed/",
    "protect_ai": "https://protectai.com/feed",
    "lakera": "https://www.lakera.ai/blog/rss.xml",
    "trail_of_bits": "https://blog.trailofbits.com/feed",
    "adversa_ai": "https://adversa.ai/blog/rss/",
    "wiz_research": "https://www.wiz.io/blog/rss",
}

_HEADERS = {"User-Agent": "Moon-ThreatIntel/1.0"}


def _safe_text(resp: httpx.Response) -> str:
    ct = resp.headers.get("content-type", "")
    if not any(ct.startswith(p) for p in _SAFE_CONTENT_PREFIXES):
        raise ValueError(f"Blocked response: unexpected content-type '{ct}'")
    if len(resp.content) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Blocked response: {len(resp.content)} bytes exceeds {MAX_RESPONSE_BYTES} limit")
    return resp.text


def _safe_json(resp: httpx.Response) -> dict | list:
    ct = resp.headers.get("content-type", "")
    if not any(ct.startswith(p) for p in _SAFE_CONTENT_PREFIXES):
        raise ValueError(f"Blocked response: unexpected content-type '{ct}'")
    if len(resp.content) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Blocked response: {len(resp.content)} bytes exceeds {MAX_RESPONSE_BYTES} limit")
    return resp.json()


def _parse_feed(xml_text: str, max_items: int) -> list[dict]:
    root = ET.fromstring(xml_text)

    items = []
    for item in root.findall(".//item")[:max_items]:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        desc = re.sub(r"<[^>]+>", "", item.findtext("description", "")).strip()[:300]
        items.append({"title": title, "link": link, "pubDate": pub_date, "description": desc})

    if not items:
        # Atom 1.0
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns)[:max_items]:
            title = entry.findtext("a:title", "", ns).strip()
            link_el = entry.find("a:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            pub_date = entry.findtext("a:published", entry.findtext("a:updated", "", ns), ns).strip()
            desc = re.sub(
                r"<[^>]+>",
                "",
                entry.findtext("a:summary", entry.findtext("a:content", "", ns), ns),
            ).strip()[:300]
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
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    results = []
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for source in sources:
            url = RSS_SOURCES.get(source)
            if not url:
                results.append(f"=== {source} ===\nUnknown source.\n")
                continue
            try:
                resp = client.get(url, headers=_HEADERS)
                resp.raise_for_status()
                # Fetch extra candidates so filtering by date still yields max_items
                all_items = _parse_feed(_safe_text(resp), max_items * 5)
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

    start = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    pub_start = start.strftime("%Y-%m-%dT%H:%M:%S.000")

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

    url = (
        f"https://services.nvd.nist.gov/rest/json/cves/2.0"
        f"?pubStartDate={pub_start}&resultsPerPage={max_results}&noRejected"
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


def fetch_threat_feeds(feed_type: str = "all", max_items: int = 10, hours_back: int = 24) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    results = []

    if feed_type in ("all", "malware"):
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
                resp = client.post(
                    "https://mb-api.abuse.ch/api/v1/",
                    data={"query": "get_recent", "selector": "time"},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                all_samples = _safe_json(resp).get("data", [])
                samples = [s for s in all_samples if _after_cutoff(s.get("first_seen", ""), cutoff)][:max_items]
            section = "=== MalwareBazaar (Recent Samples) ===\n"
            if not samples:
                section += f"  No samples in the last {hours_back}h.\n"
            else:
                for s in samples:
                    tags = ", ".join(s.get("tags") or []) or "none"
                    section += (
                        f"SHA256: {s.get('sha256_hash', 'N/A')[:16]}...\n"
                        f"  Family: {s.get('signature') or 'Unknown'} | Tags: {tags}\n"
                        f"  First seen: {s.get('first_seen', 'N/A')}\n"
                    )
            results.append(section)
        except Exception as e:
            results.append(f"=== MalwareBazaar ===\nError: {e}\n")

    if feed_type in ("all", "urls"):
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
                resp = client.post(
                    "https://urlhaus-api.abuse.ch/v1/urls/recent/",
                    data={"limit": str(max_items * 10)},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                all_urls = _safe_json(resp).get("urls", [])
                urls = [u for u in all_urls if _after_cutoff(u.get("date_added", ""), cutoff)][:max_items]
            section = "=== URLhaus (Malicious URLs) ===\n"
            if not urls:
                section += f"  No URLs in the last {hours_back}h.\n"
            else:
                for u in urls:
                    defanged = u.get("url", "").replace(".", "[.]").replace("://", "[://]")
                    tags = ", ".join(u.get("tags") or []) or "none"
                    section += f"{defanged}\n  Status: {u.get('url_status', '?')} | Tags: {tags}\n"
            results.append(section)
        except Exception as e:
            results.append(f"=== URLhaus ===\nError: {e}\n")

    if feed_type in ("all", "cisa_alerts"):
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = client.get(
                    "https://www.cisa.gov/cybersecurity-advisories/all.xml",
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                all_items = _parse_feed(_safe_text(resp), max_items * 5)
                items = [i for i in all_items if _after_cutoff(i["pubDate"], cutoff)][:max_items]
            section = "=== CISA Alerts & Advisories ===\n"
            if not items:
                section += f"  No advisories in the last {hours_back}h.\n"
            else:
                for item in items:
                    date = item["pubDate"][:16] if item["pubDate"] else "?"
                    section += f"[{date}] {item['title']}\n"
                    if item["description"]:
                        section += f"  {item['description'][:200]}\n"
            results.append(section)
        except Exception as e:
            results.append(f"=== CISA Alerts ===\nError: {e}\n")

    return "\n".join(results) or "No threat feed data retrieved."
