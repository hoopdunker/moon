import pytest
import yaml
from pathlib import Path
from moon.catalog import load_catalog, load_guidelines, load_runbooks, load_skills, load_tools


@pytest.fixture
def catalog_dir(tmp_path):
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "guidelines").mkdir()
    return tmp_path


def test_load_runbooks(catalog_dir):
    data = {"id": "rb1", "description": "Test runbook", "tags": ["test"], "steps": ["step one", "step two"]}
    (catalog_dir / "runbooks" / "rb1.yaml").write_text(yaml.dump(data))

    runbooks = load_runbooks(catalog_dir / "runbooks")
    assert len(runbooks) == 1
    assert runbooks[0].id == "rb1"
    assert [s.text for s in runbooks[0].steps] == ["step one", "step two"]
    assert runbooks[0].tags == ["test"]


def test_load_tools(catalog_dir):
    data = {
        "name": "my_tool",
        "description": "A tool",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "mock_response": "mock output",
    }
    (catalog_dir / "tools" / "my_tool.yaml").write_text(yaml.dump(data))

    tools = load_tools(catalog_dir / "tools")
    assert len(tools) == 1
    assert tools[0].name == "my_tool"
    assert tools[0].mock_response == "mock output"


def test_load_skills(catalog_dir):
    (catalog_dir / "skills" / "analyst.md").write_text("You are an analyst.")

    skills = load_skills(catalog_dir / "skills")
    assert len(skills) == 1
    assert skills[0].name == "analyst"
    assert skills[0].content == "You are an analyst."


def test_load_guidelines(catalog_dir):
    (catalog_dir / "guidelines" / "policy.md").write_text("Follow the rules.")

    guidelines = load_guidelines(catalog_dir / "guidelines")
    assert len(guidelines) == 1
    assert guidelines[0].name == "policy"
    assert guidelines[0].content == "Follow the rules."


def test_load_catalog(catalog_dir):
    (catalog_dir / "runbooks" / "rb1.yaml").write_text(
        yaml.dump({"id": "rb1", "description": "d", "tags": [], "steps": ["s"]})
    )
    (catalog_dir / "tools" / "t1.yaml").write_text(
        yaml.dump({"name": "t1", "description": "d", "parameters": {"type": "object"}, "mock_response": "m"})
    )
    (catalog_dir / "skills" / "s1.md").write_text("skill content")
    (catalog_dir / "guidelines" / "g1.md").write_text("guideline content")

    catalog = load_catalog(catalog_dir)
    assert len(catalog.runbooks) == 1
    assert len(catalog.tools) == 1
    assert len(catalog.skills) == 1
    assert len(catalog.guidelines) == 1


def test_load_empty_catalogs(catalog_dir):
    catalog = load_catalog(catalog_dir)
    assert catalog.runbooks == []
    assert catalog.tools == []
    assert catalog.skills == []
    assert catalog.guidelines == []


def test_load_multiple_runbooks(catalog_dir):
    for i in range(3):
        data = {"id": f"rb{i}", "description": f"desc {i}", "tags": [], "steps": [f"step {i}"]}
        (catalog_dir / "runbooks" / f"rb{i}.yaml").write_text(yaml.dump(data))

    runbooks = load_runbooks(catalog_dir / "runbooks")
    assert len(runbooks) == 3
    ids = {r.id for r in runbooks}
    assert ids == {"rb0", "rb1", "rb2"}


def test_skill_name_from_filename(catalog_dir):
    (catalog_dir / "skills" / "code_reviewer.md").write_text("content")
    skills = load_skills(catalog_dir / "skills")
    assert skills[0].name == "code_reviewer"


def test_guideline_name_from_filename(catalog_dir):
    (catalog_dir / "guidelines" / "escalation_policy.md").write_text("content")
    guidelines = load_guidelines(catalog_dir / "guidelines")
    assert guidelines[0].name == "escalation_policy"
