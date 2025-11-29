"""Centralized configuration for term-trace.

All hardcoded paths, URLs, and default values are defined here.
Values can be overridden via environment variables or .env file.
"""
from __future__ import annotations
import os
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    # Look for .env in current directory, home directory, or project root
    env_paths = [
        Path.cwd() / ".env",
        Path.home() / ".termtrace" / ".env",
        Path(__file__).parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    # python-dotenv not installed, skip .env loading
    pass


class Config:
    """Global configuration for term-trace."""

    # Base directory for all term-trace data
    BASE_DIR: Path = Path(os.environ.get(
        "TERMTRACE_BASE_DIR",
        str(Path.home() / ".termtrace")
    ))

    # Workspace directory
    WORKSPACE_DIR: Path = BASE_DIR / "workspaces"

    # Google OAuth token storage
    GOOGLE_TOKEN_PATH: Path = BASE_DIR / "token.pickle"

    # API endpoints
    OPENAI_API_URL: str = os.environ.get(
        "OPENAI_API_URL",
        "https://api.openai.com/v1/chat/completions"
    )

    GITHUB_MODELS_API_URL: str = os.environ.get(
        "GITHUB_MODELS_API_URL",
        "https://models.github.ai/inference/chat/completions"
    )

    HUGGINGFACE_API_URL_TEMPLATE: str = os.environ.get(
        "HUGGINGFACE_API_URL_TEMPLATE",
        "https://router.huggingface.co/hf-inference/models/{model}"
    )

    # Default model names
    DEFAULT_OPENAI_MODEL: str = os.environ.get(
        "OPENAI_MODEL",
        "gpt-3.5-turbo"
    )

    DEFAULT_GITHUB_MODEL: str = os.environ.get(
        "GITHUB_MODEL",
        "xai/grok-3-mini"
    )

    DEFAULT_HF_MODEL: str = os.environ.get(
        "HF_MODEL_NAME",
        "sshleifer/distilbart-cnn-12-6"
    )

    # API timeouts (seconds)
    DEFAULT_API_TIMEOUT: int = int(os.environ.get(
        "TERMTRACE_API_TIMEOUT",
        "60"
    ))

    # Entry limits for summarization
    MAX_ENTRIES_HF: int = int(os.environ.get(
        "TERMTRACE_MAX_ENTRIES_HF",
        "60"
    ))

    MAX_ENTRIES_GENERIC: int = int(os.environ.get(
        "TERMTRACE_MAX_ENTRIES_GENERIC",
        "80"
    ))

    # LLM generation parameters
    DEFAULT_TEMPERATURE: float = float(os.environ.get(
        "TERMTRACE_TEMPERATURE",
        "0.2"
    ))

    DEFAULT_MAX_TOKENS: int = int(os.environ.get(
        "TERMTRACE_MAX_TOKENS",
        "300"
    ))

    # Shell configuration
    USER_SHELL_RC: str = os.environ.get(
        "TERMTRACE_SHELL_RC",
        "~/.zshrc"
    )

    @classmethod
    def ensure_directories(cls) -> None:
        """Create necessary directories if they don't exist."""
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)
        cls.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_hf_api_url(cls, model_name: str) -> str:
        """Get the HuggingFace API URL for a specific model."""
        return cls.HUGGINGFACE_API_URL_TEMPLATE.format(model=model_name)


# Initialize directories on import
Config.ensure_directories()
