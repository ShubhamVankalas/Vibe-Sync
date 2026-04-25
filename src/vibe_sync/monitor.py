"""
Vibe-Sync Background Monitor.

Watches the codebase for file changes using watchdog, attributes changes
to specific AI tools when possible, generates token-dense summaries via
a local Ollama model, and maintains a deduplicated file summary index.
"""

import os
import time

import requests
import yaml
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from vibe_sync.utils import logger, safe_execute
from vibe_sync.data_manager import (
    detect_tool,
    ensure_vibe_dir,
    log_tool_activity,
    update_file_index,
    regenerate_project_summary,
    VIBE_DIR,
)

try:
    import faiss
    import numpy as np

    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("faiss-cpu not available. Vector storage disabled.")

CONFIG_FILE = "vibe_config.yaml"


def load_config() -> dict:
    """Load vibe_config.yaml safely."""
    def _read():
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh)
        return {}

    result = safe_execute(_read, "Failed to read vibe_config.yaml.")
    return result if result else {}


config = load_config()
OLLAMA_API_URL = config.get("system", {}).get("ollama_api_url", "http://localhost:11434/api/generate")
LLM_MODEL = config.get("system", {}).get("llm_model", "llama3.2:1b")


class VectorStore:
    """Simple FAISS-backed vector storage for file summaries."""

    def __init__(self, index_path: Path, dim: int = 384):
        self.index_path = index_path
        self.index = None
        if FAISS_AVAILABLE:
            def _init():
                if os.path.exists(index_path):
                    self.index = faiss.read_index(str(index_path))
                else:
                    self.index = faiss.IndexFlatL2(dim)

            safe_execute(_init, f"Failed to initialize vector store at {index_path}")

    def add_vector(self, vector) -> None:
        if FAISS_AVAILABLE and self.index is not None:
            def _add():
                self.index.add(np.array([vector], dtype=np.float32))
                VIBE_DIR.mkdir(exist_ok=True)
                faiss.write_index(self.index, str(self.index_path))

            safe_execute(_add, "Failed to add vector to FAISS database.")


vector_store = VectorStore(VIBE_DIR / "faiss_index.bin")


def summarize_with_ollama(content: str, filename: str) -> str:
    """
    Send file content to the local Ollama instance for a concise,
    token-dense summary focused on architectural significance.
    """
    prompt = (
        "You are a code change summarizer. Summarize the following file content "
        "in 2-3 sentences. Focus on the architectural purpose and any design "
        "decisions visible in the code. Be concise and token-dense.\n\n"
        f"File: {filename}\n\n{content[:3000]}"
    )

    payload = {"model": LLM_MODEL, "prompt": prompt, "stream": False}

    def _call():
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            logger.error(f"Ollama returned HTTP {response.status_code}")
            return "Summary unavailable."

    result = safe_execute(_call, "Failed to connect to Ollama. Is it running?")
    return result if result else "Summary unavailable."


class VibeCodebaseHandler(FileSystemEventHandler):
    """Filesystem event handler that summarizes changes and attributes tools."""

    IGNORE_DIRS = {
        ".git", ".vibe", ".venv", "venv", "node_modules",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "dist", "build", ".eggs",
    }
    IGNORE_EXTENSIONS = {
        ".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
        ".woff", ".woff2", ".ttf", ".eot",
        ".zip", ".tar", ".gz", ".bz2",
        ".lock", ".bin",
    }

    def __init__(self):
        super().__init__()
        self._recent_changes: list[str] = []

    def _should_ignore(self, path: str) -> bool:
        path_obj = Path(path)
        # Check directory components
        for part in path_obj.parts:
            if part in self.IGNORE_DIRS:
                return True
        # Check extension
        if path_obj.suffix.lower() in self.IGNORE_EXTENSIONS:
            return True
        return False

    def on_modified(self, event) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return

        # Debounce: wait for writes to settle
        time.sleep(0.5)

        try:
            self._process_file(event.src_path)
        except UnicodeDecodeError:
            pass  # Skip binary files silently
        except Exception as e:
            logger.error(f"Error processing {Path(event.src_path).name}: {e}")

    def _process_file(self, file_path: str) -> None:
        """Read, summarize, deduplicate, and attribute a modified file."""
        with open(file_path, "r", encoding="utf-8") as fh:
            content = fh.read()

        filename = Path(file_path).name

        # Tool attribution
        self._recent_changes.append(file_path)
        if len(self._recent_changes) > 20:
            self._recent_changes = self._recent_changes[-20:]

        tool = detect_tool(file_path, self._recent_changes)
        tool_label = tool.replace("_", " ").title()
        logger.info(f"[cyan]{filename}[/cyan] modified (attributed to [magenta]{tool_label}[/magenta]). Summarizing...")

        # Log tool activity
        log_tool_activity(tool, filename)

        # Summarize via Ollama
        summary = summarize_with_ollama(content, filename)

        # Deduplicated update: replaces any previous summary for this file
        update_file_index(filename, summary)

        # Regenerate the unified project summary from the deduplicated index
        regenerate_project_summary()

        logger.info(f"[green]✔[/green] {filename} → context updated")


def main() -> None:
    """Entry point for the background monitor daemon."""
    ensure_vibe_dir()
    logger.info(
        f"Starting Vibe-Sync Monitor "
        f"[green](Model: {LLM_MODEL})[/green] "
        f"[dim](watching current directory recursively)[/dim]"
    )

    handler = VibeCodebaseHandler()
    observer = Observer()
    observer.schedule(handler, path=".", recursive=True)

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down monitor...")
        observer.stop()
    observer.join()
    logger.info("Monitor stopped.")


if __name__ == "__main__":
    main()
