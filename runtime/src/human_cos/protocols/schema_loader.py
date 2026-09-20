"""Loader for the JSON Schemas bundled with Human-COS.

The repository-root ``schemas/`` directory remains the canonical source of truth.
Installed distributions use byte-identical transport copies under
``human_cos/_resources/schemas`` so validation does not depend on a repository
checkout.
"""

from __future__ import annotations

import calendar
import json
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from human_cos.resources import list_runtime_resources, read_runtime_resource_text

_RFC3339_DATETIME = re.compile(
    r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])-(?P<day>\d{2})"
    r"[Tt](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?"
    r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$",
    re.ASCII,
)
_FORMAT_CHECKER = FormatChecker()
_FormatPredicate = Callable[[object], bool]
_FormatRegistrar = Callable[[str], Callable[[_FormatPredicate], _FormatPredicate]]
_REGISTER_FORMAT = cast(_FormatRegistrar, _FORMAT_CHECKER.checks)


def _is_rfc3339_datetime(value: object) -> bool:
    """Validate the RFC3339 date-time shape used by the frozen S0 schemas."""
    if not isinstance(value, str):
        return True
    match = _RFC3339_DATETIME.fullmatch(value)
    if match is None:
        return False
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    if year == 0:
        return False
    return 1 <= day <= calendar.monthrange(year, month)[1]


_REGISTER_FORMAT("date-time")(_is_rfc3339_datetime)


class SchemaNotFoundError(FileNotFoundError):
    """Raised when a requested schema is unavailable."""


@cache
def load_json_schema(name: str) -> dict[str, Any]:
    """Load a schema by filename, or from an explicit absolute path."""
    path = Path(name)
    if path.is_absolute():
        if not path.exists():
            raise SchemaNotFoundError(f"schema not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            return cast("dict[str, Any]", json.load(fh))

    try:
        text = read_runtime_resource_text(f"schemas/{path.name}")
    except FileNotFoundError as exc:
        raise SchemaNotFoundError(f"schema {name!r} not found") from exc
    return cast("dict[str, Any]", json.loads(text))


def list_schema_files() -> list[Any]:
    """Return all bundled/canonical schema resources, sorted by filename."""
    return cast(list[Any], list_runtime_resources("schemas", suffix=".schema.json"))


@cache
def _registry() -> Registry:
    """Build a local registry for relative schema references without network I/O."""
    registered: dict[str, Resource] = {}
    for entry in list_schema_files():
        resource = Resource.from_contents(load_json_schema(entry.name))
        registered[entry.name] = resource
        if isinstance(entry, Path):
            registered[entry.resolve().as_uri()] = resource
    return Registry().with_resources(registered.items())


def validator_for(name: str) -> Draft202012Validator:
    schema = load_json_schema(name)
    return Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=_FORMAT_CHECKER,
    )


def validate_instance(instance: dict[str, Any], name: str) -> list[str]:
    errors = sorted(validator_for(name).iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '.'}: {e.message}" for e in errors]
