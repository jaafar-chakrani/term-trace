from ..summarizer.core import JSONLSummarizer, SummarizationMode
from ..summarizer.hf_llm import HuggingFaceSummarizer
from ..config import Config
import os
import logging
from pathlib import Path
from datetime import datetime
import subprocess
import tempfile
import textwrap


def _launch_hook_shell(workspace: str, session_name: str, n_lines: int = 10):

    env = os.environ.copy()
    log_dir = Config.WORKSPACE_DIR / workspace
    log_dir.mkdir(parents=True, exist_ok=True)

    env["ZSH_LOG_DIR"] = log_dir
    env["ZSH_COMMANDS_LOG"] = f"{log_dir}/session_{session_name}_commands.txt"
    env["ZSH_OUTPUTS_LOG"] = f"{log_dir}/session_{session_name}_outputs.txt"
    env["ZSH_JSONL_LOG"] = f"{log_dir}/session_{session_name}.jsonl"
    env["ZSH_FIRST_LINES"] = str(n_lines)
    env["ZSH_LAST_LINES"] = str(n_lines)

    script_path = Path(__file__).parent.parent / \
        "scripts" / "zsh_jsonl_trace.sh"

    with tempfile.TemporaryDirectory() as zdotdir:
        zshrc_path = os.path.join(zdotdir, ".zshrc")
        user_rc = os.path.expanduser(Config.USER_SHELL_RC)
        with open(zshrc_path, "w") as f:
            f.write(textwrap.dedent(f"""
                # Load user's normal config
                if [ -f {user_rc} ]; then
                    source {user_rc}
                fi

                # Then load term-trace hook
                source {script_path}
            """))

        env["ZDOTDIR"] = zdotdir

        # Don't raise exception on 130 (normal user interruption)
        result = subprocess.run(["zsh", "--login", "-i"], env=env)
        if result.returncode not in (0, 130):
            raise subprocess.CalledProcessError(result.returncode, result.args)


def start_session(
    workspace: str,
    session_name: str | None = None,
    summarize: bool = True,
    summarize_mode: SummarizationMode = "openai",
    batch_size: int | None = None,
    interval: int | None = None
):
    """
    Start a new term-trace session with optional live summarization.

    Args:
        workspace: Name of the workspace to use
        session_name: Optional custom session name
        summarize: Whether to enable live summarization
        summarize_mode: Summarization mode (markdown, openai, huggingface, github, custom)
        batch_size: Number of entries to batch before summarization
        interval: Time interval in seconds for periodic summarization
    """
    # Prepare workspace
    workspace_path = Config.WORKSPACE_DIR / workspace
    workspace_path.mkdir(parents=True, exist_ok=True)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = session_name or f"session_{session_id}"

    # Set up logging to file for debugging
    debug_log_file = workspace_path / f"session_{session_id}_debug.log"
    handlers = [logging.FileHandler(debug_log_file)]

    # Optionally add console handler
    if Config.DEBUG_LOG_TO_CONSOLE:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True  # Override any existing config
    )

    jsonl_path = workspace_path / f"session_{session_id}.jsonl"
    print(f"Session started: {session_name} in workspace: {workspace}")

    # Use config defaults if not provided
    if batch_size is None:
        batch_size = Config.SUMMARIZE_BATCH_SIZE
    if interval is None:
        interval = Config.SUMMARIZE_INTERVAL

    # Always create a logger for full log recording
    # If summarize=True, we'll try to set up LLM summarization
    # If that fails or summarize=False, we fall back to markdown mode
    llm_fn = None
    actual_mode = summarize_mode

    # Try to set up LLM if summarization is requested
    if summarize:
        if summarize_mode == "huggingface":
            # HuggingFace
            hf_token = os.environ.get("HUGGINGFACE_TOKEN")
            if not hf_token:
                print(
                    "Warning: HUGGINGFACE_TOKEN not set. Using markdown mode for full logs only.")
                actual_mode = "markdown"
                llm_fn = None
            else:
                print("Using HuggingFace summarizer")
                hf_model = os.environ.get("HF_MODEL_NAME")
                hf = HuggingFaceSummarizer(
                    model_name=hf_model, hf_api_token=hf_token)

                def _hf_fn(text: str) -> str:
                    entries = [{"type": "note", "text": text}]
                    return hf.summarize(entries)

                llm_fn = _hf_fn
                actual_mode = "custom"

        elif summarize_mode == "openai":
            # OpenAI GPT
            openai_key = os.environ.get("OPENAI_API_KEY")
            if not openai_key:
                print(
                    "Warning: OPENAI_API_KEY not set. Using markdown mode for full logs only.")
                actual_mode = "markdown"
                llm_fn = None
            else:
                print("Using OpenAI GPT summarizer")
                try:
                    from ..summarizer.generic_llm import create_openai_summarizer
                    openai = create_openai_summarizer()

                    # Test the connection
                    print("Testing OpenAI API connection...")
                    success, message = openai.test_connection()
                    if not success:
                        print(f"Warning: OpenAI API test failed: {message}")
                        print("   Using markdown mode for full logs only.")
                        actual_mode = "markdown"
                        llm_fn = None
                    else:
                        print(f"    {message}")

                        def _openai_fn(text: str) -> str:
                            return openai.summarize_text(text)

                        llm_fn = _openai_fn
                        actual_mode = "custom"
                except Exception as e:
                    print(
                        f"Warning: Could not initialize OpenAI summarizer: {e}")
                    print(
                        "   Using markdown mode for full logs only.")
                    actual_mode = "markdown"
                    llm_fn = None

        elif summarize_mode == "github":
            # GitHub Models
            github_token = os.environ.get("GITHUB_TOKEN")
            if not github_token:
                print(
                    "Warning: GITHUB_TOKEN not set. Using markdown mode for full logs only.")
                actual_mode = "markdown"
                llm_fn = None
            else:
                print("Using GitHub Models summarizer")
                try:
                    from ..summarizer.generic_llm import create_github_models_summarizer
                    github = create_github_models_summarizer()

                    # Test the connection
                    print("Testing GitHub Models API connection...")
                    success, message = github.test_connection()
                    if not success:
                        print(
                            f"Warning: GitHub Models API test failed: {message}")
                        print("   Using markdown mode for full logs only.")
                        actual_mode = "markdown"
                        llm_fn = None
                    else:
                        print(f"    {message}")

                        def _github_fn(text: str) -> str:
                            return github.summarize_text(text)

                        llm_fn = _github_fn
                        actual_mode = "custom"
                except Exception as e:
                    print(
                        f"Warning: Could not initialize GitHub Models summarizer: {e}")
                    print(
                        "   Using markdown mode for full logs only.")
                    actual_mode = "markdown"
                    llm_fn = None

    # Always create the logger (for full log recording)
    # Use workspace-level summary file (not session-level)
    workspace_summary_file = workspace_path / f"{workspace}_summary.md"

    print(f"\nStarting session logger (mode: {actual_mode})")

    summarizer = JSONLSummarizer(
        str(jsonl_path),
        summary_file=str(workspace_summary_file),
        mode=actual_mode,
        llm_function=llm_fn,
        batch_size=batch_size,
        interval=interval,
        workspace_name=workspace,
        google_doc_title=f"term-trace: {workspace}"
    )

    # Print summarization configuration
    if batch_size > 0:
        print(f"Real-time summarization: Every {batch_size} entries")
    elif interval > 0:
        print(f"Real-time summarization: Every {interval} seconds")
    else:
        print(
            f"Real-time summarization: Disabled (use 'term-trace summarize' to generate on-demand)")

    # Print summary of where logs will be saved
    print("\n" + "="*60)
    print("Session Log Locations:")
    print("="*60)
    print(f"JSONL log:  {jsonl_path}")
    print(f"Markdown:   {workspace_summary_file} (workspace-level)")
    print(f"Debug log:  {debug_log_file}")
    if hasattr(summarizer, 'google_logger') and summarizer.google_logger:
        doc_url = summarizer.google_logger.get_doc_url()
        print(f"Google Doc: {doc_url}")
    print("="*60 + "\n")

    try:
        # Launch the shell interactively
        _launch_hook_shell(workspace, session_id)
    finally:
        if summarizer and summarizer.thread.is_alive():
            summarizer.stop()
        print("Session ended.")
