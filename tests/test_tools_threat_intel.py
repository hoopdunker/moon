from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from moon.tools.threat_intel import (
    _after_cutoff,
    _format_cve,
    _parse_feed,
    _parse_pub_date,
    _safe_json,
    _safe_text,
    fetch_latest_cves,
    fetch_security_news,
    fetch_threat_feeds,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rfc2822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _mock_resp(content_type: str = "text/xml", text: str = "", json_data=None, size: int = 100):
    resp = MagicMock()
    resp.headers = MagicMock()
    resp.headers.get.side_effect = lambda k, d="": content_type if k == "content-type" else d
    resp.content = b"x" * size
    resp.text = text
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = MagicMock()
    return resp


def _make_client(*responses, method="get"):
    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    getattr(client, method).side_effect = list(responses)
    return client


RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Critical RCE in Apache</title>
    <link>https://example.com/rce</link>
    <pubDate>{date}</pubDate>
    <description>A critical remote code execution vulnerability.</description>
  </item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom Entry</title>
    <link href="https://example.com/atom"/>
    <published>{date}</published>
    <summary>Atom summary content.</summary>
  </entry>
</feed>"""

NVD_RESPONSE = {
    "vulnerabilities": [
        {
            "cve": {
                "id": "CVE-2025-1234",
                "descriptions": [{"lang": "en", "value": "Critical buffer overflow in Foo 1.0"}],
                "metrics": {
                    "cvssMetricV31": [{"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}]
                },
            }
        },
        {
            "cve": {
                "id": "CVE-2025-5678",
                "descriptions": [{"lang": "en", "value": "High severity auth bypass in Bar"}],
                "metrics": {
                    "cvssMetricV31": [{"cvssData": {"baseScore": 7.5, "baseSeverity": "HIGH"}}]
                },
            }
        },
    ]
}

KEV_RESPONSE = {
    "vulnerabilities": [
        {"cveID": "CVE-2025-1234", "dueDate": "2025-01-30"},
    ]
}

MB_RESPONSE = {
    "data": [
        {
            "sha256_hash": "abc123def456789012345678901234567890abcd",
            "signature": "AgentTesla",
            "tags": ["stealer", "keylogger"],
            "first_seen": _rfc2822(datetime.now(timezone.utc) - timedelta(hours=1)).replace("+0000", "UTC"),
        }
    ]
}

URLHAUS_RESPONSE = {
    "urls": [
        {
            "url": "http://malicious.example.com/payload.exe",
            "url_status": "online",
            "tags": ["emotet"],
            "date_added": (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        }
    ]
}


# ---------------------------------------------------------------------------
# _parse_pub_date
# ---------------------------------------------------------------------------

def test_parse_pub_date_rfc2822():
    result = _parse_pub_date("Tue, 14 Jan 2025 08:00:00 +0000")
    assert result is not None
    assert result.year == 2025
    assert result.month == 1
    assert result.day == 14


def test_parse_pub_date_iso8601_z():
    result = _parse_pub_date("2025-01-14T08:00:00Z")
    assert result is not None
    assert result.year == 2025
    assert result.hour == 8


def test_parse_pub_date_iso8601_no_tz():
    result = _parse_pub_date("2025-01-14T08:00:00")
    assert result is not None
    assert result.tzinfo is not None


def test_parse_pub_date_abusech_format():
    result = _parse_pub_date("2025-01-14 08:22:01")
    assert result is not None
    assert result.year == 2025
    assert result.minute == 22


def test_parse_pub_date_empty():
    assert _parse_pub_date("") is None


def test_parse_pub_date_invalid():
    assert _parse_pub_date("not-a-date") is None


# ---------------------------------------------------------------------------
# _after_cutoff
# ---------------------------------------------------------------------------

def test_after_cutoff_recent_item_included():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = _rfc2822(datetime.now(timezone.utc) - timedelta(hours=1))
    assert _after_cutoff(recent, cutoff) is True


def test_after_cutoff_old_item_excluded():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    old = _rfc2822(datetime.now(timezone.utc) - timedelta(hours=48))
    assert _after_cutoff(old, cutoff) is False


def test_after_cutoff_unparseable_date_included():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    assert _after_cutoff("not-a-date", cutoff) is True


def test_after_cutoff_empty_date_included():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    assert _after_cutoff("", cutoff) is True


# ---------------------------------------------------------------------------
# _safe_text
# ---------------------------------------------------------------------------

def test_safe_text_valid_content_type():
    resp = _mock_resp(content_type="text/xml; charset=utf-8", text="hello")
    assert _safe_text(resp) == "hello"


def test_safe_text_blocks_binary_content_type():
    resp = _mock_resp(content_type="application/octet-stream")
    with pytest.raises(ValueError, match="Blocked"):
        _safe_text(resp)


def test_safe_text_blocks_zip():
    resp = _mock_resp(content_type="application/zip")
    with pytest.raises(ValueError, match="Blocked"):
        _safe_text(resp)


def test_safe_text_blocks_oversized_response():
    resp = _mock_resp(content_type="text/xml", size=6 * 1024 * 1024)
    with pytest.raises(ValueError, match="Blocked"):
        _safe_text(resp)


def test_safe_text_accepts_json_content_type():
    resp = _mock_resp(content_type="application/json", text='{"ok": true}')
    assert _safe_text(resp) == '{"ok": true}'


# ---------------------------------------------------------------------------
# _safe_json
# ---------------------------------------------------------------------------

def test_safe_json_valid_content_type():
    resp = _mock_resp(content_type="application/json", json_data={"key": "val"})
    assert _safe_json(resp) == {"key": "val"}


def test_safe_json_blocks_binary():
    resp = _mock_resp(content_type="application/octet-stream")
    with pytest.raises(ValueError, match="Blocked"):
        _safe_json(resp)


def test_safe_json_blocks_oversized():
    resp = _mock_resp(content_type="application/json", size=6 * 1024 * 1024)
    with pytest.raises(ValueError, match="Blocked"):
        _safe_json(resp)


# ---------------------------------------------------------------------------
# _parse_feed
# ---------------------------------------------------------------------------

def test_parse_feed_rss20():
    now_str = _rfc2822(datetime.now(timezone.utc))
    xml = RSS_XML.format(date=now_str)
    items = _parse_feed(xml, max_items=5)
    assert len(items) == 1
    assert items[0]["title"] == "Critical RCE in Apache"
    assert items[0]["link"] == "https://example.com/rce"


def test_parse_feed_atom():
    items = _parse_feed(ATOM_XML.format(date="2025-01-14T08:00:00Z"), max_items=5)
    assert len(items) == 1
    assert items[0]["title"] == "Atom Entry"
    assert items[0]["link"] == "https://example.com/atom"


def test_parse_feed_respects_max_items():
    multi = RSS_XML.format(date=_rfc2822(datetime.now(timezone.utc))).replace(
        "</channel>",
        "<item><title>Extra</title><link>x</link><pubDate/><description/></item></channel>",
    )
    items = _parse_feed(multi, max_items=1)
    assert len(items) == 1


def test_parse_feed_strips_html_from_description():
    # Real RSS feeds use entity-encoded HTML, not raw tags (which would be invalid XML).
    xml = RSS_XML.format(date=_rfc2822(datetime.now(timezone.utc))).replace(
        "A critical remote code execution vulnerability.",
        "&lt;b&gt;Bold&lt;/b&gt; and &lt;a href='x'&gt;link&lt;/a&gt;",
    )
    items = _parse_feed(xml, max_items=5)
    assert "<b>" not in items[0]["description"]
    assert "Bold" in items[0]["description"]


# ---------------------------------------------------------------------------
# fetch_security_news
# ---------------------------------------------------------------------------

def test_fetch_security_news_returns_source_header():
    now_str = _rfc2822(datetime.now(timezone.utc))
    resp = _mock_resp(content_type="text/xml", text=RSS_XML.format(date=now_str))
    client = _make_client(resp)
    with patch("moon.tools.threat_intel.httpx.Client", return_value=client):
        result = fetch_security_news(sources=["bleepingcomputer"], hours_back=24)
    assert "Bleepingcomputer" in result


def test_fetch_security_news_returns_headline_within_window():
    now_str = _rfc2822(datetime.now(timezone.utc))
    resp = _mock_resp(content_type="text/xml", text=RSS_XML.format(date=now_str))
    client = _make_client(resp)
    with patch("moon.tools.threat_intel.httpx.Client", return_value=client):
        result = fetch_security_news(sources=["bleepingcomputer"], hours_back=24)
    assert "Critical RCE in Apache" in result


def test_fetch_security_news_filters_old_items():
    old_str = _rfc2822(datetime.now(timezone.utc) - timedelta(hours=48))
    resp = _mock_resp(content_type="text/xml", text=RSS_XML.format(date=old_str))
    client = _make_client(resp)
    with patch("moon.tools.threat_intel.httpx.Client", return_value=client):
        result = fetch_security_news(sources=["bleepingcomputer"], hours_back=24)
    assert "Critical RCE in Apache" not in result
    assert "No items in the last" in result


def test_fetch_security_news_unknown_source():
    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    with patch("moon.tools.threat_intel.httpx.Client", return_value=client):
        result = fetch_security_news(sources=["totally_unknown_source"])
    assert "Unknown source" in result


def test_fetch_security_news_http_error_continues():
    import httpx as real_httpx
    err_resp = MagicMock()
    err_resp.status_code = 503
    err_resp.text = "Service Unavailable"
    ok_resp = _mock_resp(
        content_type="text/xml",
        text=RSS_XML.format(date=_rfc2822(datetime.now(timezone.utc))),
    )
    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    client.get.side_effect = [
        real_httpx.HTTPStatusError("503", request=MagicMock(), response=err_resp),
        ok_resp,
    ]
    with patch("moon.tools.threat_intel.httpx.Client", return_value=client):
        result = fetch_security_news(sources=["bleepingcomputer", "hackernews"], hours_back=24)
    assert "Error" in result
    assert "Critical RCE in Apache" in result


def test_fetch_security_news_bad_content_type_shows_error():
    resp = _mock_resp(content_type="application/octet-stream", text="binary garbage")
    client = _make_client(resp)
    with patch("moon.tools.threat_intel.httpx.Client", return_value=client):
        result = fetch_security_news(sources=["bleepingcomputer"])
    assert "Error" in result


# ---------------------------------------------------------------------------
# fetch_latest_cves
# ---------------------------------------------------------------------------

def _make_cve_clients(kev_data=None, nvd_data=None):
    kev_resp = _mock_resp(content_type="application/json", json_data=kev_data or KEV_RESPONSE)
    nvd_resp = _mock_resp(content_type="application/json", json_data=nvd_data or NVD_RESPONSE)
    kev_client = _make_client(kev_resp)
    nvd_client = _make_client(nvd_resp)
    return [kev_client, nvd_client]


def test_fetch_latest_cves_returns_cve_id():
    clients = _make_cve_clients()
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=clients):
        result = fetch_latest_cves(hours_back=24)
    assert "CVE-2025-1234" in result


def test_fetch_latest_cves_kev_items_surface_first():
    clients = _make_cve_clients()
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=clients):
        result = fetch_latest_cves(hours_back=24)
    kev_pos = result.index("CVE-2025-1234")
    other_pos = result.index("CVE-2025-5678")
    assert kev_pos < other_pos


def test_fetch_latest_cves_shows_kev_marker():
    clients = _make_cve_clients()
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=clients):
        result = fetch_latest_cves(hours_back=24)
    assert "CISA KEV" in result


def test_fetch_latest_cves_shows_cvss_score():
    clients = _make_cve_clients()
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=clients):
        result = fetch_latest_cves(hours_back=24)
    assert "9.8" in result


def test_fetch_latest_cves_shows_kev_deadline():
    clients = _make_cve_clients()
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=clients):
        result = fetch_latest_cves(hours_back=24)
    assert "2025-01-30" in result


def test_fetch_latest_cves_no_results():
    kev_resp = _mock_resp(content_type="application/json", json_data={"vulnerabilities": []})
    nvd_resp = _mock_resp(content_type="application/json", json_data={"vulnerabilities": []})
    clients = [_make_client(kev_resp), _make_client(nvd_resp)]
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=clients):
        result = fetch_latest_cves(hours_back=24)
    assert "No CVEs found" in result


def test_fetch_latest_cves_nvd_error():
    import httpx as real_httpx
    kev_resp = _mock_resp(content_type="application/json", json_data=KEV_RESPONSE)
    kev_client = _make_client(kev_resp)
    nvd_client = MagicMock()
    nvd_client.__enter__ = lambda s: s
    nvd_client.__exit__ = MagicMock(return_value=False)
    err = MagicMock()
    err.status_code = 503
    nvd_client.get.side_effect = real_httpx.HTTPStatusError("503", request=MagicMock(), response=err)
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[kev_client, nvd_client]):
        result = fetch_latest_cves(hours_back=24)
    assert "Error fetching CVEs" in result


def test_fetch_latest_cves_kev_failure_still_returns_cves():
    import httpx as real_httpx
    kev_client = MagicMock()
    kev_client.__enter__ = lambda s: s
    kev_client.__exit__ = MagicMock(return_value=False)
    kev_client.get.side_effect = real_httpx.RequestError("timeout", request=MagicMock())
    nvd_resp = _mock_resp(content_type="application/json", json_data=NVD_RESPONSE)
    nvd_client = _make_client(nvd_resp)
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[kev_client, nvd_client]):
        result = fetch_latest_cves(hours_back=24)
    assert "CVE-2025-1234" in result


def test_fetch_latest_cves_hours_back_in_summary():
    clients = _make_cve_clients()
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=clients):
        result = fetch_latest_cves(hours_back=24)
    assert "24h" in result


# ---------------------------------------------------------------------------
# _format_cve — version / fix / hotfix logic
# ---------------------------------------------------------------------------

def _cve_entry(cve_id="CVE-2025-9999", score=9.8, severity="CRITICAL",
               configurations=None, references=None):
    return {
        "cve": {
            "id": cve_id,
            "descriptions": [{"lang": "en", "value": f"Test vuln in {cve_id}"}],
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": score, "baseSeverity": severity}}]
            },
            "configurations": configurations or [],
            "references": references or [],
        }
    }


def _cpe_node(product, ver_start_inc="", ver_end_exc="", ver_end_inc="", exact_ver=""):
    criteria = f"cpe:2.3:a:vendor:{product}:{exact_ver or '*'}:*:*:*:*:*:*:*"
    match = {"vulnerable": True, "criteria": criteria}
    if ver_start_inc:
        match["versionStartIncluding"] = ver_start_inc
    if ver_end_exc:
        match["versionEndExcluding"] = ver_end_exc
    if ver_end_inc:
        match["versionEndIncluding"] = ver_end_inc
    return {"nodes": [{"cpeMatch": [match]}]}


def test_format_cve_shows_affected_version_range():
    entry = _cve_entry(configurations=[_cpe_node("nginx", ver_start_inc="1.23.0", ver_end_exc="1.25.3")])
    result = _format_cve(entry, {})
    assert "Affected:" in result
    assert "nginx" in result
    assert "1.23.0" in result


def test_format_cve_shows_fix_version_from_versionEndExcluding():
    entry = _cve_entry(configurations=[_cpe_node("nginx", ver_start_inc="1.23.0", ver_end_exc="1.25.3")])
    result = _format_cve(entry, {})
    assert "Fix:" in result
    assert "1.25.3" in result


def test_format_cve_fix_uses_upgrade_language():
    entry = _cve_entry(configurations=[_cpe_node("openssl", ver_start_inc="3.0.0", ver_end_exc="3.0.9")])
    result = _format_cve(entry, {})
    assert "upgrade to" in result


def test_format_cve_exact_version_shown_as_affected():
    entry = _cve_entry(configurations=[_cpe_node("log4j", exact_ver="2.14.1")])
    result = _format_cve(entry, {})
    assert "Affected:" in result
    assert "2.14.1" in result


def test_format_cve_no_fix_version_uses_patch_reference():
    refs = [{"url": "https://vendor.example.com/advisory/SA-001", "tags": ["Vendor Advisory"]}]
    entry = _cve_entry(
        configurations=[_cpe_node("foobar", ver_start_inc="1.0.0", ver_end_inc="2.9.9")],
        references=refs,
    )
    result = _format_cve(entry, {})
    assert "Fix:" in result
    assert "vendor.example.com" in result


def test_format_cve_no_patch_shows_hotfix_guidance():
    # No configurations, no fix references
    entry = _cve_entry(
        references=[{"url": "https://nvd.nist.gov/vuln/detail/CVE-2025-9999", "tags": ["Third Party Advisory"]}]
    )
    result = _format_cve(entry, {})
    assert "Fix:" in result
    assert "no patch available" in result
    assert "isolate" in result


def test_format_cve_multiple_products_deduplicated():
    config = {
        "nodes": [{
            "cpeMatch": [
                {"vulnerable": True, "criteria": "cpe:2.3:a:vendor:nginx:*:*:*:*:*:*:*:*",
                 "versionStartIncluding": "1.0.0", "versionEndExcluding": "1.2.0"},
                {"vulnerable": True, "criteria": "cpe:2.3:a:vendor:nginx:*:*:*:*:*:*:*:*",
                 "versionStartIncluding": "1.0.0", "versionEndExcluding": "1.2.0"},
            ]
        }]
    }
    entry = _cve_entry(configurations=[config])
    result = _format_cve(entry, {})
    assert result.count("nginx >=1.0.0") == 1


def test_format_cve_kev_deadline_still_shown_with_version_info():
    entry = _cve_entry(configurations=[_cpe_node("ivanti", ver_start_inc="22.7.0", ver_end_exc="22.7.5")])
    result = _format_cve(entry, {"CVE-2025-9999": "2025-02-01"})
    assert "KEV deadline: 2025-02-01" in result
    assert "Fix:" in result


def test_format_cve_no_configurations_falls_back_gracefully():
    entry = _cve_entry()  # no configurations, no references
    result = _format_cve(entry, {})
    assert "CVE-2025-9999" in result
    assert "9.8" in result
    assert "no patch available" in result


# ---------------------------------------------------------------------------
# fetch_threat_feeds
# ---------------------------------------------------------------------------

def _mb_client(data=None, hours_ago=1):
    sample_time = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
    payload = data or {
        "data": [
            {
                "sha256_hash": "abc123def456789012345678901234567890abcd",
                "signature": "AgentTesla",
                "tags": ["stealer"],
                "first_seen": sample_time,
            }
        ]
    }
    resp = _mock_resp(content_type="application/json", json_data=payload)
    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    client.post.return_value = resp
    return client


def _uh_client(hours_ago=1):
    url_time = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "urls": [
            {
                "url": "http://malicious.example.com/payload.exe",
                "url_status": "online",
                "tags": ["emotet"],
                "date_added": url_time,
            }
        ]
    }
    resp = _mock_resp(content_type="application/json", json_data=payload)
    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    client.post.return_value = resp
    return client


def _cisa_client():
    xml = RSS_XML.format(date=_rfc2822(datetime.now(timezone.utc)))
    resp = _mock_resp(content_type="text/xml", text=xml)
    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    client.get.return_value = resp
    return client


def test_fetch_threat_feeds_malware_shows_family():
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[_mb_client(), _uh_client(), _cisa_client()]):
        result = fetch_threat_feeds(feed_type="malware")
    assert "AgentTesla" in result


def test_fetch_threat_feeds_malware_shows_sha256():
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[_mb_client()]):
        result = fetch_threat_feeds(feed_type="malware")
    assert "SHA256" in result


def test_fetch_threat_feeds_urls_defanged():
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[_uh_client()]):
        result = fetch_threat_feeds(feed_type="urls")
    assert "malicious[.]example[.]com" in result
    assert "http://malicious.example.com" not in result


def test_fetch_threat_feeds_urls_not_clickable():
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[_uh_client()]):
        result = fetch_threat_feeds(feed_type="urls")
    assert "hxxp[://]" in result or "[://]" in result


def test_fetch_threat_feeds_cisa_shows_title():
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[_cisa_client()]):
        result = fetch_threat_feeds(feed_type="cisa_alerts")
    assert "Critical RCE in Apache" in result


def test_fetch_threat_feeds_filters_old_malware():
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[_mb_client(hours_ago=48)]):
        result = fetch_threat_feeds(feed_type="malware", hours_back=24)
    assert "AgentTesla" not in result
    assert "No samples in the last" in result


def test_fetch_threat_feeds_filters_old_urls():
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[_uh_client(hours_ago=48)]):
        result = fetch_threat_feeds(feed_type="urls", hours_back=24)
    assert "malicious" not in result
    assert "No URLs in the last" in result


def test_fetch_threat_feeds_malware_only_skips_urlhaus():
    mb = _mb_client()
    with patch("moon.tools.threat_intel.httpx.Client", side_effect=[mb]) as mock_cls:
        fetch_threat_feeds(feed_type="malware")
    assert mock_cls.call_count == 1


def test_fetch_threat_feeds_error_returns_message():
    import httpx as real_httpx
    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    client.post.side_effect = real_httpx.RequestError("timeout", request=MagicMock())
    with patch("moon.tools.threat_intel.httpx.Client", return_value=client):
        result = fetch_threat_feeds(feed_type="malware")
    assert "Error" in result


# ---------------------------------------------------------------------------
# tool_registry
# ---------------------------------------------------------------------------

def test_registry_has_fetch_security_news():
    from moon import tool_registry
    assert callable(tool_registry.get_handler("fetch_security_news"))


def test_registry_has_fetch_latest_cves():
    from moon import tool_registry
    assert callable(tool_registry.get_handler("fetch_latest_cves"))


def test_registry_has_fetch_threat_feeds():
    from moon import tool_registry
    assert callable(tool_registry.get_handler("fetch_threat_feeds"))
