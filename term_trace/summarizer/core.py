import json
import threading
import time
import os
import logging
from pathlib import Path
from typing import Callable, List, Dict, Any, Literal, Optional
from term_trace.summarizer.google_docs import GoogleDocsLogger

# Set up logger for background thread
logger = logging.getLogger(__name__)

SummarizationMode = Literal["markdown",
                            "openai", "huggingface", "github", "custom"]


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
        self._full_log_heading_written: bool = False

        # Create summary file directory if needed
        self.summary_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialize summary file with header (only if it doesn't exist)
        if not self.summary_file.exists():
            with self.summary_file.open('w', encoding='utf-8') as f:
                f.write(f"# {google_doc_title}\n\n")
        else:
            # File exists, check if it already has Full Log section
            with self.summary_file.open('r', encoding='utf-8') as f:
                content = f.read()
                if '## Full Log' in content:
                    self._full_log_heading_written = True

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
        """Background thread that reads new JSONL entries and logs them immediately."""
        buffer: List[Dict[str, Any]] = []
        last_batch_time: float = time.time()
        new_entries_for_logging: List[Dict[str, Any]] = []

        while self._running:
            # Read new entries
            if self.jsonl_file.exists():
                with self.jsonl_file.open() as f:
                    f.seek(self.last_pos)
                    for line in f:
                        entry = json.loads(line)
                        # Check for summarize trigger
                        if entry.get("type") == "summarize":
                            print(
                                f"\n[term-trace] Received summarization request")
                            logger.info(
                                "Received summarization request, processing buffered entries...")
                            if buffer:
                                logger.info(
                                    f"Summarizing {len(buffer)} entries")
                                self._summarize_batch(buffer)
                                buffer.clear()
                                last_batch_time = time.time()
                            else:
                                print(
                                    f"[term-trace] No entries in buffer to summarize")
                                logger.info(
                                    "No entries in buffer to summarize")
                            continue
                        # Always add to new entries for immediate logging
                        new_entries_for_logging.append(entry)
                        # Also add to buffer for summarization (if enabled)
                        buffer.append(entry)
                    self.last_pos = f.tell()

            # Write new entries to full log immediately (Google Docs and markdown)
            if new_entries_for_logging:
                self._log_entries_to_full_log(new_entries_for_logging)
                new_entries_for_logging.clear()

            # Check if we should run summarization
            should_summarize = False
            if self.batch_size > 0 and len(buffer) >= self.batch_size:
                should_summarize = True
            elif self.interval > 0:
                now: float = time.time()
                if buffer and now - last_batch_time >= self.interval:
                    should_summarize = True

            if should_summarize:
                self._summarize_batch(buffer)
                buffer.clear()
                last_batch_time = time.time()

            time.sleep(1)

    def _log_entries_to_full_log(self, entries: List[Dict[str, Any]]) -> None:
        """Write entries to full log (Google Docs and markdown) immediately."""
        if not entries:
            return

        # Write to markdown full log
        md: str = self._to_markdown(entries)
        with self.summary_file.open('a', encoding='utf-8') as f:
            # Only write the heading once
            if not self._full_log_heading_written:
                f.write("## Full Log\n\n")
                self._full_log_heading_written = True
            f.write(md)
            f.write("\n\n")

        # Write to Google Docs full log
        if getattr(self, 'google_logger', None):
            try:
                self.google_logger.write_entries(entries)
            except Exception as e:
                print(f"Warning: failed to write entries to Google Docs: {e}")

    def _summarize_batch(self, entries: List[Dict[str, Any]]) -> None:
        """Summarize a batch of entries according to the selected mode."""
        if not entries:
            logger.warning("_summarize_batch called with empty entries")
            return

        logger.info(f"Generating summary in mode: {self.mode}")

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
        logger.info(f"Writing summary to file: {self.summary_file}")
        logger.debug(f"Summary content: {summary[:200]}...")
        try:
            with self.summary_file.open('a', encoding='utf-8') as f:
                f.write("## Summary\n\n")
                f.write(summary)
                f.write("\n\n")
            logger.info("Summary successfully written")
        except Exception as e:
            logger.error(f"ERROR writing summary: {e}", exc_info=True)

        # Also write summary to Google Docs if logger available
        if getattr(self, 'google_logger', None):
            try:
                self.google_logger.write_summary(summary)
            except Exception as e:
                print(f"Warning: failed to write summary to Google Docs: {e}")

    def _to_markdown(self, entries: List[Dict[str, Any]]) -> str:
        """Convert a batch of entries to Markdown format (terminal-style)."""
        md_lines: List[str] = []
        for e in entries:
            timestamp = e.get("timestamp", "")
            # Format timestamp like Google Docs does
            ts_formatted = self._format_timestamp_for_markdown(timestamp)

            if e.get("type") == "note":
                # Format: [timestamp] NOTE: text
                md_lines.append(f"[{ts_formatted}] **NOTE:** {e['text']}")
            else:
                # Format: shell block for command, console block for output
                cmd = e.get('command', '')
                output = e.get('output', '').rstrip()
                exit_code = e.get('exit_code', 0)

                parts = []

                # Command in shell block
                shell_block = f"```shell\n[{ts_formatted}] $ {cmd}\n```"
                parts.append(shell_block)

                # Output in console block (if present)
                if output or exit_code != 0:
                    console_parts = []
                    if output:
                        console_parts.append(output)
                    if exit_code != 0:
                        console_parts.append(f"[Exit code: {exit_code}]")

                    console_block = "```console\n" + \
                        '\n'.join(console_parts) + "\n```"
                    parts.append(console_block)

                md_lines.append('\n'.join(parts))

        return "\n\n".join(md_lines)

    def _format_timestamp_for_markdown(self, ts_str: str) -> str:
        """Format timestamp for markdown (same as Google Docs format)."""
        try:
            from datetime import datetime
            # Parse ISO format timestamp (assumed to be UTC)
            dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            # Convert to local timezone
            local_dt = dt.astimezone()
            # Format as: Nov 28, 16:45:30
            return local_dt.strftime("%b %d, %H:%M:%S")
        except Exception:
            return ts_str
