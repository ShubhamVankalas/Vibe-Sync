"""
Vibe-Sync CLI — A beautiful command-line toolkit for managing your project's vibe.

Commands:
    init     — Configure MCP connections across AI coding tools
    status   — Live dashboard of context stats, tool activity, and vibe rules
    log      — Pretty-print recent decisions from the ledger
    doctor   — Full health diagnostic of your Vibe-Sync setup
    compact  — Manually trigger ledger compaction
"""

import os
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from vibe_sync import __version__
from vibe_sync.utils import console, safe_execute
from vibe_sync.data_manager import (
    compact_ledger,
    ensure_vibe_dir,
    get_context_stats,
    get_tool_stats,
    read_ledger,
)

BANNER = r"""
[bold cyan] ╦  ╦╦╔╗ ╔═╗  ╔═╗╦ ╦╔╗╔╔═╗[/bold cyan]
[bold cyan] ╚╗╔╝║╠╩╗║╣───╚═╗╚╦╝║║║║  [/bold cyan]
[bold cyan]  ╚╝ ╩╚═╝╚═╝  ╚═╝ ╩ ╝╚╝╚═╝[/bold cyan]
[dim]  Unified context for every AI coding tool[/dim]
"""

CONFIG_FILE = "vibe_config.yaml"


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]vibe-sync[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


app = typer.Typer(
    help="Vibe-Sync — Unified context for every AI coding tool.",
    invoke_without_command=True,
    no_args_is_help=True,
)


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit.", callback=version_callback, is_eager=True,
    ),
) -> None:
    """Vibe-Sync CLI — manage your project's shared AI context."""
    pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_vibe_config() -> dict:
    """Load vibe_config.yaml safely."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _show_banner() -> None:
    console.print(BANNER)


def _configure_mcp_json(
    config_path: Path,
    server_name: str,
    command: str,
    args: list[str],
    env: Optional[dict] = None,
) -> bool:
    """Safely updates or creates an MCP JSON configuration file."""
    def _write_config():
        config: dict = {"mcpServers": {}}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
                if content:
                    config = json.loads(content)

        if "mcpServers" not in config:
            config["mcpServers"] = {}

        server_block: dict = {"command": command, "args": args}
        if env:
            server_block["env"] = env

        config["mcpServers"][server_name] = server_block
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=4)
        return True

    result = safe_execute(_write_config, f"Failed to write config to {config_path}")
    if result:
        console.print(f"  [green]✔[/green] Configured [cyan]{server_name}[/cyan] at [dim]{config_path}[/dim]")
        return True
    else:
        console.print(f"  [red]✘[/red] Skipped [cyan]{config_path}[/cyan] — see error above")
        return False


def _format_time_ago(iso_timestamp: str) -> str:
    """Convert an ISO timestamp to a human-readable 'X ago' string."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        else:
            return f"{seconds // 86400}d ago"
    except (ValueError, TypeError):
        return "unknown"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def init() -> None:
    """Configure MCP connections across AI coding tools."""
    _show_banner()
    console.print(Panel.fit(
        "[bold white]Configuration Wizard[/bold white]",
        border_style="cyan",
        subtitle="Step 1 of 2",
    ))

    codebase_str = Prompt.ask("\n[yellow]Enter the absolute path to your codebase[/yellow]")
    if not codebase_str:
        console.print("[red]Path cannot be empty. Exiting.[/red]")
        raise typer.Exit(1)

    codebase_path = Path(codebase_str.strip("\"'"))
    if not codebase_path.exists() or not codebase_path.is_dir():
        console.print("[red]Directory does not exist. Please check the path and try again.[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold green]Codebase:[/bold green] {codebase_path}\n")

    console.print(Panel.fit(
        "[bold white]Detecting AI Tools[/bold white]",
        border_style="cyan",
        subtitle="Step 2 of 2",
    ))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Scanning IDE configurations...", total=None)

        results: list[tuple[str, bool]] = []

        # Cursor
        mcp_path = codebase_path / ".cursor" / "mcp.json"
        results.append(("Cursor", _configure_mcp_json(mcp_path, "vibe-sync", "uv", ["run", "vibe-server"])))

        # Windsurf
        windsurf_path = Path.home() / ".windsurf" / "mcp_config.json"
        results.append(("Windsurf", _configure_mcp_json(windsurf_path, "vibe-sync", "uv", ["run", "vibe-server"])))

        # Claude Desktop (Windows)
        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                claude_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
                results.append(("Claude Desktop", _configure_mcp_json(claude_path, "vibe-sync", "uv", ["run", "vibe-server"])))

    # Summary
    console.print()
    configured = sum(1 for _, ok in results if ok)
    console.print(f"[bold green]{configured}[/bold green] tool(s) configured automatically.\n")

    # Manual instructions
    console.print(Panel(
        "[bold white]For CLI tools (OpenCode, Aider, Roo, Antigravity):[/bold white]\n\n"
        "Add this as the MCP stdio command in their config:\n\n"
        "[bold cyan]uv run vibe-server[/bold cyan]",
        title="[yellow]Manual Setup[/yellow]",
        border_style="yellow",
        expand=False,
    ))

    console.print("\n[bold green]✨ Configuration complete! Vibe-Sync is ready.[/bold green]")
    console.print("[dim]Run [bold]vibe-config status[/bold] to verify your setup.[/dim]\n")


@app.command()
def status() -> None:
    """Show a live dashboard of your project's vibe context."""
    _show_banner()

    vibe_config = _load_vibe_config()
    model = vibe_config.get("system", {}).get("llm_model", "llama3.2:1b")
    vibe_rules = vibe_config.get("vibe_rules", [])

    # Check Ollama status
    ollama_status = "[red]● Offline[/red]"
    try:
        import requests
        api_url = vibe_config.get("system", {}).get("ollama_api_url", "http://localhost:11434/api/generate")
        base_url = api_url.rsplit("/api", 1)[0]
        resp = requests.get(base_url, timeout=3)
        if resp.status_code == 200:
            ollama_status = "[green]● Running[/green]"
    except Exception:
        pass

    # Context stats
    ctx = get_context_stats()
    tool_stats = get_tool_stats()

    # Main info panel
    info_lines = [
        f"[bold]Model:[/bold]   {model}",
        f"[bold]Ollama:[/bold]  {ollama_status}",
    ]
    console.print(Panel("\n".join(info_lines), title="[bold cyan]Vibe-Sync Status[/bold cyan]", border_style="cyan"))

    # Context stats table
    ctx_table = Table(title="Context Statistics", border_style="blue", show_header=True, header_style="bold blue")
    ctx_table.add_column("Metric", style="white")
    ctx_table.add_column("Value", justify="right", style="green")
    ctx_table.add_row("Total Decisions Logged", str(ctx["total_decisions"]))
    ctx_table.add_row("Total Context Tokens", f"~{ctx['total_tokens']:,}")
    ctx_table.add_row("FAISS Vectors Stored", str(ctx["faiss_vectors"]) if ctx["faiss_vectors"] >= 0 else "N/A")
    ctx_table.add_row("Summary Files Tracked", str(ctx["tracked_files"]))
    ctx_table.add_row("Compacted Epochs", str(ctx["compacted_epochs"]))
    console.print(ctx_table)

    # Tool activity table
    if tool_stats:
        tool_table = Table(title="Recent Tool Activity", border_style="magenta", show_header=True, header_style="bold magenta")
        tool_table.add_column("Tool", style="white")
        tool_table.add_column("Last Seen", style="yellow")
        tool_table.add_column("Actions", justify="right", style="green")

        tool_display_names = {
            "cursor": "Cursor",
            "claude_code": "Claude Code",
            "aider": "Aider",
            "windsurf": "Windsurf",
            "cline": "Cline",
            "roo_code": "Roo Code",
            "manual_edit": "Manual Edit",
        }

        for tool, data in sorted(tool_stats.items(), key=lambda x: x[1]["last_seen"], reverse=True):
            display_name = tool_display_names.get(tool, tool.title())
            last_seen = _format_time_ago(data["last_seen"])
            tool_table.add_row(display_name, last_seen, str(data["count"]))

        console.print(tool_table)
    else:
        console.print("[dim]No tool activity recorded yet. Run [bold]vibe-monitor[/bold] to start tracking.[/dim]")

    # Vibe rules
    if vibe_rules:
        rules_text = "\n".join(f"  [cyan]{i+1}.[/cyan] {rule}" for i, rule in enumerate(vibe_rules))
        console.print(Panel(rules_text, title="[bold green]Active Vibe Rules[/bold green]", border_style="green"))
    else:
        console.print("[dim]No vibe rules configured in vibe_config.yaml.[/dim]")

    console.print()


@app.command()
def log(count: int = typer.Option(10, "--count", "-n", help="Number of recent decisions to show.")) -> None:
    """Pretty-print recent decisions from the vibe ledger."""
    _show_banner()
    entries = read_ledger()

    if not entries:
        console.print("[yellow]No decisions logged yet.[/yellow]")
        console.print("[dim]Use your AI tool's log_decision MCP tool, or add entries manually.[/dim]")
        raise typer.Exit()

    table = Table(title=f"Last {min(count, len(entries))} Decisions", border_style="cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Timestamp", style="yellow", width=18)
    table.add_column("Importance", justify="center", width=12)
    table.add_column("Decision", style="white")

    for i, entry in enumerate(entries[-count:], 1):
        ts = entry.get("timestamp", "N/A")
        try:
            dt = datetime.fromisoformat(ts)
            ts_display = dt.strftime("%b %d, %H:%M")
        except (ValueError, TypeError):
            ts_display = str(ts)[:18]

        importance = entry.get("importance", 0.5)
        if importance >= 0.8:
            imp_style = "[bold red]"
        elif importance >= 0.5:
            imp_style = "[yellow]"
        else:
            imp_style = "[dim]"

        table.add_row(
            str(i),
            ts_display,
            f"{imp_style}{importance:.2f}[/]",
            entry.get("decision", "N/A"),
        )

    console.print(table)
    console.print(f"\n[dim]Total entries: {len(entries)}[/dim]\n")


@app.command()
def doctor() -> None:
    """Run a full diagnostic of your Vibe-Sync setup."""
    _show_banner()
    console.print(Panel.fit("[bold white]Running Diagnostics...[/bold white]", border_style="cyan"))
    console.print()

    checks: list[tuple[str, bool, str]] = []

    # 1. Python version
    import sys
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    checks.append(("Python >= 3.10", py_ok, f"v{py_ver}"))

    # 2. vibe_config.yaml exists
    config_exists = os.path.exists(CONFIG_FILE)
    checks.append(("vibe_config.yaml found", config_exists, "Present" if config_exists else "Missing"))

    # 3. Ollama reachable
    ollama_ok = False
    ollama_detail = "Unreachable"
    try:
        import requests
        vibe_config = _load_vibe_config()
        api_url = vibe_config.get("system", {}).get("ollama_api_url", "http://localhost:11434/api/generate")
        base_url = api_url.rsplit("/api", 1)[0]
        resp = requests.get(base_url, timeout=3)
        if resp.status_code == 200:
            ollama_ok = True
            ollama_detail = "Running"
    except Exception:
        pass
    checks.append(("Ollama daemon", ollama_ok, ollama_detail))

    # 4. Model pulled — check via Ollama API instead of CLI
    model_ok = False
    model_detail = "Unknown"
    vibe_config = _load_vibe_config()
    model_name = vibe_config.get("system", {}).get("llm_model", "llama3.2:1b")
    try:
        import requests
        api_url = vibe_config.get("system", {}).get("ollama_api_url", "http://localhost:11434/api/generate")
        tags_url = api_url.rsplit("/api", 1)[0] + "/api/tags"
        resp = requests.get(tags_url, timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            if any(model_name in name for name in model_names):
                model_ok = True
                model_detail = f"{model_name} available"
            else:
                model_detail = f"{model_name} not pulled"
    except Exception:
        model_detail = "Could not check (Ollama offline?)"
    checks.append(("LLM model pulled", model_ok, model_detail))

    # 5. .vibe directory
    vibe_dir_ok = Path(".vibe").exists()
    checks.append((".vibe directory", vibe_dir_ok, "Present" if vibe_dir_ok else "Will be created on first run"))

    # 6. FAISS available
    faiss_ok = False
    try:
        import faiss  # noqa: F401
        faiss_ok = True
    except ImportError:
        pass
    checks.append(("faiss-cpu installed", faiss_ok, "Available" if faiss_ok else "Not installed (optional)"))

    # 7. tiktoken available
    tiktoken_ok = False
    try:
        import tiktoken  # noqa: F401
        tiktoken_ok = True
    except ImportError:
        pass
    checks.append(("tiktoken installed", tiktoken_ok, "Available" if tiktoken_ok else "Missing — token counting degraded"))

    # Render results
    table = Table(title="Diagnostic Results", border_style="cyan")
    table.add_column("Check", style="white")
    table.add_column("Status", justify="center", width=8)
    table.add_column("Detail", style="dim")

    all_passed = True
    for name, passed, detail in checks:
        status_icon = "[green]✔[/green]" if passed else "[red]✘[/red]"
        if not passed:
            all_passed = False
        table.add_row(name, status_icon, detail)

    console.print(table)
    console.print()

    if all_passed:
        console.print("[bold green]All checks passed! Vibe-Sync is healthy.[/bold green]\n")
    else:
        console.print("[bold yellow]Some checks failed. Review the details above.[/bold yellow]")
        console.print("[dim]Run [bold]setup.bat[/bold] to fix common issues automatically.[/dim]\n")


@app.command()
def compact() -> None:
    """Manually trigger ledger compaction to merge old entries into epoch summaries."""
    _show_banner()

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Compacting ledger...", total=None)
        result = compact_ledger()

    if result["status"] == "skipped":
        console.print(f"[yellow]Compaction skipped:[/yellow] {result['reason']}")
    else:
        console.print("[bold green]✔ Compaction complete![/bold green]")
        console.print(f"  Entries compacted: [cyan]{result['entries_compacted']}[/cyan]")
        console.print(f"  Epochs created:    [cyan]{result['epochs_created']}[/cyan]")
        console.print(f"  Entries remaining:  [cyan]{result['entries_remaining']}[/cyan]")

    console.print()


if __name__ == "__main__":
    app()
