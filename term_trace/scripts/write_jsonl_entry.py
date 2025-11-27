
#!/usr/bin/env python3
import sys
import json
from pathlib import Path
from typing import Any


import re


def strip_ansi_sequences(text: str) -> str:
    # Remove ANSI escape/control sequences (including OSC, CSI, etc.)
    # OSC: \x1b]...\x07 or \x1b]...\x1b\\
    # CSI: \x1b[...letter
    # Also aggressively remove \x1b]7;... (window position)
    osc_pattern = re.compile(r"\x1B\][0-9]*;[^\x07\x1B]*[\x07\x1B\\]?")
    csi_pattern = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")
    # Remove OSC sequences
    text = osc_pattern.sub("", text)
    # Remove CSI sequences
    text = csi_pattern.sub("", text)
    # Remove any remaining ESC followed by non-printable
    text = re.sub(r"\x1B[^\w]", "", text)
    # Remove trailing backslash left by OSC sequence removal
    return text.rstrip("\\")


def create_note_entry(timestamp: str, command: str) -> dict[str, Any]:
    """Create a note entry from a command starting with #."""
    # Remove the # and any following whitespace
    note_text = command[1:].lstrip()
    return {
        "type": "note",
        "timestamp": timestamp,
        "text": note_text
    }


def create_command_entry(timestamp: str, command: str, output: str, exit_code: int) -> dict[str, Any]:
    """Create a command entry with cleaned output."""
    clean_output = strip_ansi_sequences(output)
    return {
        "type": "command",
        "timestamp": timestamp,
        "command": command,
        "output": clean_output,
        "exit_code": exit_code
    }


def write_jsonl_entry(log_path: Path, timestamp: str, command: str, output: str, exit_code: int) -> None:
    """
    Append a JSONL entry to the log file. Handles two types of entries:
    - Notes: When command starts with # (e.g., "# This is a note")
    - Commands: All other entries, with command, output, and exit code
    """
    # Determine entry type and create appropriate entry
    if command.startswith("#"):
        entry = create_note_entry(timestamp, command)
    else:
        entry = create_command_entry(timestamp, command, output, exit_code)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    if len(sys.argv) != 6:
        print("Usage: write_jsonl_entry.py <log_path> <timestamp> <command> <output> <exit_code>", file=sys.stderr)
        sys.exit(1)
    log_path = Path(sys.argv[1])
    timestamp = sys.argv[2]
    command = sys.argv[3]
    output = sys.argv[4]
    try:
        exit_code = int(sys.argv[5])
    except ValueError:
        print("Error: exit_code must be an integer.", file=sys.stderr)
        sys.exit(2)
    write_jsonl_entry(log_path, timestamp, command, output, exit_code)


if __name__ == "__main__":
    main()
