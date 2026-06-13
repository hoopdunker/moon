"""Tests for Bedrock model registry and resolution logic."""
from moon import config
from moon.models import ResourceSelection


# ── config.resolve_model ──────────────────────────────────────────────────────

def test_resolve_model_claude_haiku():
    assert config.resolve_model("claude-haiku") == "us.anthropic.claude-3-5-haiku-20241022-v1:0"


def test_resolve_model_claude_sonnet():
    assert config.resolve_model("claude-sonnet") == "us.anthropic.claude-3-5-sonnet-20241022-v2:0"


def test_resolve_model_claude_opus():
    assert config.resolve_model("claude-opus") == "us.anthropic.claude-3-opus-20240229-v1:0"


def test_resolve_model_nova_micro():
    assert config.resolve_model("nova-micro") == "amazon.nova-micro-v1:0"


def test_resolve_model_nova_lite():
    assert config.resolve_model("nova-lite") == "amazon.nova-lite-v1:0"


def test_resolve_model_nova_pro():
    assert config.resolve_model("nova-pro") == "amazon.nova-pro-v1:0"


def test_resolve_model_unknown_falls_back_to_agent_model():
    assert config.resolve_model("unknown-xyz") == config.AGENT_MODEL


def test_model_registry_all_entries_have_required_fields():
    for name, info in config.MODEL_REGISTRY.items():
        assert "bedrock_id" in info, f"{name} missing bedrock_id"
        assert "use_for" in info, f"{name} missing use_for"


def test_model_registry_claude_models_have_anthropic_prefix():
    for name, info in config.MODEL_REGISTRY.items():
        if name.startswith("claude"):
            assert "anthropic." in info["bedrock_id"], f"{name} should contain anthropic. in bedrock_id"


def test_model_registry_nova_models_have_amazon_prefix():
    for name, info in config.MODEL_REGISTRY.items():
        if name.startswith("nova"):
            assert info["bedrock_id"].startswith("amazon."), f"{name} should have amazon. prefix"


# ── ResourceSelection.agent_model ────────────────────────────────────────────

def test_resource_selection_default_agent_model():
    rs = ResourceSelection(tool_names=[], skill_names=[], guideline_names=[])
    assert rs.agent_model == "sonnet"


def test_resource_selection_explicit_nova_model():
    rs = ResourceSelection(tool_names=[], skill_names=[], guideline_names=[], agent_model="nova-pro")
    assert rs.agent_model == "nova-pro"


def test_resource_selection_explicit_claude_model():
    rs = ResourceSelection(tool_names=[], skill_names=[], guideline_names=[], agent_model="claude-opus")
    assert rs.agent_model == "claude-opus"
