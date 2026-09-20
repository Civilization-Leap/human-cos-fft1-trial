"""Semantic version helpers for the Protocol Registry.

Human-COS treats protocol versions as contract versions.  A version must be
strictly comparable and may only move forward without an RFC-blessed change.
This module keeps the parsing logic in one place so the rest of the codebase
cannot silently diverge on what a "version" means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")

# Allow future versions to grow segment counts, but require at least one dot
# ("1" alone is not a valid protocol version) and forbid a leading "+" or
# pre-release decorations.  V0.1-style registry uses "0.1".
_MIN_SEGMENTS = 2


@dataclass(frozen=True, order=True)
class ProtocolVersion:
    """Parsed, comparable protocol version (e.g. ``0.1``, ``2.4.1``)."""

    segments: tuple[int, ...]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return ".".join(str(s) for s in self.segments)


class InvalidVersionError(ValueError):
    """Raised when a version string cannot be parsed as a protocol version."""


def parse_version(value: object) -> ProtocolVersion:
    """Parse a version string into a comparable :class:`ProtocolVersion`.

    Raises :class:`InvalidVersionError` for empty, non-numeric, negative, or
    too-short versions.  This is deliberately strict: a malformed version in
    the registry is a contract hazard, not a cosmetic issue.
    """
    if not isinstance(value, str) or not value.strip():
        raise InvalidVersionError(f"protocol version must be a non-empty string, got {value!r}")

    text = value.strip()
    if not _VERSION_RE.match(text):
        raise InvalidVersionError(
            f"protocol version {value!r} must be dot-separated non-negative integers"
        )

    parts = text.split(".")
    if len(parts) < _MIN_SEGMENTS:
        raise InvalidVersionError(
            f"protocol version {value!r} must have at least {_MIN_SEGMENTS} segments (e.g. '0.1')"
        )

    try:
        segments = tuple(int(p) for p in parts)
    except ValueError as exc:  # pragma: no cover - guarded by regex
        msg = f"protocol version {value!r} contains non-integer segments"
        raise InvalidVersionError(msg) from exc

    return ProtocolVersion(segments)


def version_ge(a: str, b: str) -> bool:
    """Return True if protocol version ``a`` >= ``b``."""
    return parse_version(a) >= parse_version(b)


def version_gt(a: str, b: str) -> bool:
    """Return True if protocol version ``a`` > ``b``."""
    return parse_version(a) > parse_version(b)
