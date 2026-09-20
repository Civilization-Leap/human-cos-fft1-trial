"""Actor/role visibility and temporal admissibility rules for S1."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from .models import Case, Evidence, Visibility

VisibilityBasis = Literal["PUBLIC", "ACTOR", "ROLE"]


def visibility_basis(
    visibility: Visibility,
    *,
    actor_id: str | None,
    role_id: str | None,
) -> VisibilityBasis | None:
    """Return the deterministic ACL basis; deny by default."""
    if visibility.public:
        return "PUBLIC"
    if actor_id is not None and actor_id in visibility.actor_ids:
        return "ACTOR"
    if role_id is not None and role_id in visibility.role_ids:
        return "ROLE"
    return None


def visibility_allows(
    visibility: Visibility,
    *,
    actor_id: str | None,
    role_id: str | None,
) -> bool:
    return visibility_basis(visibility, actor_id=actor_id, role_id=role_id) is not None


def temporal_allows(case: Case, evidence: Evidence, *, as_of: datetime) -> bool:
    """Enforce time as a data boundary for every Case mode.

    Historical blind evaluation always uses Case T0 and admits only PRE_T0
    evidence. ``LATER_VERIFICATION_OF_PRE_T0_FACT`` remains useful for later
    verification stages but cannot enter the clean T0 worker world.
    """
    cutoff = case.time_boundary.T0 if case.case_mode == "HISTORICAL_BLIND_EVAL" else as_of

    if case.case_mode == "HISTORICAL_BLIND_EVAL" and evidence.temporal_class != "PRE_T0":
        return False

    if evidence.source_timestamp > cutoff:
        return False
    if evidence.available_from > cutoff:
        return False
    if evidence.available_until is not None and evidence.available_until < cutoff:
        return False

    # For live/scenario runs, evidence must also have entered the Runtime by the
    # reference time. Historical blind packs are intentionally ingested later,
    # so their present-day ingestion timestamp is not compared to historical T0.
    if case.case_mode != "HISTORICAL_BLIND_EVAL" and evidence.ingested_at > cutoff:
        return False

    return True


def context_allows(
    case: Case,
    evidence: Evidence,
    *,
    actor_id: str | None,
    role_id: str | None,
    as_of: datetime,
) -> bool:
    if evidence.case_id != case.case_id:
        return False
    return temporal_allows(case, evidence, as_of=as_of) and visibility_allows(
        evidence.visibility, actor_id=actor_id, role_id=role_id
    )
