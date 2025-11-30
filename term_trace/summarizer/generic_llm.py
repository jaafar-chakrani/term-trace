from __future__ import annotations

from typing import List, Dict, Optional
import os
import json

try:
    import requests
except Exception:
    requests = None

from .llm_base import LLMSummarizer


class GenericChatSummarizer(LLMSummarizer):
    """Generic summarizer that works with any OpenAI-compatible chat completions endpoint.

    This class allows you to specify:
    - api_url: The full URL for the chat completions endpoint
    - token_env_var: Name of the environment variable containing the API token
    - model_name: The model identifier to use

    Examples:
        # OpenAI
        GenericChatSummarizer(
            api_url="https://api.openai.com/v1/chat/completions",
            token_env_var="OPENAI_API_KEY",
            model_name="gpt-3.5-turbo"
        )

        # GitHub Models
        GenericChatSummarizer(
            api_url="https://models.github.ai/inference/chat/completions",
            token_env_var="GITHUB_TOKEN",
            model_name="xai/grok-3-mini"
        )

        # Azure OpenAI
        GenericChatSummarizer(
            api_url="https://YOUR_RESOURCE.openai.azure.com/openai/deployments/YOUR_DEPLOYMENT/chat/completions?api-version=2024-02-01",
            token_env_var="AZURE_OPENAI_KEY",
            model_name="gpt-4"
        )

    Configuration via environment variables:
        LLM_API_URL       - API endpoint URL
        LLM_TOKEN_ENV_VAR - Name of env var containing the token
        LLM_MODEL_NAME    - Model identifier
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        token_env_var: Optional[str] = None,
        model_name: Optional[str] = None,
        api_token: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: int = 60,
    ):
        """Initialize generic chat summarizer.

        Args:
            api_url: Full URL to chat completions endpoint (or use LLM_API_URL env var)
            token_env_var: Name of env var with API token (or use LLM_TOKEN_ENV_VAR env var)
            model_name: Model identifier (or use LLM_MODEL_NAME env var)
            api_token: Explicit API token (takes precedence over env vars)
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
        """
        if requests is None:
            raise RuntimeError(
                "Missing dependency 'requests'. Install with: pip install requests")

        # API URL (required)
        self.api_url = api_url or os.environ.get("LLM_API_URL")
        if not self.api_url:
            raise ValueError(
                "api_url must be provided or LLM_API_URL environment variable must be set. "
                "Example: https://api.openai.com/v1/chat/completions"
            )

        # Token env var name (required to look up token)
        self.token_env_var = token_env_var or os.environ.get(
            "LLM_TOKEN_ENV_VAR")
        if not self.token_env_var and not api_token:
            raise ValueError(
                "token_env_var must be provided or LLM_TOKEN_ENV_VAR environment variable must be set. "
                "Example: OPENAI_API_KEY or GITHUB_TOKEN"
            )

        # Get the actual token
        if api_token:
            self.api_token = api_token
        elif self.token_env_var:
            self.api_token = os.environ.get(self.token_env_var)
        else:
            self.api_token = None

        # Model name (required)
        self.model_name = model_name or os.environ.get("LLM_MODEL_NAME")
        if not self.model_name:
            raise ValueError(
                "model_name must be provided or LLM_MODEL_NAME environment variable must be set. "
                "Example: gpt-3.5-turbo or xai/grok-3-mini"
            )

        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.timeout = int(timeout)

    def test_connection(self) -> tuple[bool, str]:
        """Test if the API token and endpoint are working.

        Returns:
            (success, message) tuple
        """
        if not self.api_token:
            return False, f"API token not found (checked env var: {self.token_env_var})"

        # Send a minimal test request
        test_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'ok'"}
        ]

        payload = {
            "model": self.model_name,
            "messages": test_messages,
            "temperature": 0,
            "max_tokens": 5,
        }

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=10
            )
            resp.raise_for_status()
            return True, "Connection successful"
        except requests.HTTPError as e:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text if resp is not None else "No response"
            return False, f"API error (HTTP {resp.status_code}): {error_body}"
        except Exception as e:
            return False, f"Connection failed: {e}"

    # Unified prompt configuration
    SYSTEM_PROMPT = (
        "You are a terminal session summarizer. Create a concise bullet-point summary "
        "of what was done. Use action verbs without subjects (e.g., 'Cloned repository', "
        "'Installed dependencies'). Focus on key steps and outcomes only."
    )

    USER_PROMPT_TEMPLATE = (
        "Summarize this terminal session as bullet points:\n\n{content}\n\n"
        "Format: Simple bullet list with action verbs, no subject pronouns."
    )

    def _build_prompt_messages(self, content: str) -> List[Dict[str, str]]:
        """Build chat messages from any content string.

        This is the unified prompt builder used by both summarize() and summarize_text().
        """
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": self.USER_PROMPT_TEMPLATE.format(
                content=content)}
        ]

    def _format_entries_as_text(self, entries: List[Dict], max_entries: Optional[int] = None) -> str:
        """Convert entries list to compact text representation."""
        from term_trace.config import Config
        if max_entries is None:
            max_entries = Config.MAX_ENTRIES_GENERIC
        if len(entries) > max_entries:
            entries = entries[-max_entries:]

        lines = []
        for e in entries:
            ts = e.get("timestamp", "?")
            typ = e.get("type", "cmd")
            if typ == "note":
                lines.append(f"[{ts}] NOTE: {e.get('text', '')}")
            else:
                cmd = e.get("command", "")
                out = e.get("output", "").strip().replace("\n", " ")
                exit_code = e.get("exit_code")
                lines.append(
                    f"[{ts}] CMD: {cmd} | OUT: {out} | EXIT: {exit_code}")

        return "\n".join(lines)

    def summarize(self, entries: List[Dict]) -> str:
        """Summarize a list of terminal entries."""
        if not entries:
            return "No entries to summarize."

        if not self.api_token:
            return f"API token not found (looked in env var: {self.token_env_var})"

        # Convert entries to text and build unified prompt
        content = self._format_entries_as_text(entries)
        messages = self._build_prompt_messages(content)

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            body = None
            try:
                body = resp.json()
            except Exception:
                body = resp.text if resp is not None else None
            return f"API error (HTTP {resp.status_code}): {e} - {body}"
        except Exception as e:
            return f"Request failed: {e}"

        try:
            j = resp.json()
            # Standard OpenAI-compatible format
            if "choices" in j and j["choices"]:
                message = j["choices"][0].get("message", {})

                # Try regular content first
                content = message.get("content")
                if content:
                    return content.strip()

                # For reasoning models (like grok-3-mini-high), check reasoning_content
                reasoning_content = message.get("reasoning_content")
                if reasoning_content:
                    return reasoning_content.strip()

            # Fallback: return full JSON
            return json.dumps(j, indent=2)
        except Exception as e:
            return f"Failed to parse response: {e} - raw: {resp.text}"

    def summarize_text(self, text: str) -> str:
        """Summarize pre-formatted text (for compatibility with session_manager)."""
        if not text:
            return "No text to summarize."

        if not self.api_token:
            return f"API token not found (looked in env var: {self.token_env_var})"

        # Use unified prompt builder
        messages = self._build_prompt_messages(text)

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            body = None
            try:
                body = resp.json()
            except Exception:
                body = resp.text if resp is not None else None
            return f"API error (HTTP {resp.status_code}): {e} - {body}"
        except Exception as e:
            return f"Request failed: {e}"

        try:
            j = resp.json()
            if "choices" in j and j["choices"]:
                message = j["choices"][0].get("message", {})

                # Try regular content first
                content = message.get("content")
                if content:
                    return content.strip()

                # For reasoning models (like grok-3-mini-high), check reasoning_content
                reasoning_content = message.get("reasoning_content")
                if reasoning_content:
                    return reasoning_content.strip()

            return json.dumps(j, indent=2)
        except Exception as e:
            return f"Failed to parse response: {e} - raw: {resp.text}"


# Convenience factory functions for common providers
def create_openai_summarizer(model_name: Optional[str] = None, **kwargs) -> GenericChatSummarizer:
    """Create summarizer configured for OpenAI."""
    from term_trace.config import Config
    return GenericChatSummarizer(
        api_url=Config.OPENAI_API_URL,
        token_env_var="OPENAI_API_KEY",
        model_name=model_name or Config.DEFAULT_OPENAI_MODEL,
        **kwargs
    )


def create_github_models_summarizer(model_name: Optional[str] = None, **kwargs) -> GenericChatSummarizer:
    """Create summarizer configured for GitHub Models."""
    from term_trace.config import Config
    return GenericChatSummarizer(
        api_url=Config.GITHUB_MODELS_API_URL,
        token_env_var="GITHUB_TOKEN",
        model_name=model_name or Config.DEFAULT_GITHUB_MODEL,
        **kwargs
    )


def create_azure_openai_summarizer(
    resource_name: str,
    deployment_name: str,
    api_version: str = "2024-02-01",
    **kwargs
) -> GenericChatSummarizer:
    """Create summarizer configured for Azure OpenAI.

    Args:
        resource_name: Azure OpenAI resource name
        deployment_name: Deployment name (not model name)
        api_version: API version string
    """
    api_url = (
        f"https://{resource_name}.openai.azure.com/openai/deployments/"
        f"{deployment_name}/chat/completions?api-version={api_version}"
    )
    return GenericChatSummarizer(
        api_url=api_url,
        token_env_var="AZURE_OPENAI_KEY",
        model_name=deployment_name,  # Azure uses deployment name
        **kwargs
    )
