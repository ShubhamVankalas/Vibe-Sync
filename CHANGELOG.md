# Changelog

All notable changes to Vibe-Sync will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-26

### Added
- **Smart Data Management Layer** (`data_manager.py`):
  - Importance-weighted decision retrieval with token budgeting via `tiktoken`
  - Ledger compaction: old entries merge into weekly epoch summaries
  - File summary deduplication via `file_index.json`
  - Per-tool activity tracking and attribution
- **CLI Dashboard** (`vibe-config status`):
  - Live context stats (total decisions, tokens, FAISS vectors, tracked files)
  - Recent tool activity table (which AI tool, last seen, action count)
  - Active vibe rules display
- **CLI Commands**: `status`, `log`, `doctor`, `compact`, `--version`
- **MCP Tools**: `get_vibe_rules`, `search_vibes`
- ASCII art banner for all CLI commands
- `CONTRIBUTING.md`, `CHANGELOG.md`, GitHub issue/PR templates
- `tiktoken` for precise token counting
- Ruff linter configuration

### Changed
- `get_current_vibe` now returns importance-weighted results within a token budget
- `log_decision` now accepts an `importance` parameter (0.0–1.0)
- Monitor now attributes file changes to specific AI tools
- Monitor uses file deduplication instead of blind appending
- Expanded file ignore list (binary files, build artifacts)

## [0.2.0] - 2026-04-25

### Added
- Restructured into `src/vibe_sync/` Python package
- Rich + Typer for beautiful CLI output
- Centralized error handling via `safe_execute()` — no raw tracebacks

## [0.1.0] - 2026-04-25

### Added
- Initial release with `config_manager.py`, `vibe_server.py`, `vibe_monitor.py`
- MCP tools: `get_current_vibe`, `log_decision`
- MCP resource: `vibe://project-summary`
- `setup.bat` one-click Windows installer
- Support for Cursor, Windsurf, Claude Desktop
