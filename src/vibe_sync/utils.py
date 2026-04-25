"""
Vibe-Sync shared utilities.

Provides centralized logging, error handling, and a pre-configured
Rich console instance for consistent terminal output.
"""

import os
import sys
import logging
from rich.console import Console
from rich.logging import RichHandler

# Force UTF-8 on Windows so Rich can render Unicode safely
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

# Global rich console — force_terminal enables color even in piped output
console = Console(force_terminal=True)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Set up rich logging configuration."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console, markup=True)],
    )
    return logging.getLogger("vibe-sync")


logger = setup_logging()


def safe_execute(func, error_msg: str, exit_on_fail: bool = False):
    """
    Safely execute a function, catching exceptions and printing human-readable
    errors using Rich instead of raw Python tracebacks.

    Args:
        func: A zero-argument callable to execute.
        error_msg: A user-friendly message to display on failure.
        exit_on_fail: If True, terminate the process on failure.

    Returns:
        The return value of func(), or None if an exception occurred.
    """
    try:
        return func()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {error_msg}")
        console.print(f"[red]Details: {e!s}[/red]")
        if exit_on_fail:
            sys.exit(1)
        return None
