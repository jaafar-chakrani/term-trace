from __future__ import annotations
from pathlib import Path
from typing import List
import json
from term_trace.config import Config

BASE_DIR: Path = Config.WORKSPACE_DIR


def create_workspace(name: str) -> Path:
    """
    Create a new workspace directory with metadata file.

    Args:
        name (str): Workspace name.

    Returns:
        Path: Path to the created workspace directory.
    """
    ws_dir = BASE_DIR / name
    ws_dir.mkdir(parents=True, exist_ok=True)

    meta_file = ws_dir / "meta.json"
    if not meta_file.exists():
        meta = {"name": name, "sessions": []}
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return ws_dir


def list_workspaces() -> List[str]:
    """
    List all existing workspaces.

    Returns:
        List[str]: Names of all workspaces.
    """
    if not BASE_DIR.exists():
        return []
    return [p.name for p in BASE_DIR.iterdir() if p.is_dir()]


def add_session(workspace: str, session_file: Path) -> None:
    """
    Add a session log file to a workspace's metadata.

    Args:
        workspace (str): Workspace name.
        session_file (Path): Path to the session JSONL file.

    Raises:
        FileNotFoundError: If the workspace or meta.json does not exist.
    """
    ws_dir = BASE_DIR / workspace
    meta_path = ws_dir / "meta.json"

    if not meta_path.exists():
        raise FileNotFoundError(f"Workspace '{workspace}' not found.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if str(session_file) not in meta["sessions"]:
        meta["sessions"].append(str(session_file))
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
