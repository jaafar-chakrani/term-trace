from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Optional

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static, Tree
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive

from term_trace.config import Config


class SessionLoader:
    def list_sessions(self, workspace: str) -> List[Path]:
        base = Config.WORKSPACE_DIR / workspace
        return sorted(base.glob("session_*.jsonl"))

    def load_entries(self, session_path: Path) -> List[Dict]:
        entries: List[Dict] = []
        if session_path.exists():
            with session_path.open() as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        continue
        return entries


class LogView(Static):
    """Tree-based log view with collapsible commands and searchable entries."""
    entries: List[Dict] = reactive([])
    filter_text: str = reactive("")

    def compose(self) -> ComposeResult:
        yield Tree("Session Logs", id="logs-tree")

    def on_mount(self) -> None:
        self.refresh_view()

    def set_entries(self, entries: List[Dict]) -> None:
        self.entries = entries
        self.refresh_view()

    def set_filter(self, text: str) -> None:
        self.filter_text = text
        self.refresh_view()

    def refresh_view(self) -> None:
        tree = self.query_one("#logs-tree", Tree)
        tree.clear()
        root = tree.root
        ft = self.filter_text.lower().strip()
        for e in self.entries:
            ts = e.get("timestamp", "?")
            if e.get("type") == "note":
                text = e.get("text", "")
                if ft and ft not in text.lower():
                    continue
                root.add(f"[bold yellow][{ts}] NOTE:[/bold yellow] {text}")
            else:
                cmd = e.get("command", "")
                out = e.get("output", "")
                exit_code = e.get("exit_code", "")
                if ft and (ft not in cmd.lower()) and (ft not in out.lower()):
                    continue
                header = root.add(
                    f"[bold cyan][{ts}] $[/bold cyan] [white]{cmd}[/white]")
                normalized = (out or "(no output)").rstrip()
                lines = normalized.splitlines()
                cleaned_lines = []
                prev_blank = False
                for ln in lines:
                    is_blank = (ln.strip() == "")
                    if is_blank and prev_blank:
                        continue
                    cleaned_lines.append(ln)
                    prev_blank = is_blank
                # Add exit code with color based on actual code value
                try:
                    exit_val = int(exit_code)
                    if exit_val == 0:
                        exit_color = "green"
                    elif exit_val == 1:
                        exit_color = "red"
                    elif exit_val == 2:
                        exit_color = "orange1"
                    elif exit_val >= 126 and exit_val <= 128:
                        exit_color = "magenta"
                    elif exit_val > 128:
                        exit_color = "red"
                    else:
                        exit_color = "yellow"
                except (ValueError, TypeError):
                    exit_color = "red"
                header.add(
                    f"[bold {exit_color}]Exit Code:[/bold {exit_color}] [{exit_color}]{exit_code}[/{exit_color}]")
                output_node = header.add("[bold blue]Output[/bold blue]")
                if cleaned_lines:
                    for line in cleaned_lines:
                        output_node.add(
                            f"[dim]{line if line.strip() else ' '}[/dim]")
                else:
                    output_node.add("[dim italic](no output)[/dim italic]")
        # Expand root to show top-level nodes; children can be toggled by user
        try:
            tree.root.expand()
        except Exception:
            pass


class SessionViewer(App):
    CSS = """
    #log-view {
        height: 1fr;
    }
    .right-pane {
        height: 1fr;
    }
    """

    def __init__(self, workspace: Optional[str] = None, session: Optional[str] = None):
        super().__init__()
        self.workspace = workspace
        self.session = session
        self.loader = SessionLoader()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Vertical(
                Static("Workspaces / Sessions"),
                Tree("Workspaces", id="ws-tree"),
                classes="left-pane",
            ),
            Vertical(
                Input(placeholder="Search logs...", id="search"),
                LogView(id="log-view"),
                classes="right-pane",
            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        tree = self.query_one("#ws-tree", Tree)
        try:
            root = tree.root
            for wdir in sorted([d for d in Config.WORKSPACE_DIR.iterdir() if d.is_dir()]):
                wnode = root.add(wdir.name)
                for session_file in sorted(wdir.glob("session_*.jsonl")):
                    wnode.add(session_file.name, data=session_file)
            tree.expand_all()
        except Exception:
            self.notify("No workspaces found.")

    def _load_session(self, path: Path) -> None:
        entries = self.loader.load_entries(path)
        self.query_one(LogView).set_entries(entries)

    def on_input_changed(self, event: Input.Changed) -> None:
        self.query_one(LogView).set_filter(event.value)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        data = getattr(node, "data", None)
        if isinstance(data, Path):
            self._load_session(data)


def run_viewer(workspace: Optional[str] = None, session: Optional[str] = None) -> None:
    app = SessionViewer(workspace=workspace, session=session)
    app.run()
