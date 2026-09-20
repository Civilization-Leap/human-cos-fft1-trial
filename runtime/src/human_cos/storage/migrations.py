"""Deterministic SQL migration runner for Human-COS S1 through S8-EVAL."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from psycopg import Connection

from human_cos.resources import read_runtime_resource_text

_MIGRATION_ROOT = Path(__file__).resolve().parents[3] / "migrations"

_S1_FORWARD_NAME = "0001_s1_case_evidence.sql"
_S1_ROLLBACK_NAME = "0001_s1_case_evidence.rollback.sql"
_S3_FORWARD_NAME = "0002_s3_run_runtime.sql"
_S3_ROLLBACK_NAME = "0002_s3_run_runtime.rollback.sql"
_S4_FORWARD_NAME = "0003_s4_validation_lab.sql"
_S4_ROLLBACK_NAME = "0003_s4_validation_lab.rollback.sql"
_S5_FORWARD_NAME = "0004_s5_cognitive_subjects.sql"
_S5_ROLLBACK_NAME = "0004_s5_cognitive_subjects.rollback.sql"
_S6_FORWARD_NAME = "0005_s6_world_integration.sql"
_S6_ROLLBACK_NAME = "0005_s6_world_integration.rollback.sql"
_S7_FORWARD_NAME = "0006_s7_scenario_challenger_safety.sql"
_S7_ROLLBACK_NAME = "0006_s7_scenario_challenger_safety.rollback.sql"
_S8_FORWARD_NAME = "0007_s8_evaluation.sql"
_S8_ROLLBACK_NAME = "0007_s8_evaluation.rollback.sql"


def _migration_sql(name: str) -> str:
    source = _MIGRATION_ROOT / name
    if source.is_file():
        return source.read_text(encoding="utf-8")
    return cast(str, read_runtime_resource_text(f"migrations/{name}", prefer_source=False))


def apply_s1_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S1_FORWARD_NAME))
    connection.commit()


def rollback_s1_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S1_ROLLBACK_NAME))
    connection.commit()


def apply_s3_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S3_FORWARD_NAME))
    connection.commit()


def rollback_s3_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S3_ROLLBACK_NAME))
    connection.commit()


def apply_s4_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S4_FORWARD_NAME))
    connection.commit()


def rollback_s4_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S4_ROLLBACK_NAME))
    connection.commit()


def apply_s5_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S5_FORWARD_NAME))
    connection.commit()


def rollback_s5_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S5_ROLLBACK_NAME))
    connection.commit()


def apply_s6_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S6_FORWARD_NAME))
    connection.commit()


def rollback_s6_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S6_ROLLBACK_NAME))
    connection.commit()


def apply_s7_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S7_FORWARD_NAME))
    connection.commit()


def rollback_s7_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S7_ROLLBACK_NAME))
    connection.commit()


def apply_s8_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S8_FORWARD_NAME))
    connection.commit()


def rollback_s8_migration(connection: Connection[Any]) -> None:
    connection.execute(_migration_sql(_S8_ROLLBACK_NAME))
    connection.commit()
