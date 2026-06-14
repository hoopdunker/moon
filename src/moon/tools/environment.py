from pathlib import Path

import yaml

from moon import config


def get_environment_profile(catalogs_path: Path | None = None) -> str:
    path = (catalogs_path or config.CATALOGS_PATH) / "environment.yaml"
    if not path.exists():
        return (
            "No environment profile found. Create catalogs/environment.yaml to enable "
            "targeted recommendations based on your controls, log sources, and asset inventory."
        )

    raw = yaml.safe_load(path.read_text())
    if not raw:
        return "No environment profile configured. Produce a generic threat intelligence brief without org-specific asset mapping or control gap analysis."

    sections: list[str] = []

    if org := raw.get("org"):
        meta = [f"Org: {org}"]
        if industry := raw.get("industry"):
            meta.append(f"Industry: {industry}")
        if count := raw.get("employee_count"):
            meta.append(f"Size: ~{count} employees")
        sections.append(" | ".join(meta))

    if controls := raw.get("controls"):
        lines = ["=== Security Controls ==="]
        for category, items in controls.items():
            if category == "gaps":
                continue
            label = category.replace("_", " ").title()
            for item in items or []:
                name = item.get("name", "")
                coverage = item.get("coverage", "")
                line = f"  [{label}] {name}"
                if coverage:
                    line += f" — {coverage}"
                lines.append(line)
        if gaps := controls.get("gaps"):
            lines.append("  [Gaps]")
            for g in gaps:
                lines.append(f"    - {g}")
        sections.append("\n".join(lines))

    if logs := raw.get("log_sources"):
        lines = ["=== Log Sources ==="]
        for log in logs:
            lines.append(f"  - {log}")
        sections.append("\n".join(lines))

    if assets := raw.get("assets"):
        lines = ["=== Asset Inventory ==="]
        if cloud := assets.get("cloud"):
            provider = cloud.get("provider", "")
            regions = ", ".join(cloud.get("regions", []))
            services = ", ".join(cloud.get("primary_services", []))
            lines.append(f"  Cloud: {provider} ({regions})")
            if services:
                lines.append(f"    Services: {services}")
        if on_prem := assets.get("on_prem"):
            lines.append(f"  On-prem: {on_prem}")
        if critical := assets.get("critical_systems"):
            lines.append("  Critical systems:")
            for s in critical:
                note = f" [{s['notes']}]" if s.get("notes") else ""
                lines.append(f"    - {s['name']}{note}")
        if surface := assets.get("public_attack_surface"):
            lines.append("  Public attack surface:")
            for s in surface:
                lines.append(f"    - {s}")
        sections.append("\n".join(lines))

    if compliance := raw.get("compliance"):
        sections.append("=== Compliance ===\n  " + ", ".join(compliance))

    if slas := raw.get("patch_slas"):
        lines = ["=== Patch SLAs ==="]
        for severity, sla in slas.items():
            lines.append(f"  {severity.title()}: {sla}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
