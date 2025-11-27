from __future__ import annotations
from typing import List, Dict, Optional
import os
import requests
from .llm_base import LLMSummarizer


class HuggingFaceSummarizer(LLMSummarizer):
    """Simple summarizer using Hugging Face Inference API.

    This uses the public Inference API endpoint at
    https://api-inference.huggingface.co/models/{model_name}.

    Notes:
    - For reliable usage, set the environment variable HF_API_TOKEN with a
      Hugging Face API token (free tier available).
    - If no token is provided some models may still allow limited anonymous
      inference; behavior depends on Hugging Face account and model settings.
    - This implementation keeps things simple: it concatenates recent entries
      into a prompt and asks the model to produce a short summary.
    """

    def __init__(self, model_name: Optional[str] = None, hf_api_token: Optional[str] = None, max_length: int = 200):
        from term_trace.config import Config
        DEFAULT_MODEL = os.environ.get(
            "HF_MODEL_NAME", Config.DEFAULT_HF_MODEL)
        self.model_name = model_name or DEFAULT_MODEL
        self.hf_api_token = hf_api_token or os.environ.get("HUGGINGFACE_TOKEN")
        self.api_url = Config.get_hf_api_url(self.model_name)
        self.max_length = max_length

    def _build_prompt(self, entries: List[Dict]) -> str:
        from term_trace.config import Config
        # Limit the number of entries to keep prompt size reasonable
        max_entries = Config.MAX_ENTRIES_HF
        if len(entries) > max_entries:
            entries = entries[-max_entries:]

        lines = []
        for e in entries:
            ts = e.get("timestamp", "unknown time")
            cmd = e.get("command", "")
            out = e.get("output", "")
            out_preview = out.replace("\n", " \n ")
            lines.append(f"[{ts}] {cmd} -> {out_preview}")

        text = "\n".join(lines)
        prompt = (
            "The following are terminal session entries. "
            "Write a concise, plain-language summary of the user's workflow, goals, and important outputs.\n\n"
            f"Session entries:\n{text}\n\nSummary:"
        )
        return prompt

    def summarize(self, entries: List[Dict]) -> str:
        if not entries:
            return "No entries to summarize."

        prompt = self._build_prompt(entries)

        headers = {"Accept": "application/json"}
        if self.hf_api_token:
            headers["Authorization"] = f"Bearer {self.hf_api_token}"

        payload = {
            "inputs": prompt,
            "parameters": {"max_length": self.max_length, "do_sample": False},
        }

        try:
            resp = requests.post(
                self.api_url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # Inference API returns a list of generated items for some models
            if isinstance(data, list) and data:
                text = data[0].get("generated_text") or data[0].get(
                    "summary_text") or data[0].get("text")
                if text:
                    return text.strip()

            # Or a dict with 'summary_text' (summarization pipeline)
            if isinstance(data, dict):
                # Some models return {'summary_text': '...'}
                if "summary_text" in data:
                    return data["summary_text"].strip()
                # Or {'generated_text': '...'}
                if "generated_text" in data:
                    return data["generated_text"].strip()

            # If nothing usable, return a simple fallback
            return "(No summary returned by HF API)"

        except requests.HTTPError as e:
            return f"HuggingFace API error: {e} - response: {getattr(e.response, 'text', '')}"
        except Exception as e:  # network, timeout, JSON errors
            return f"HuggingFace summarization failed: {e}"
