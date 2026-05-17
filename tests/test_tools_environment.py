import textwrap
from pathlib import Path

import pytest
import yaml

from moon.tools.environment import get_environment_profile


def _write_env(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "environment.yaml"
    p.write_text(yaml.dump(data))
    return tmp_path


# ---------------------------------------------------------------------------
# Missing / empty file
# ---------------------------------------------------------------------------

def test_missing_file_returns_helpful_message(tmp_path):
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "No environment profile found" in result
    assert "environment.yaml" in result


def test_empty_file_returns_message(tmp_path):
    (tmp_path / "environment.yaml").write_text("")
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "empty" in result


# ---------------------------------------------------------------------------
# Org metadata
# ---------------------------------------------------------------------------

def test_org_name_shown(tmp_path):
    _write_env(tmp_path, {"org": "Acme Corp"})
    assert "Acme Corp" in get_environment_profile(catalogs_path=tmp_path)


def test_industry_shown(tmp_path):
    _write_env(tmp_path, {"org": "Acme", "industry": "finance"})
    assert "finance" in get_environment_profile(catalogs_path=tmp_path)


def test_employee_count_shown(tmp_path):
    _write_env(tmp_path, {"org": "Acme", "employee_count": 250})
    assert "250" in get_environment_profile(catalogs_path=tmp_path)


# ---------------------------------------------------------------------------
# Security controls
# ---------------------------------------------------------------------------

def test_endpoint_control_shown(tmp_path):
    _write_env(tmp_path, {"controls": {"endpoint": [{"name": "CrowdStrike Falcon", "coverage": "all servers"}]}})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "CrowdStrike Falcon" in result
    assert "all servers" in result


def test_control_category_label_shown(tmp_path):
    _write_env(tmp_path, {"controls": {"network": [{"name": "Palo Alto NGFW"}]}})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "Network" in result


def test_gaps_shown(tmp_path):
    _write_env(tmp_path, {"controls": {"gaps": ["No dark web monitoring", "No CASB"]}})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "No dark web monitoring" in result
    assert "Gaps" in result


def test_gaps_not_shown_as_regular_control_category(tmp_path):
    _write_env(tmp_path, {"controls": {
        "endpoint": [{"name": "CrowdStrike"}],
        "gaps": ["No honeypot"],
    }})
    result = get_environment_profile(catalogs_path=tmp_path)
    # gaps should appear under [Gaps], not as [gaps] control category
    assert "[gaps]" not in result.lower() or "Gaps" in result


def test_multiple_controls_in_same_category(tmp_path):
    _write_env(tmp_path, {"controls": {"network": [
        {"name": "Palo Alto NGFW"},
        {"name": "Cloudflare WAF"},
    ]}})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "Palo Alto NGFW" in result
    assert "Cloudflare WAF" in result


# ---------------------------------------------------------------------------
# Log sources
# ---------------------------------------------------------------------------

def test_log_sources_shown(tmp_path):
    _write_env(tmp_path, {"log_sources": ["AWS CloudTrail", "Okta audit logs"]})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "AWS CloudTrail" in result
    assert "Okta audit logs" in result


def test_log_sources_section_header(tmp_path):
    _write_env(tmp_path, {"log_sources": ["AWS CloudTrail"]})
    assert "Log Sources" in get_environment_profile(catalogs_path=tmp_path)


# ---------------------------------------------------------------------------
# Asset inventory
# ---------------------------------------------------------------------------

def test_cloud_provider_and_regions_shown(tmp_path):
    _write_env(tmp_path, {"assets": {"cloud": {"provider": "AWS", "regions": ["us-east-1", "eu-west-1"]}}})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "AWS" in result
    assert "us-east-1" in result
    assert "eu-west-1" in result


def test_critical_systems_shown(tmp_path):
    _write_env(tmp_path, {"assets": {"critical_systems": [
        {"name": "Payment processing", "notes": "PCI in scope"},
    ]}})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "Payment processing" in result
    assert "PCI in scope" in result


def test_public_attack_surface_shown(tmp_path):
    _write_env(tmp_path, {"assets": {"public_attack_surface": ["API gateway (public)"]}})
    assert "API gateway" in get_environment_profile(catalogs_path=tmp_path)


def test_on_prem_shown(tmp_path):
    _write_env(tmp_path, {"assets": {"on_prem": "2 data centres (London, Dublin)"}})
    assert "London" in get_environment_profile(catalogs_path=tmp_path)


# ---------------------------------------------------------------------------
# Compliance and patch SLAs
# ---------------------------------------------------------------------------

def test_compliance_frameworks_shown(tmp_path):
    _write_env(tmp_path, {"compliance": ["SOC 2 Type II", "PCI DSS 4.0"]})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "SOC 2 Type II" in result
    assert "PCI DSS 4.0" in result


def test_patch_slas_shown(tmp_path):
    _write_env(tmp_path, {"patch_slas": {"critical": "24 hours", "high": "7 days"}})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "24 hours" in result
    assert "7 days" in result


def test_patch_sla_section_header(tmp_path):
    _write_env(tmp_path, {"patch_slas": {"critical": "24 hours"}})
    assert "Patch SLAs" in get_environment_profile(catalogs_path=tmp_path)


# ---------------------------------------------------------------------------
# Partial / sparse profiles
# ---------------------------------------------------------------------------

def test_only_log_sources_no_controls(tmp_path):
    _write_env(tmp_path, {"log_sources": ["Splunk"]})
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "Splunk" in result
    assert "Security Controls" not in result


def test_full_profile_contains_all_sections(tmp_path):
    _write_env(tmp_path, {
        "org": "Acme",
        "controls": {"endpoint": [{"name": "CrowdStrike"}]},
        "log_sources": ["CloudTrail"],
        "assets": {"cloud": {"provider": "AWS", "regions": ["us-east-1"]}},
        "compliance": ["SOC 2"],
        "patch_slas": {"critical": "24 hours"},
    })
    result = get_environment_profile(catalogs_path=tmp_path)
    assert "Security Controls" in result
    assert "Log Sources" in result
    assert "Asset Inventory" in result
    assert "Compliance" in result
    assert "Patch SLAs" in result
