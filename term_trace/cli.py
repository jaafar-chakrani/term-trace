#!/usr/bin/env python3
import argparse
from term_trace.logger.session_manager import start_session


def main():
    parser = argparse.ArgumentParser(description="term-trace CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Start command
    start_parser = subparsers.add_parser("start", help="Start a session")
    start_parser.add_argument(
        "--workspace", required=True, help="Workspace name")
    start_parser.add_argument("--session-name", help="Optional session name")

    args = parser.parse_args()

    if args.command == "start":
        start_session(workspace=args.workspace, session_name=args.session_name)
        # Logs are flushed automatically after shell exits
        print("Session fully completed.")


if __name__ == "__main__":
    main()
