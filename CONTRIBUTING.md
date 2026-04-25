# Contributing to Vibe-Sync

Thanks for your interest in contributing to Vibe-Sync! This document provides guidelines and instructions for contributing.

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ShubhamVankalas/Vibe-Sync.git
   cd Vibe-Sync
   ```

2. **Install dependencies with dev extras:**
   ```bash
   uv sync --extra dev
   ```

3. **Verify your setup:**
   ```bash
   uv run vibe-config doctor
   ```

## Code Style

- We use **Ruff** for linting. Run before committing:
  ```bash
  uv run ruff check src/
  ```
- Follow PEP 8 conventions
- Use type hints on all public functions
- Write docstrings for all modules, classes, and public functions

## Project Structure

```
src/vibe_sync/
├── __init__.py       # Package version
├── cli.py            # Typer CLI commands (init, status, log, doctor, compact)
├── server.py         # FastMCP server (tools + resources for AI agents)
├── monitor.py        # Watchdog file monitor + Ollama summarizer
├── data_manager.py   # Smart data layer (compaction, dedup, token budgeting)
└── utils.py          # Shared logging and error handling
```

## Making Changes

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes** following the code style guidelines above

3. **Test your changes** manually:
   ```bash
   uv run vibe-config doctor
   uv run vibe-config status
   ```

4. **Submit a Pull Request** with a clear description of what changed and why

## Reporting Bugs

Please use the [GitHub Issues](https://github.com/ShubhamVankalas/Vibe-Sync/issues) page and include:
- Your Python version (`python --version`)
- Your OS and version
- Steps to reproduce
- Expected vs actual behavior

## Feature Requests

We welcome ideas! Open an issue with the `feature-request` label and describe:
- What problem the feature solves
- How you envision it working
- Any alternatives you've considered

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
