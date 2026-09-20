"""Provider-neutral S2-L ModelAdapter contract."""

from __future__ import annotations

from typing import Protocol

from human_cos.models.types import ModelIdentity, ModelRequest, ModelResponse


class ModelAdapter(Protocol):
    @property
    def identity(self) -> ModelIdentity: ...

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Invoke exactly this configured model.

        Adapters never select a fallback, change Human-COS process state, or
        obtain reality-execution tool authority.
        """
        ...
