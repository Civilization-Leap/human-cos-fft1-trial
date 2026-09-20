"""Deterministic in-memory Model Registry for S2-L.

This registry records already-approved model profile facts. It does not invent
qualification thresholds, schedule work, or decide Human-COS process state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from human_cos.models.errors import IdentityMismatchError, RegistryError, UnknownModelError
from human_cos.models.profile import ModelProfile
from human_cos.models.types import ModelIdentity


class ModelRegistry:
    def __init__(self, profiles: Iterable[ModelProfile]) -> None:
        by_id: dict[str, ModelProfile] = {}
        for profile in profiles:
            if profile.model_id in by_id:
                raise RegistryError(f"duplicate model_id: {profile.model_id}")
            by_id[profile.model_id] = profile
        self._profiles: Mapping[str, ModelProfile] = MappingProxyType(by_id)

    @property
    def profiles(self) -> Mapping[str, ModelProfile]:
        return self._profiles

    def get(self, model_id: str) -> ModelProfile:
        try:
            return self._profiles[model_id]
        except KeyError as exc:
            raise UnknownModelError(f"unknown model_id: {model_id}") from exc

    def assert_identity(self, identity: ModelIdentity) -> ModelProfile:
        profile = self.get(identity.model_id)
        if profile.provider != identity.provider or profile.model_family != identity.model_family:
            raise IdentityMismatchError(
                "adapter identity does not match registered provider/model_family "
                f"for {identity.model_id}"
            )
        return profile
