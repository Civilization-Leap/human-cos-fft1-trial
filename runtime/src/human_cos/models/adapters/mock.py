"""Deterministic MockAdapter used by S2-L merge-blocking tests."""

from __future__ import annotations

from human_cos.models.errors import ModelAdapterError
from human_cos.models.types import AdapterErrorCode, ModelIdentity, ModelRequest, ModelResponse


class MockAdapter:
    def __init__(
        self,
        identity: ModelIdentity,
        *,
        output_text: str = "mock-response",
        fail_with: AdapterErrorCode | None = None,
        retryable: bool = True,
    ) -> None:
        self._identity = identity
        self._output_text = output_text
        self._fail_with = fail_with
        self._retryable = retryable
        self.calls = 0

    @property
    def identity(self) -> ModelIdentity:
        return self._identity

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self._fail_with is not None:
            raise ModelAdapterError(
                self._fail_with,
                self._identity,
                f"mock adapter failure: {self._fail_with.value}",
                retryable=self._retryable,
            )
        return ModelResponse(
            identity=self._identity,
            output_text=self._output_text,
            finish_reason="mock",
            provider_request_id=f"mock-{self.calls}",
            usage={"max_output_tokens": request.max_output_tokens},
        )
