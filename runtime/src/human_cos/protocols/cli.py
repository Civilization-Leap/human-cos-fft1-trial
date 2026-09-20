"""``human-cos-protocols`` CLI.

``load`` and ``snapshot`` accept an explicit registry path.  When omitted they
operate on the byte-identical Protocol Registry bundled with the installed
Human-COS distribution, so a repository checkout is not required.
"""

from __future__ import annotations

import argparse
import sys
from typing import cast

from human_cos.resources import read_runtime_resource_text

from .registry import ProtocolRegistryError, load_protocol_registry

_BUNDLED_REGISTRY = "protocols/protocol_registry_v0.1.yaml"


def _registry_source(registry_path: str | None) -> str:
    if registry_path is not None:
        return registry_path
    return cast(str, read_runtime_resource_text(_BUNDLED_REGISTRY, prefer_source=False))


def _cmd_load(registry_path: str | None) -> int:
    try:
        registry = load_protocol_registry(_registry_source(registry_path))
    except (ProtocolRegistryError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"registry_version={registry.version} status={registry.status}")
    print(f"change_control={registry.change_control}")
    for entry in registry.protocols:
        tests = ",".join(entry.merge_blocking_tests)
        print(f"  {entry.id}@{entry.version} [{entry.status}] AT{{{tests}}}")
    return 0


def _cmd_snapshot(registry_path: str | None) -> int:
    try:
        registry = load_protocol_registry(_registry_source(registry_path))
    except (ProtocolRegistryError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for entry in registry.protocols:
        print(f"{entry.id}@{entry.version}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="human-cos-protocols")
    sub = parser.add_subparsers(dest="command", required=True)
    p_load = sub.add_parser("load", help="load and validate a protocol registry")
    p_load.add_argument("path", nargs="?", help="registry path; defaults to packaged V0.1 registry")
    p_snap = sub.add_parser("snapshot", help="print a stable id@version snapshot")
    p_snap.add_argument("path", nargs="?", help="registry path; defaults to packaged V0.1 registry")
    args = parser.parse_args(argv)

    if args.command == "load":
        return _cmd_load(args.path)
    if args.command == "snapshot":
        return _cmd_snapshot(args.path)
    parser.error(f"unknown command {args.command}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
