from __future__ import annotations
from typing import List, Dict
from abc import ABC, abstractmethod

class LLMSummarizer(ABC):
    """
    Abstract base class for LLM-based summarizers.
    Implementations must provide `summarize` method.
    """

    @abstractmethod
    def summarize(self, entries: List[Dict]) -> str:
        """
        Generate a summary from terminal session entries.

        Args:
            entries (List[Dict]): List of JSON entries with "timestamp", "command", "output".

        Returns:
            str: AI-generated summary text.
        """
        pass
