# term-trace
*Trace your terminal sessions, annotate them inline, and generate structured summaries.*

`term-trace` is a CLI tool that logs all commands and outputs from your zsh terminal sessions, allows inline notes, and summarizes activity into human-readable formats (in Google Docs and/or Markdown).

## Features

- 📝 **Automatic session logging** - Captures all commands, outputs, and exit codes in JSONL format
- 🤖 **AI-powered summaries** - Generate concise summaries using OpenAI, GitHub Models, or HuggingFace
- 📄 **Multiple output formats** - Export to Markdown files and/or Google Docs
- 🏢 **Workspace organization** - Group related sessions into workspaces
- 🔄 **Live summarization** - Summaries update in real-time as you work
- 💬 **Inline notes** - Add annotations directly from your terminal


## Requirements

- **Python 3.11 or higher**
- **macOS or Linux**: supports zsh shell only
- **Optional**: API tokens for LLM providers (OpenAI, GitHub, or HuggingFace)
- **Optional**: Google OAuth credentials for Google Docs integration

## Installation

### From source

```console
$ git clone https://github.com/jaafar-chakrani/term-trace.git
$ cd term-trace
$ pip install -e .
```

### Dependencies

The following dependencies are automatically installed:
- `requests` - HTTP client for API calls
- `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2`, `google-api-python-client` - Google Docs integration

## Configuration

### Environment Variables

Create a `.env` file or export variables in your shell (see `.env.example` for the full list):

```bash
# Required for LLM summarization (choose one or more)
export OPENAI_API_KEY="sk-..."           # For OpenAI GPT models
export GITHUB_TOKEN="ghp_..."            # For GitHub Models
export HUGGINGFACE_TOKEN="hf_..."        # For HuggingFace models

# Optional: Custom model selection
export OPENAI_MODEL="gpt-4"              # Default: gpt-3.5-turbo
export GITHUB_MODEL="xai/grok-3-mini"    # Default: xai/grok-3-mini
export HF_MODEL_NAME="facebook/bart-large-cnn"  # Default: sshleifer/distilbart-cnn-12-6

# Optional: Google Docs integration
export GOOGLE_CLIENT_SECRET="path/to/credentials.json"

# Optional: Custom data directory
export TERMTRACE_BASE_DIR="$HOME/.termtrace"  # Default: ~/.termtrace
```

### Google Docs Setup (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the Google Docs API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download the credentials JSON file
6. Set `GOOGLE_CLIENT_SECRET` to the file path

On first use, you'll be prompted to authorize the application in your browser.

## Usage

### Start a traced session

```console
$ term-trace start --workspace <workspace-name>
```

This launches a new shell session where all commands are automatically logged.

### Basic Examples

**Start with OpenAI GPT summarization (default):**
```console
$ term-trace start --workspace my-project
```

**Use GitHub Models instead:**
```console
$ term-trace start --workspace my-project --llm github
```

**Use HuggingFace models:**
```console
$ term-trace start --workspace my-project --llm huggingface
```

**Markdown only (no LLM):**
```console
$ term-trace start --workspace my-project --llm markdown
```

**Disable summarization completely:**
```console
$ term-trace start --workspace my-project --no-summarize
```

**Custom session name:**
```console
$ term-trace start --workspace my-project --session-name bug-fix-session
```

### Command-line Options

```console
$ term-trace start [OPTIONS]

Options:
  --workspace TEXT       Workspace name (required)
  --session-name TEXT    Custom session name (default: auto-generated timestamp)
  --llm TEXT            LLM provider for summarization
                        Choices: openai, gpt, github, huggingface, hf, markdown, none
                        Default: openai
  --no-summarize        Disable summarization (logging only)
  -h, --help            Show help message
```

### Adding Inline Notes

While in a traced session, simply start a line with `#` to log a note:

```console
$ # Starting database migration
$ psql -d mydb -f migration.sql
$ # Testing the new schema
$ psql -d mydb -c "SELECT * FROM users LIMIT 5"
$ # Migration completed successfully
```

Notes are automatically captured and included in both the session log and summaries.

### Triggering Summarization on Demand

By default, summarization happens automatically in batches. To generate a summary immediately at any point from within a traced session:

```console
$ term-trace summarize
```

This is useful when you want to capture a summary at a specific milestone or before switching to a different task, or if you disable the automatic summarization. Note that this command is only possible from within a traced session.

### Where Files Are Stored

All session data is stored in `~/.termtrace/workspaces/<workspace-name>/` (or your custom `TERMTRACE_BASE_DIR`):

```
~/.termtrace/
└── workspaces/
    └── my-project/
        ├── my-project_summary.md           # Workspace-level summary (all sessions)
        ├── session_20250127_143022.jsonl   # Raw session log
        ├── session_20250127_150315.jsonl   # Another session
        └── ...
```

### Session Summary

At the start of each session, you'll see:

```
Session started: session_20250127_143022 in workspace: my-project
Using OpenAI GPT summarizer
Starting live summarization (mode: openai)

============================================================
Session Log Locations:
============================================================
JSONL log: /Users/you/.termtrace/workspaces/my-project/session_20250127_143022.jsonl
Summary:   /Users/you/.termtrace/workspaces/my-project/my-project_summary.md (workspace-level)
Google Doc: https://docs.google.com/document/d/...
============================================================
```

## LLM Provider Details

### OpenAI
- Models: `gpt-4`, `gpt-3.5-turbo`, etc.
- Requires: `OPENAI_API_KEY`
- Best quality summaries

### GitHub Models (Free for developers)
- Models: `xai/grok-3-mini`, `meta-llama/Llama-3.3-70B-Instruct`, etc.
- Requires: `GITHUB_TOKEN` (GitHub Personal Access Token with models scope)
- Free tier available for GitHub users

### HuggingFace
- Models: Any HuggingFace model with text generation
- Requires: `HUGGINGFACE_TOKEN`
- Free tier available

### Markdown (No LLM)
- Generates deterministic markdown summaries
- No API token required
- Good for privacy-sensitive environments


### Project Structure

```
term-trace/
├── term_trace/
│   ├── cli.py                    # CLI entry point
│   ├── config.py                 # Centralized configuration
│   ├── logger/
│   │   └── session_manager.py    # Session management
│   ├── summarizer/
│   │   ├── core.py              # Background summarization
│   │   ├── generic_llm.py       # OpenAI-compatible APIs
│   │   ├── hf_llm.py            # HuggingFace API
│   │   └── google_docs.py       # Google Docs integration
│   ├── workspaces/
│   │   └── manager.py           # Workspace management
│   └── scripts/
│       ├── write_jsonl_entry.py # Note-taking command
│       └── zsh_jsonl_trace.sh   # Shell hooks
├── pyproject.toml
└── README.md
```

## Example Session

Here's what a small traced session looks like:

**Terminal session:**
```console
$ term-trace start --workspace demo-project
Session started: session_20250127_143022 in workspace: demo-project
Using OpenAI GPT summarizer
...

$ # Setting up a new Python project
$ mkdir my-app && cd my-app
$ python -m venv venv
$ source venv/bin/activate
$ pip install requests flask
Successfully installed requests-2.31.0 flask-3.0.0 ...
$ # Creating the main application file
$ echo 'from flask import Flask\napp = Flask(__name__)' > app.py
$ ls
app.py  venv
$ exit
Session ended.
```

**Generated JSONL log (`session_20250127_143022.jsonl`):**
```jsonl
{"type": "note", "timestamp": "2025-01-27T14:30:45Z", "text": "Setting up a new Python project"}
{"type": "command", "timestamp": "2025-01-27T14:30:48Z", "command": "mkdir my-app && cd my-app", "output": "", "exit_code": 0}
{"type": "command", "timestamp": "2025-01-27T14:30:52Z", "command": "python -m venv venv", "output": "", "exit_code": 0}
{"type": "command", "timestamp": "2025-01-27T14:30:55Z", "command": "source venv/bin/activate", "output": "", "exit_code": 0}
{"type": "command", "timestamp": "2025-01-27T14:31:02Z", "command": "pip install requests flask", "output": "Collecting requests\n  Downloading requests-2.31.0-py3-none-any.whl\nCollecting flask\n  Downloading flask-3.0.0-py3-none-any.whl\nSuccessfully installed requests-2.31.0 flask-3.0.0 Werkzeug-3.0.1 click-8.1.7", "exit_code": 0}
{"type": "note", "timestamp": "2025-01-27T14:31:15Z", "text": "Creating the main application file"}
{"type": "command", "timestamp": "2025-01-27T14:31:18Z", "command": "echo 'from flask import Flask\\napp = Flask(__name__)' > app.py", "output": "", "exit_code": 0}
{"type": "command", "timestamp": "2025-01-27T14:31:22Z", "command": "ls", "output": "app.py\nvenv", "exit_code": 0}
```

**AI-generated summary (`demo-project_summary.md`):**
```markdown
## Session Summary

- Set up a new Python project
- Created and activated a virtual environment
- Installed requests and flask packages
- Created main application file (app.py)
- Verified project structure
```

## License

MIT License - see LICENSE file for details


## Contributing

Contributions welcome! Please open an issue or PR on GitHub.