"""Fail-closed S3-N tool authorization policy.

Evidence/model text is never consulted here. Authority comes only from the
code-owned capability catalog plus the immutable Context Manifest allowlist and
forbidden scopes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class ToolCapabilityClass(str, Enum):
    READ_ONLY_RESEARCH = "READ_ONLY_RESEARCH"
    REALITY_EXECUTION = "REALITY_EXECUTION"


@dataclass(frozen=True)
class ToolCapability:
    name: str
    capability_class: ToolCapabilityClass
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolDecision:
    allowed: bool
    reason: str


class ToolPolicyError(PermissionError):
    """Requested tool authority is not permitted by S3-N."""


class ToolPolicy:
    def __init__(self, capabilities: Sequence[ToolCapability]) -> None:
        by_name: dict[str, ToolCapability] = {}
        for capability in capabilities:
            if not capability.name.strip():
                raise ValueError("tool capability name must be non-empty")
            if capability.name in by_name:
                raise ValueError(f"duplicate tool capability: {capability.name}")
            by_name[capability.name] = capability
        self._capabilities: Mapping[str, ToolCapability] = MappingProxyType(by_name)

    @property
    def capabilities(self) -> Mapping[str, ToolCapability]:
        return self._capabilities

    def decision(
        self,
        tool_name: str,
        *,
        allowed_tools: Sequence[str],
        forbidden_scopes: Sequence[str],
    ) -> ToolDecision:
        capability = self._capabilities.get(tool_name)
        if capability is None:
            return ToolDecision(False, "unknown capability class/tool; fail closed")
        if tool_name not in allowed_tools:
            return ToolDecision(False, "tool is not listed in immutable Context permissions")
        if capability.capability_class is not ToolCapabilityClass.READ_ONLY_RESEARCH:
            return ToolDecision(False, "reality-execution capability is globally denied in V0.1")
        blocked = sorted(set(capability.scopes).intersection(forbidden_scopes))
        if blocked:
            return ToolDecision(False, f"tool intersects forbidden scopes: {', '.join(blocked)}")
        return ToolDecision(True, "explicitly listed read-only research capability")

    def assert_allowed(
        self,
        tool_name: str,
        *,
        allowed_tools: Sequence[str],
        forbidden_scopes: Sequence[str],
    ) -> ToolCapability:
        decision = self.decision(
            tool_name,
            allowed_tools=allowed_tools,
            forbidden_scopes=forbidden_scopes,
        )
        if not decision.allowed:
            raise ToolPolicyError(f"{tool_name}: {decision.reason}")
        return self._capabilities[tool_name]

    def authorize_context(
        self,
        *,
        allowed_tools: Sequence[str],
        forbidden_scopes: Sequence[str],
    ) -> tuple[ToolCapability, ...]:
        return tuple(
            self.assert_allowed(
                tool_name,
                allowed_tools=allowed_tools,
                forbidden_scopes=forbidden_scopes,
            )
            for tool_name in allowed_tools
        )
