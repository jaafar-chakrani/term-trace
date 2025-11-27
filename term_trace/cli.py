#!/usr/bin/env python3
import argparse
from term_trace.logger.session_manager import start_session
from term_trace.viewer.app import run_viewer


def main():
    parser = argparse.ArgumentParser(description="term-trace CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Start command
    start_parser = subparsers.add_parser("start", help="Start a session")
    start_parser.add_argument(
        "--workspace", required=True, help="Workspace name")
    start_parser.add_argument("--session-name", help="Optional session name")
    start_parser.add_argument(
        "--llm",
        choices=["openai", "gpt", "github",
                 "huggingface", "hf", "markdown", "none"],
        default="openai",
        help="LLM provider to use for summarization (default: openai)")
    start_parser.add_argument(
        "--no-summarize",
        action="store_true",
        help="Disable live summarization")

    # View command
    view_parser = subparsers.add_parser(
        "view", help="View recorded sessions in a TUI")
    view_parser.add_argument("workspace", nargs="?",
                             help="Workspace name (optional)")
    view_parser.add_argument("--session", dest="session",
                             help="Specific session file name (optional)")

    args = parser.parse_args()

    if args.command == "start":
        # Map LLM choice to mode
        llm_mode = args.llm
        if llm_mode in ("huggingface", "hf"):
            llm_mode = "huggingface"
        elif llm_mode == "github":
            llm_mode = "github"
        elif llm_mode == "none":
            llm_mode = "markdown"
        elif llm_mode in ("openai", "gpt"):
            llm_mode = "openai"

        start_session(
            workspace=args.workspace,
            session_name=args.session_name,
            summarize=not args.no_summarize,
            summarize_mode=llm_mode)
        # Logs are flushed automatically after shell exits
        print("Session fully completed.")
    elif args.command == "view":
        run_viewer(workspace=args.workspace, session=args.session)


if __name__ == "__main__":
    main()
