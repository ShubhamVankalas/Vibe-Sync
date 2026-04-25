"""
Vibe-Sync Data Management Layer.

Handles ledger compaction, summary deduplication, importance-weighted retrieval,
tool activity tracking, and token budgeting for efficient long-running projects.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import tiktoken

from vibe_sync.utils import logger, safe_execute

VIBE_DIR = Path(".vibe")
LEDGER_FILE = VIBE_DIR / "vibe_ledger.jsonl"
SUMMARY_FILE = VIBE_DIR / "project_summary.md"
FILE_INDEX_PATH = VIBE_DIR / "file_index.json"
TOOL_ACTIVITY_PATH = VIBE_DIR / "tool_activity.jsonl"
COMPACTED_PATH = VIBE_DIR / "compacted_history.jsonl"

# Compaction thresholds
COMPACTION_THRESHOLD = 500
KEEP_RECENT_COUNT = 50

# Token budgeting
DEFAULT_TOKEN_BUDGET = 2000

# tiktoken encoder (cl100k_base is used by GPT-4/Claude-class models)
try:
    _encoder = tiktoken.get_encoding("cl100k_base")
except Exception:
    _encoder = None


def ensure_vibe_dir() -> None:
    """Create the .vibe directory and seed files if they don't exist."""
    VIBE_DIR.mkdir(exist_ok=True)
    if not LEDGER_FILE.exists():
        LEDGER_FILE.touch()
    if not SUMMARY_FILE.exists():
        SUMMARY_FILE.write_text("# Vibe-Sync Project Summary\n\nNo updates recorded yet.\n")
    if not FILE_INDEX_PATH.exists():
        FILE_INDEX_PATH.write_text("{}")
    if not TOOL_ACTIVITY_PATH.exists():
        TOOL_ACTIVITY_PATH.touch()
    if not COMPACTED_PATH.exists():
        COMPACTED_PATH.touch()


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base). Falls back to len/4."""
    if _encoder is not None:
        return len(_encoder.encode(text))
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Ledger operations
# ---------------------------------------------------------------------------

def read_ledger() -> list[dict]:
    """Read all entries from the vibe ledger."""
    ensure_vibe_dir()
    entries: list[dict] = []

    def _read():
        with open(LEDGER_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    try:
                        entries.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        logger.warning("Skipped corrupted ledger line.")

    safe_execute(_read, "Failed to read vibe ledger.")
    return entries


def append_ledger(decision: str, importance: float = 0.5) -> bool:
    """Append a decision to the ledger with timestamp and importance."""
    ensure_vibe_dir()
    entry = {
        "decision": decision,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "importance": round(max(0.0, min(1.0, importance)), 2),
    }

    def _write():
        with open(LEDGER_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    result = safe_execute(_write, "Failed to write decision to ledger.")
    return result is not None


def get_budgeted_vibe(token_budget: int = DEFAULT_TOKEN_BUDGET) -> str:
    """
    Return the most important recent decisions within a token budget.

    Strategy: sort by importance (desc), then fill until budget is exhausted.
    Recent entries (last KEEP_RECENT_COUNT) are always considered first.
    """
    entries = read_ledger()
    compacted = read_compacted_history()

    # Build candidate pool: recent entries + compacted epochs
    recent = entries[-KEEP_RECENT_COUNT:]
    recent_sorted = sorted(recent, key=lambda e: e.get("importance", 0.5), reverse=True)

    lines: list[str] = []
    used_tokens = 0

    # Header
    header = "# Current Project Vibe\n\n"
    used_tokens += count_tokens(header)
    lines.append(header)

    # Add compacted history summary if it exists
    if compacted:
        epoch_header = "## Historical Context\n"
        used_tokens += count_tokens(epoch_header)
        lines.append(epoch_header)
        for epoch in compacted[-3:]:  # Last 3 epochs max
            epoch_line = f"- {epoch.get('summary', 'N/A')}\n"
            cost = count_tokens(epoch_line)
            if used_tokens + cost > token_budget:
                break
            lines.append(epoch_line)
            used_tokens += cost
        lines.append("\n")

    # Add recent decisions
    lines.append("## Recent Decisions\n")
    used_tokens += count_tokens("## Recent Decisions\n")

    for entry in recent_sorted:
        decision = entry.get("decision", "N/A")
        importance = entry.get("importance", 0.5)
        ts = entry.get("timestamp", "unknown")
        # Format timestamp to be more readable
        try:
            dt = datetime.fromisoformat(ts)
            ts_short = dt.strftime("%b %d, %H:%M")
        except (ValueError, TypeError):
            ts_short = ts

        line = f"- [{ts_short}] (importance: {importance}) {decision}\n"
        cost = count_tokens(line)
        if used_tokens + cost > token_budget:
            lines.append(f"\n_({len(recent_sorted) - len(lines) + 3} more entries omitted due to token budget)_\n")
            break
        lines.append(line)
        used_tokens += cost

    return "".join(lines)


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------

def read_compacted_history() -> list[dict]:
    """Read compacted epoch summaries."""
    ensure_vibe_dir()
    epochs: list[dict] = []

    def _read():
        with open(COMPACTED_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    try:
                        epochs.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        pass

    safe_execute(_read, "Failed to read compacted history.")
    return epochs


def compact_ledger() -> dict:
    """
    Compact old ledger entries into epoch summaries.

    Keeps the last KEEP_RECENT_COUNT entries intact and merges older ones
    into weekly epoch summaries appended to compacted_history.jsonl.

    Returns stats about the compaction.
    """
    ensure_vibe_dir()
    entries = read_ledger()

    if len(entries) < COMPACTION_THRESHOLD:
        return {
            "status": "skipped",
            "reason": f"Only {len(entries)} entries (threshold: {COMPACTION_THRESHOLD})",
            "entries_total": len(entries),
        }

    # Split: old entries to compact, recent to keep
    old_entries = entries[:-KEEP_RECENT_COUNT]
    recent_entries = entries[-KEEP_RECENT_COUNT:]

    # Group old entries by week
    weekly_groups: dict[str, list[dict]] = {}
    for entry in old_entries:
        ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            week_key = dt.strftime("Week of %b %d, %Y")
        except (ValueError, TypeError):
            week_key = "Unknown Period"
        weekly_groups.setdefault(week_key, []).append(entry)

    # Create epoch summaries
    new_epochs: list[dict] = []
    for week_key, group in weekly_groups.items():
        decisions = [e.get("decision", "") for e in group]
        avg_importance = sum(e.get("importance", 0.5) for e in group) / len(group)
        summary = f"{week_key}: {'; '.join(decisions[:10])}"
        if len(decisions) > 10:
            summary += f" (and {len(decisions) - 10} more)"
        new_epochs.append({
            "period": week_key,
            "summary": summary,
            "entry_count": len(group),
            "avg_importance": round(avg_importance, 2),
            "compacted_at": datetime.now(timezone.utc).isoformat(),
        })

    # Write compacted epochs
    def _write_epochs():
        with open(COMPACTED_PATH, "a", encoding="utf-8") as fh:
            for epoch in new_epochs:
                fh.write(json.dumps(epoch) + "\n")

    safe_execute(_write_epochs, "Failed to write compacted history.")

    # Rewrite ledger with only recent entries
    def _rewrite_ledger():
        with open(LEDGER_FILE, "w", encoding="utf-8") as fh:
            for entry in recent_entries:
                fh.write(json.dumps(entry) + "\n")

    safe_execute(_rewrite_ledger, "Failed to rewrite ledger after compaction.")

    return {
        "status": "compacted",
        "entries_compacted": len(old_entries),
        "epochs_created": len(new_epochs),
        "entries_remaining": len(recent_entries),
    }


# ---------------------------------------------------------------------------
# File index (summary deduplication)
# ---------------------------------------------------------------------------

def load_file_index() -> dict[str, dict]:
    """Load the per-file summary index."""
    ensure_vibe_dir()
    try:
        with open(FILE_INDEX_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def update_file_index(filename: str, summary: str) -> None:
    """Update the per-file summary index, replacing any previous summary for this file."""
    index = load_file_index()
    index[filename] = {
        "summary": summary,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    def _write():
        with open(FILE_INDEX_PATH, "w", encoding="utf-8") as fh:
            json.dump(index, fh, indent=2)

    safe_execute(_write, f"Failed to update file index for {filename}.")


def regenerate_project_summary() -> None:
    """Regenerate project_summary.md from the file index (deduplicated)."""
    index = load_file_index()
    lines = ["# Vibe-Sync Project Summary\n\n"]
    lines.append(f"_Last regenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n\n")

    for filename, data in sorted(index.items()):
        summary = data.get("summary", "No summary.")
        lines.append(f"### {filename}\n{summary}\n\n")

    def _write():
        with open(SUMMARY_FILE, "w", encoding="utf-8") as fh:
            fh.write("".join(lines))

    safe_execute(_write, "Failed to regenerate project summary.")


# ---------------------------------------------------------------------------
# Tool activity tracking
# ---------------------------------------------------------------------------

TOOL_SIGNATURES = {
    "aider": [".aider.chat.history.md", ".aider.tags.cache.v3"],
    "cursor": [".cursor"],
    "claude_code": [".claude", "CLAUDE.md"],
    "windsurf": [".windsurf"],
    "cline": [".cline"],
    "roo_code": [".roo"],
}


def detect_tool(changed_file: str, recent_changes: Optional[list[str]] = None) -> str:
    """
    Attempt to attribute a file change to an AI coding tool based on
    contextual signals in the recently changed files.
    """
    all_files = [changed_file] + (recent_changes or [])
    combined = " ".join(all_files).lower()

    for tool_name, signatures in TOOL_SIGNATURES.items():
        for sig in signatures:
            if sig.lower() in combined:
                return tool_name

    return "manual_edit"


def log_tool_activity(tool: str, filename: str, action: str = "modified") -> None:
    """Record a tool activity event."""
    ensure_vibe_dir()
    entry = {
        "tool": tool,
        "file": filename,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    def _write():
        with open(TOOL_ACTIVITY_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    safe_execute(_write, "Failed to log tool activity.")


def read_tool_activity() -> list[dict]:
    """Read all tool activity entries."""
    ensure_vibe_dir()
    entries: list[dict] = []

    def _read():
        with open(TOOL_ACTIVITY_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    try:
                        entries.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        pass

    safe_execute(_read, "Failed to read tool activity log.")
    return entries


def get_tool_stats() -> dict[str, dict]:
    """
    Aggregate tool activity into stats: action count and last-seen timestamp per tool.
    """
    entries = read_tool_activity()
    stats: dict[str, dict] = {}

    for entry in entries:
        tool = entry.get("tool", "unknown")
        ts = entry.get("timestamp", "")
        if tool not in stats:
            stats[tool] = {"count": 0, "last_seen": ts}
        stats[tool]["count"] += 1
        if ts > stats[tool]["last_seen"]:
            stats[tool]["last_seen"] = ts

    return stats


def get_context_stats() -> dict:
    """
    Calculate overall context statistics: total decisions, total tokens,
    FAISS vectors (if available), tracked files, compacted epochs.
    """
    ensure_vibe_dir()
    entries = read_ledger()
    file_index = load_file_index()
    compacted = read_compacted_history()

    # Total tokens across all context sources
    all_text = ""
    for e in entries:
        all_text += e.get("decision", "") + " "
    for filename, data in file_index.items():
        all_text += data.get("summary", "") + " "
    for epoch in compacted:
        all_text += epoch.get("summary", "") + " "

    total_tokens = count_tokens(all_text)

    # FAISS vector count
    faiss_count = 0
    faiss_path = VIBE_DIR / "faiss_index.bin"
    if faiss_path.exists():
        try:
            import faiss
            index = faiss.read_index(str(faiss_path))
            faiss_count = index.ntotal
        except Exception:
            faiss_count = -1  # Indicates error reading

    return {
        "total_decisions": len(entries),
        "total_tokens": total_tokens,
        "faiss_vectors": faiss_count,
        "tracked_files": len(file_index),
        "compacted_epochs": len(compacted),
    }
