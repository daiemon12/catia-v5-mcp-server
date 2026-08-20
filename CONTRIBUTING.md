# Contributing

Thanks for your interest in improving the CATIA V5 MCP Server! Contributions
are very welcome — bug reports, fixes, new tools, documentation. Issues and
PRs may be written in English or Chinese (欢迎使用中文).

## Ground rules for pull requests

1. **Keep PRs small and focused.** One topic per PR (one module, one fix).
   Large multi-topic PRs are effectively unreviewable and will be sent back
   for splitting.
2. **Describe what and how.** Say what the PR does, and how you tested it —
   ideally against a running CATIA V5 instance, since COM behavior varies
   between releases. Mention your CATIA version.
3. **Run the offline test suite** before pushing:
   ```bash
   pip install -e .
   python test_server.py
   ```
   It validates imports, tool schemas, name uniqueness and routing without
   needing CATIA. CI runs the same suite on Windows.
4. **No project-specific files.** Personal smoke scripts, part-specific
   generators or experiment files belong in your fork, not in the shared
   codebase.
5. **Match the existing style.** Tools live in `catia_mcp/tools/<module>.py`
   as a `*Tools` class exposing `get_tools()` (MCP schemas) and
   `handle_tool()` (routing); names are `catia_*`. Look at an existing module
   (e.g. `part_design.py`) and follow the same patterns, including defensive
   `try/except` around COM calls that vary across CATIA releases.

## Reporting bugs

Open an issue with: what you asked the model to do, the tool call and its
error message (from `catia_mcp.log`), plus your CATIA V5 release and Windows
version. A minimal reproduction makes fixes much faster.

## Ideas that are especially welcome

- Drawing / drafting tools (views, dimensions, BOM) — see #6
- A parts-library mechanism for standard components (screws, bearings,
  profiles) — see #6
- `catia_delete_feature` and other feature-management tools — see #2
- More runtime smoke tests against real CATIA instances
