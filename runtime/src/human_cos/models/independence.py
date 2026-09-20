"""Identity-level independence facts for S2-L."""

from __future__ import annotations

from human_cos.models.types import IdentityIndependence, ModelIdentity


def compare_identity_independence(
    left: ModelIdentity,
    right: ModelIdentity,
) -> IdentityIndependence:
    return IdentityIndependence(
        model_family=left.model_family != right.model_family,
        provider=left.provider != right.provider,
    )
