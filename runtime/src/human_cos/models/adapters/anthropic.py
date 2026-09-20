"""Anthropic Messages API adapter for S2-L."""

from __future__ import annotations

import os
from typing import Any

from human_cos.models.adapters.http import HttpOpener, request_json
from human_cos.models.errors import ModelAdapterError
from human_cos.models.types import AdapterErrorCode, ModelIdentity, ModelRequest, ModelResponse


class AnthropicMessagesAdapter:
    def __init__(
        self,
        identity: ModelIdentity,
        *,
        api_key: str | None = None,
        endpoint: str = "https://api.anthropic.com/v1/messages",
        api_version: str = "2023-06-01",
        timeout: float = 60.0,
        opener: HttpOpener | None = None,
    ) -> None:
        if identity.provider != "anthropic":
            raise ValueError("AnthropicMessagesAdapter identity.provider must be 'anthropic'")
        self._identity = identity
        self._api_key = api_key
        self._endpoint = endpoint
        self._api_version = api_version
        self._timeout = timeout
        self._opener = opener

    @property
    def identity(self) -> ModelIdentity:
        return self._identity

    def _key(self) -> str:
        key = self._api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ModelAdapterError(
                AdapterErrorCode.CONFIGURATION,
                self._identity,
                "ANTHROPIC_API_KEY is not configured",
                retryable=False,
            )
        return key

    @staticmethod
    def _output_text(data: dict[str, Any]) -> str | None:
        content = data.get("content")
        if not isinstance(content, list):
            return None
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
        return "".join(parts) or None

    def invoke(self, request: ModelRequest) -> ModelResponse:
        data, request_id = request_json(
            identity=self._identity,
            url=self._endpoint,
            headers={
                "x-api-key": self._key(),
                "anthropic-version": self._api_version,
                "content-type": "application/json",
            },
            payload={
                "model": self._identity.model_id,
                "max_tokens": request.max_output_tokens,
                "messages": [{"role": "user", "content": request.input_text}],
            },
            timeout=self._timeout,
            opener=self._opener,
        )
        text = self._output_text(data)
        if text is None:
            raise ModelAdapterError(
                AdapterErrorCode.INVALID_RESPONSE,
                self._identity,
                "Anthropic response did not contain text content",
                retryable=False,
            )
        stop_reason = data.get("stop_reason")
        usage = data.get("usage")
        return ModelResponse(
            identity=self._identity,
            output_text=text,
            finish_reason=stop_reason if isinstance(stop_reason, str) else None,
            provider_request_id=request_id,
            usage=usage if isinstance(usage, dict) else None,
        )
