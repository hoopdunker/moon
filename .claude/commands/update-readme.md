Update README.md to reflect the current state of the Moon codebase. Do not ask for confirmation — make the changes directly.

Follow these steps:

1. Read the current README.md in full.

2. Discover the current state of the codebase by reading:
   - `catalogs/runbooks/*.yaml` — every runbook (id, description, tools used, steps)
   - `catalogs/tools/*.yaml` — every tool (name, description, mock vs live status)
   - `catalogs/skills/*.md` — every skill (name, one-line summary of its persona)
   - `catalogs/guidelines/*.md` — every guideline (name, one-line summary)
   - `src/moon/tool_registry.py` — which tools have real implementations registered
   - `src/moon/tools/` — what tool implementation files exist
   - `src/moon/static/index.html` — what tabs/features the web UI has
   - `src/moon/config.py` — configuration variables and their defaults

3. Update README.md so that every section accurately reflects what you found:
   - **Architecture diagram** — update if new components were added (new tool groups, new UI sections, new store backends)
   - **Runbooks table** — one row per runbook; description and tools columns must match the YAML
   - **Tools table** — one row per tool YAML; Status is "Live" if the tool name appears in `_REGISTRY` in tool_registry.py, otherwise "Mock"
   - **Threat Intel sources** — keep the category/source breakdown in sync with `RSS_SOURCES` in `src/moon/tools/threat_intel.py` if that file exists
   - **Skills table** — one row per skill file
   - **Guidelines table** — one row per guideline file
   - **Web UI section** — describe all tabs and their features
   - **Configuration table** — one row per env var in `src/moon/config.py`
   - **Project layout** — keep the file tree in sync with actual files under `src/moon/` and `catalogs/`
   - **Test file list** — update the test filenames under `tests/`

4. Do not remove sections that are still accurate. Do not add invented features. Only reflect what actually exists in the code.

5. Keep the existing README style: concise prose, tables for structured data, ASCII diagram for architecture, fenced code blocks for examples.
