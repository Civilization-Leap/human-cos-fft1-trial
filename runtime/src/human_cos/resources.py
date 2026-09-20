"""Access Human-COS runtime resources from source checkouts or installed wheels.

Repository-root contract files remain the canonical signed originals.  Files
under ``human_cos/_resources`` are byte-identical distribution transport copies
used when a repository checkout is unavailable (for example, a normal wheel
installation).
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RESOURCE_ROOT_NAME = "_resources"


def repository_root() -> Path:
    """Return the source-checkout root inferred from this module location."""
    return _REPO_ROOT


def _safe_parts(relative_path: str) -> tuple[str, ...]:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"runtime resource path must be relative and contained: {relative_path!r}")
    return tuple(part for part in path.parts if part not in ("", "."))


def source_resource_path(relative_path: str) -> Path | None:
    """Return a canonical repository-root resource path when it exists."""
    candidate = _REPO_ROOT.joinpath(*_safe_parts(relative_path))
    return candidate if candidate.is_file() else None


def bundled_resource(relative_path: str) -> Any:
    """Return an importlib Traversable for a packaged distribution resource."""
    node = resources.files("human_cos").joinpath(_RESOURCE_ROOT_NAME)
    for part in _safe_parts(relative_path):
        node = node.joinpath(part)
    return node


def read_runtime_resource_bytes(relative_path: str, *, prefer_source: bool = True) -> bytes:
    """Read a resource, preferring canonical source bytes when requested."""
    if prefer_source:
        source = source_resource_path(relative_path)
        if source is not None:
            return source.read_bytes()
    node = bundled_resource(relative_path)
    if not node.is_file():
        raise FileNotFoundError(f"Human-COS packaged resource not found: {relative_path}")
    return cast(bytes, node.read_bytes())


def read_runtime_resource_text(relative_path: str, *, prefer_source: bool = True) -> str:
    return read_runtime_resource_bytes(relative_path, prefer_source=prefer_source).decode("utf-8")


def list_runtime_resources(
    relative_dir: str,
    *,
    suffix: str,
    prefer_source: bool = True,
) -> list[Any]:
    """List matching resources from the source tree or installed distribution."""
    parts = _safe_parts(relative_dir)
    if prefer_source:
        source_dir = _REPO_ROOT.joinpath(*parts)
        if source_dir.is_dir():
            return sorted(source_dir.glob(f"*{suffix}"), key=lambda item: item.name)

    node = bundled_resource(relative_dir)
    if not node.is_dir():
        return []
    return sorted(
        [child for child in node.iterdir() if child.is_file() and child.name.endswith(suffix)],
        key=lambda item: item.name,
    )
