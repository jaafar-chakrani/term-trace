from ..summarizer.core import JSONLSummarizer, SummarizationMode
from ..summarizer.hf_llm import HuggingFaceSummarizer
from ..summarizer.gpt_llm import OpenAIGPTSummarizer
from ..config import Config
import os
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

        subprocess.run(["zsh", "--login", "-i"], check=True, env=env)


def start_session(
    workspace: str,
    session_name: str | None = None,
    summarize: bool = True,
    summarize_mode: SummarizationMode = "gpt",
    batch_size: int = 5,
    interval: int = -1
):
    """
    Start a new term-trace session with optional live summarization.

    Args:
        workspace: Name of the workspace to use
        session_name: Optional custom session name
        summarize: Whether to enable live summarization
        summarize_mode: Summarization mode (markdown, remote_llm, custom)
        batch_size: Number of entries to batch before summarization
        interval: Time interval in seconds for periodic summarization
    """
    # Prepare workspace
    workspace_path = Config.WORKSPACE_DIR / workspace
    workspace_path.mkdir(parents=True, exist_ok=True)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = session_name or f"session_{session_id}"

    jsonl_path = workspace_path / f"session_{session_id}.jsonl"
    print(f"Session started: {session_name} in workspace: {workspace}")

    # Start summarizer if requested
    summarizer = None
    if summarize:
        print(f"Starting live summarization (mode: {summarize_mode})")
        llm_fn = None

        # All LLM providers are treated as "remote_llm" - the mode just specifies which provider
        if summarize_mode == "remote_llm":
            # HuggingFace
            hf_token = os.environ.get("HUGGINGFACE_TOKEN")
            if not hf_token:
                print(
                    "Warning: HUGGINGFACE_TOKEN not set. Continuing without LLM summarization.")
                print("   Only full logs will be recorded.")
                summarize = False
            else:
                print("Using HuggingFace summarizer")
                hf_model = os.environ.get("HF_MODEL_NAME")
                hf = HuggingFaceSummarizer(
                    model_name=hf_model, hf_api_token=hf_token)

                def _hf_fn(text: str) -> str:
                    entries = [{"type": "note", "text": text}]
                    return hf.summarize(entries)

                llm_fn = _hf_fn
                summarize_mode = "custom"

        elif summarize_mode in ("gpt", "openai"):
            # OpenAI GPT
            openai_key = os.environ.get("OPENAI_API_KEY")
            if not openai_key:
                print(
                    "Warning: OPENAI_API_KEY not set. Continuing without LLM summarization.")
                print("   Only full logs will be recorded.")
                summarize = False
            else:
                print("Using OpenAI GPT summarizer")
                try:
                    gpt = OpenAIGPTSummarizer()

                    def _gpt_fn(text: str) -> str:
                        return gpt.summarize_text(text)

                    llm_fn = _gpt_fn
                    summarize_mode = "custom"
                except Exception as e:
                    print(
                        f"Warning: Could not initialize OpenAI summarizer: {e}")
                    print(
                        "   Continuing without LLM summarization. Only full logs will be recorded.")
                    summarize = False

        elif summarize_mode == "github":
            # GitHub Models
            github_token = os.environ.get("GITHUB_TOKEN")
            if not github_token:
                print(
                    "Warning: GITHUB_TOKEN not set. Continuing without LLM summarization.")
                print("   Only full logs will be recorded.")
                summarize = False
            else:
                print("Using GitHub Models summarizer")
                try:
                    from ..summarizer.generic_llm import create_github_models_summarizer
                    github = create_github_models_summarizer()

                    def _github_fn(text: str) -> str:
                        return github.summarize_text(text)

                    llm_fn = _github_fn
                    summarize_mode = "custom"
                except Exception as e:
                    print(
                        f"Warning: Could not initialize GitHub Models summarizer: {e}")
                    print(
                        "   Continuing without LLM summarization. Only full logs will be recorded.")
                    summarize = False

        # Only create summarizer if we still have summarization enabled
        # Use workspace-level summary file (not session-level)
        workspace_summary_file = workspace_path / f"{workspace}_summary.md"
        if summarize:
            summarizer = JSONLSummarizer(
                str(jsonl_path),
                summary_file=str(workspace_summary_file),
                mode=summarize_mode,
                llm_function=llm_fn,
                batch_size=batch_size,
                interval=interval,
                workspace_name=workspace,
                google_doc_title=f"term-trace: {workspace}"
            )
        else:
            print("Session will record commands and outputs only (no summarization).")

    # Print summary of where logs will be saved
    print("\n" + "="*60)
    print("Session Log Locations:")
    print("="*60)
    print(f"JSONL log: {jsonl_path}")
    if summarizer:
        print(f"Summary:   {workspace_summary_file} (workspace-level)")
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
