"""LLM adapters for the assistant runtime."""

from __future__ import annotations

import logging
from typing import Any

from keel.core.engine import LLMInterface

from assistant.config import LLMSettings
from assistant.http_client import JsonHttpClient

logger = logging.getLogger(__name__)


class OpenAICompatibleLLM(LLMInterface):
    """OpenAI-compatible chat completions adapter."""

    def __init__(self, settings: LLMSettings):
        self._settings = settings
        self._http = JsonHttpClient(timeout_seconds=settings.request_timeout_seconds)

    def complete(self, messages: list[dict[str, str]] | str) -> str:
        payload_messages = self._coerce_messages(messages)
        logger.debug(
            "LLM request: model=%s messages=%d temperature=%.2f",
            self._settings.model,
            len(payload_messages),
            self._settings.temperature,
        )
        response = self._http.request_json(
            "POST",
            self._settings.api_url,
            headers={"Authorization": f"Bearer {self._settings.api_key}"},
            payload={
                "model": self._settings.model,
                "messages": payload_messages,
                "temperature": self._settings.temperature,
            },
        )
        choices = response.get("choices", [])
        if not choices:
            raise RuntimeError("LLM API returned no choices")

        message = choices[0].get("message", {})
        content = self._extract_content(message.get("content", ""))
        if not content:
            raise RuntimeError("LLM API returned an empty response")
        logger.debug("LLM response: length=%d", len(content))
        return content

    def _coerce_messages(self, messages: list[dict[str, str]] | str) -> list[dict[str, str]]:
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        return messages

    def _extract_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            return "\n".join(part for part in text_parts if part).strip()
        return str(content).strip()
