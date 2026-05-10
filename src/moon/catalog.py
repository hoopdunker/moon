from pathlib import Path
import yaml
from moon import config
from moon.models import Catalog, Guideline, Runbook, Skill, Tool


def load_runbooks(path: Path) -> list[Runbook]:
    return [Runbook(**yaml.safe_load(f.read_text())) for f in sorted(path.glob("*.yaml"))]


def load_tools(path: Path) -> list[Tool]:
    return [Tool(**yaml.safe_load(f.read_text())) for f in sorted(path.glob("*.yaml"))]


def load_skills(path: Path) -> list[Skill]:
    return [Skill(name=f.stem, content=f.read_text()) for f in sorted(path.glob("*.md"))]


def load_guidelines(path: Path) -> list[Guideline]:
    return [Guideline(name=f.stem, content=f.read_text()) for f in sorted(path.glob("*.md"))]


def load_catalog(catalogs_path: Path | None = None) -> Catalog:
    base = catalogs_path or config.CATALOGS_PATH
    return Catalog(
        runbooks=load_runbooks(base / "runbooks"),
        tools=load_tools(base / "tools"),
        skills=load_skills(base / "skills"),
        guidelines=load_guidelines(base / "guidelines"),
    )
