import json
import threading
import time
import os
from pathlib import Path
from typing import Callable, List, Dict, Any, Literal, Optional
from term_trace.summarizer.google_docs import GoogleDocsLogger

SummarizationMode = Literal["markdown", "remote_llm", "custom"]


class JSONLSummarizer:
    """
    Reads a JSONL log file and performs background summarization
    either in batches or deferred.
    Supports multiple summarization modes: Markdown, local LLM, remote LLM, or custom function.
    """

    def __init__(
        self,
        jsonl_file: str,
        summary_file: Optional[str] = None,
        mode: SummarizationMode = "custom",
        llm_function: Optional[Callable[[str], str]] = None,
        batch_size: int = 5,
        interval: int = -1,
        google_client_secret: Optional[str] = None,
        google_folder_id: Optional[str] = None,
        google_doc_title: str = "term-trace session",
        write_to_google_docs: bool = True,
        workspace_name: Optional[str] = None,
    ) -> None:
        """
        :param jsonl_file: Path to JSONL file
        :param summary_file: Path to write summaries (if None, uses jsonl_file with .md extension)
        :param mode: Summarization mode
        :param llm_function: Callable for custom or LLM summarization
        :param batch_size: Number of entries to batch before summarization
        :param interval: Time interval in seconds for periodic summarization. If negative, only summarize when batch_size is reached.
        """
        self.jsonl_file: Path = Path(jsonl_file)
        self.summary_file: Path = Path(
            summary_file) if summary_file else self.jsonl_file.with_suffix('.md')
        self.mode: SummarizationMode = mode
        self.llm_function: Optional[Callable[[str], str]] = llm_function
        self.batch_size: int = batch_size
        self.interval: int = interval
        self.last_pos: int = 0
        self._running: bool = True

        # Create summary file directory if needed
        self.summary_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialize summary file with header (only if it doesn't exist)
        if not self.summary_file.exists():
            with self.summary_file.open('w', encoding='utf-8') as f:
                f.write(f"# {google_doc_title}\n\n")

        # Optionally initialize Google Docs logger
        self.google_logger: Optional[GoogleDocsLogger] = None
        if write_to_google_docs:
            client_path = google_client_secret or os.environ.get(
                "GOOGLE_CLIENT_SECRET")
            if not client_path:
                print(
                    "Warning: GOOGLE_CLIENT_SECRET not set. Google Docs integration disabled.")
                print(
                    "   Set GOOGLE_CLIENT_SECRET environment variable to enable Google Docs logging.")
            else:
                print("Initializing Google Docs Logger...")
                try:
                    self.google_logger = GoogleDocsLogger(
                        client_secret_path=client_path,
                        doc_title=google_doc_title,
                        workspace=workspace_name or "default",
                        folder_id=google_folder_id,
                    )
                except Exception as e:
                    print(
                        f"Warning: Could not initialize Google Docs logger: {e}")
                    print(
                        "   Google Docs integration disabled. Logs will be saved locally only.")
                    self.google_logger = None

        self.thread: threading.Thread = threading.Thread(
            target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop the background summarization thread."""
        self._running = False
        if self.thread.is_alive():
            # Wait up to 5 seconds for clean shutdown
            self.thread.join(timeout=5.0)

    def _run(self) -> None:
        """Background thread that reads new JSONL entries and summarizes them."""
        buffer: List[Dict[str, Any]] = []
        last_batch_time: float = time.time()

        while self._running:
            # Read new entries
            if self.jsonl_file.exists():
                with self.jsonl_file.open() as f:
                    f.seek(self.last_pos)
                    for line in f:
                        buffer.append(json.loads(line))
                    self.last_pos = f.tell()

            # Check if we have enough entries for a batch
            if len(buffer) >= self.batch_size:
                self._summarize_batch(buffer)
                buffer.clear()
                last_batch_time = time.time()
            # Only check time-based summarization if interval is positive
            elif self.interval > 0:
                now: float = time.time()
                if buffer and now - last_batch_time >= self.interval:
                    self._summarize_batch(buffer)
                    buffer.clear()
                    last_batch_time = now

            time.sleep(1)

    def _summarize_batch(self, entries: List[Dict[str, Any]]) -> None:
        """Summarize a batch of entries according to the selected mode."""
        if not entries:
            return

        if self.mode == "markdown":
            # Produce markdown for the batch and a small deterministic summary
            md: str = self._to_markdown(entries)
            total = len(entries)
            notes_count = sum(1 for e in entries if e.get("type") == "note")
            cmd_entries = [e for e in entries if e.get("type") != "note"]
            recent_cmds = [e.get("command", "") for e in cmd_entries][-5:]

            summary_lines: List[str] = [
                f"Session summary: {total} entries ({len(cmd_entries)} commands, {notes_count} notes)."]
            if recent_cmds:
                summary_lines.append("Recent commands:")
                for c in recent_cmds:
                    summary_lines.append(f"- {c}")

            summary: str = "\n".join(summary_lines)
        elif self.mode in ["remote_llm", "custom"]:
            if not self.llm_function:
                return
            text: str = "\n\n".join([
                f"# Note: {e['text']}" if e["type"] == "note"
                else f"Command: {e['command']}\nOutput: {e['output']}\nExit code: {e['exit_code']}"
                for e in entries
            ])
            summary = self.llm_function(text)
        else:
            return

        # Write summary to file
        with self.summary_file.open('a', encoding='utf-8') as f:
            f.write(summary)
            f.write("\n\n")

        # Also write summary and entries to Google Docs if logger available
        if getattr(self, 'google_logger', None):
            try:
                self.google_logger.write_summary(summary)
                self.google_logger.write_entries(entries)
            except Exception as e:
                print(f"Warning: failed to write to Google Docs: {e}")

    def _to_markdown(self, entries: List[Dict[str, Any]]) -> str:
        """Convert a batch of entries to Markdown format."""
        md_lines: List[str] = []
        for e in entries:
            timestamp = e.get("timestamp", "")
            if e["type"] == "note":
                md_lines.append(f"[{timestamp}] **Note:** {e['text']}")
            else:
                md_lines.append(
                    f"[{timestamp}] **Command:** `{e['command']}`\n```\n{e['output']}\n```\nExit code: {e['exit_code']}"
                )
        return "\n\n".join(md_lines)
