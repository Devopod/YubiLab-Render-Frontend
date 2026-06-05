"""
Groq Service for Frontend - Fully Synchronous.
Direct Groq API integration for AI chat and agent features.

Supports dual API keys: GROQ_API_KEY and GROQ_API_KEY_2.
If one key hits rate limit, automatically falls back to the other.
"""

import os
import logging
from groq import Groq
from typing import Dict, List, Generator, Optional

logger = logging.getLogger(__name__)


class GroqService:
    """Frontend Groq API service - SYNCHRONOUS only, with dual-key rotation."""

    def __init__(self):
        self.api_keys = []
        key1 = os.getenv("GROQ_API_KEY", "")
        key2 = os.getenv("GROQ_API_KEY_2", "")
        if key1:
            self.api_keys.append(key1)
        if key2:
            self.api_keys.append(key2)

        self.default_model = os.getenv("GROQ_DEFAULT_MODEL", "openai/gpt-oss-120b")
        self.max_tokens = 4096
        self.current_key_index = 0

        self.clients = [Groq(api_key=k) for k in self.api_keys] if self.api_keys else []

    def _get_client(self) -> Optional[Groq]:
        if not self.clients:
            return None
        return self.clients[self.current_key_index % len(self.clients)]

    def _rotate_key(self):
        if len(self.clients) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.clients)
            logger.info(f"Rotated to Groq API key #{self.current_key_index + 1}")

    def chat_completion(self, messages: List[Dict], model: str = None,
                        max_tokens: int = 4096, temperature: float = 0.3,
                        reasoning_effort: str = "medium") -> str:
        """Synchronous chat completion with automatic key rotation."""
        if not self.clients:
            return "Error: Groq API key not configured"

        attempts = len(self.clients)
        for attempt in range(attempts):
            client = self._get_client()
            try:
                response = client.chat.completions.create(
                    model=model or self.default_model,
                    messages=messages,
                    max_completion_tokens=min(max_tokens, self.max_tokens),
                    temperature=temperature,
                    reasoning_effort=reasoning_effort,
                )
                return response.choices[0].message.content if response.choices else ""
            except Exception as e:
                error_str = str(e).lower()
                if "rate_limit" in error_str or "429" in error_str or "limit" in error_str:
                    logger.warning(f"Rate limit hit on key #{self.current_key_index + 1}, rotating...")
                    self._rotate_key()
                    if attempt < attempts - 1:
                        continue
                return f"Error: {str(e)}"
        return "Error: All API keys exhausted"

    def stream_completion(self, messages: List[Dict], model: str = None,
                          max_tokens: int = 4096, temperature: float = 0.3,
                          reasoning_effort: str = "medium") -> Generator[str, None, None]:
        """Synchronous streaming generator with automatic key rotation."""
        if not self.clients:
            yield "Error: Groq API key not configured"
            return

        attempts = len(self.clients)
        for attempt in range(attempts):
            client = self._get_client()
            try:
                stream = client.chat.completions.create(
                    model=model or self.default_model,
                    messages=messages,
                    max_completion_tokens=min(max_tokens, self.max_tokens),
                    temperature=temperature,
                    reasoning_effort=reasoning_effort,
                    stream=True,
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as e:
                error_str = str(e).lower()
                if "rate_limit" in error_str or "429" in error_str or "limit" in error_str:
                    logger.warning(f"Rate limit hit on key #{self.current_key_index + 1}, rotating...")
                    self._rotate_key()
                    if attempt < attempts - 1:
                        continue
                yield f"\n[Error: {str(e)}]"
                return


groq_service = GroqService()
