"""OpenAI Responses API adapter for S2-L.

The adapter is a provider boundary only. It does not use the Agents SDK and
does not receive Human-COS state-machine or reality-execution authority.
"""

from __future__ import annotations

import os
from typing import Any

from human_cos.models.adapters.http import HttpOpener, request_json
from human_cos.models.errors import ModelAdapterError
from human_cos.models.types import AdapterErrorCode, ModelIdentity, ModelRequest, ModelResponse


class OpenAIResponsesAdapter:
    def __init__(
        self,
        identity: ModelIdentity,
        *,
        api_key: str | None = None,
        endpoint: str = "https://api.openai.com/v1/responses",
        timeout: float = 60.0,
        opener: HttpOpener | None = None,
    ) -> None:
        if identity.provider != "openai":
            raise ValueError("OpenAIResponsesAdapter identity.provider must be 'openai'")
        self._identity = identity
        self._api_key = api_key
        self._endpoint = endpoint
        self._timeout = timeout
        self._opener = opener

    @property
    def identity(self) -> ModelIdentity:
        return self._identity

    def _key(self) -> str:
        key = self._api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ModelAdapterError(
                AdapterErrorCode.CONFIGURATION,
                self._identity,
                "OPENAI_API_KEY is not configured",
                retryable=False,
            )
        return key

    @staticmethod
    def _output_text(data: dict[str, Any]) -> str | None:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct:
            return direct
        output = data.get("output")
        if not isinstance(output, list):
            return None
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
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
                "Authorization": f"Bearer {self._key()}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self._identity.model_id,
                "input": request.input_text,
                "max_output_tokens": request.max_output_tokens,
            },
            timeout=self._timeout,
            opener=self._opener,
        )
        text = self._output_text(data)
        if text is None:
            raise ModelAdapterError(
                AdapterErrorCode.INVALID_RESPONSE,
                self._identity,
                "OpenAI response did not contain output text",
                retryable=False,
            )
        status = data.get("status")
        usage = data.get("usage")
        return ModelResponse(
            identity=self._identity,
            output_text=text,
            finish_reason=status if isinstance(status, str) else None,
            provider_request_id=request_id,
            usage=usage if isinstance(usage, dict) else None,
        )
