"""
Vibe-Sync MCP Server.

Exposes tools for AI coding agents to read and write project context
via the Model Context Protocol (MCP).

Tools:
    get_current_vibe   — Token-budgeted, importance-weighted context summary
    log_decision       — Record an architectural decision with importance scoring
    get_vibe_rules     — Read the project's coding standards and rules
    search_vibes       — Keyword search across past decisions

Resources:
    vibe://project-summary — Passive project state overview
"""

import os
import json
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from vibe_sync.utils import logger, safe_execute
from vibe_sync.data_manager import (
    append_ledger,
    ensure_vibe_dir,
    get_budgeted_vibe,
    read_ledger,
    SUMMARY_FILE,
)

mcp = FastMCP("Vibe-Sync")

CONFIG_FILE = "vibe_config.yaml"


def _load_vibe_config() -> dict:
    """Load vibe_config.yaml safely."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


@mcp.tool()
def get_current_vibe(token_budget: int = 2000) -> str:
    """
    Returns a token-budgeted, importance-weighted summary of recent
    architectural decisions and the overall project vibe.

    The most important decisions surface first. Older entries that have
    been compacted are included as historical epoch summaries.

    Args:
        token_budget: Maximum number of tokens to include in the response.
                      Defaults to 2000.
    """
    ensure_vibe_dir()
    try:
        return get_budgeted_vibe(token_budget)
    except Exception as e:
        logger.error(f"Failed to build vibe summary: {e}")
        return "Error: Could not retrieve current vibe. Check server logs."


@mcp.tool()
def log_decision(decision: str, importance: float = 0.5) -> str:
    """
    Records a high-level design choice into the local vibe ledger.

    Examples:
        - "Switching from REST to GraphQL for the API layer"
        - "Adopting Tailwind CSS, removing custom stylesheet"
        - "Moving auth to a separate microservice"

    Args:
        decision: A clear description of the architectural or design decision.
        importance: Score from 0.0 (trivial) to 1.0 (critical architectural change).
                    Defaults to 0.5.
    """
    ensure_vibe_dir()
    success = append_ledger(decision, importance)
    if success:
        return f"Decision logged successfully (importance: {importance})."
    return "Failed to log decision due to an I/O error."


@mcp.tool()
def get_vibe_rules() -> str:
    """
    Returns the project's coding standards and rules defined in vibe_config.yaml.

    These rules represent the development team's preferences and should be
    followed when generating or modifying code.
    """
    config = _load_vibe_config()
    rules = config.get("vibe_rules", [])

    if not rules:
        return "No vibe rules configured. Add rules to vibe_config.yaml to set coding standards."

    lines = ["# Project Vibe Rules\n"]
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. {rule}")

    return "\n".join(lines)


@mcp.tool()
def search_vibes(query: str) -> str:
    """
    Search through past decisions in the vibe ledger using keyword matching.

    Args:
        query: The search keyword or phrase to look for in past decisions.
    """
    ensure_vibe_dir()
    entries = read_ledger()
    query_lower = query.lower()

    matches = [
        entry for entry in entries
        if query_lower in entry.get("decision", "").lower()
    ]

    if not matches:
        return f"No decisions found matching '{query}'."

    lines = [f"# Search Results for '{query}' ({len(matches)} found)\n"]
    for entry in matches[-10:]:  # Return last 10 matches
        decision = entry.get("decision", "N/A")
        importance = entry.get("importance", 0.5)
        ts = entry.get("timestamp", "unknown")
        lines.append(f"- [{ts}] (importance: {importance}) {decision}")

    if len(matches) > 10:
        lines.append(f"\n_Showing last 10 of {len(matches)} matches._")

    return "\n".join(lines)


@mcp.resource("vibe://project-summary")
def get_project_summary() -> str:
    """A passive data stream of the project's current generated state overview."""
    ensure_vibe_dir()

    def _read_summary():
        with open(SUMMARY_FILE, "r", encoding="utf-8") as fh:
            return fh.read()

    content = safe_execute(_read_summary, "Failed to load project summary.")
    return content if content else "Summary not available."


def main() -> None:
    logger.info("Starting Vibe-Sync FastMCP Server on stdio...")
    mcp.run()


if __name__ == "__main__":
    main()
