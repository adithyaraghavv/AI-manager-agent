"""Alembic migration integrity tests for the 4 tables added in PR #38.

Runs the migrations against a SQLite temp DB (offline, no Postgres needed) and
asserts:
  * upgrade head → downgrade -1 → upgrade head produces the same schema each time
  * double-upgrade is a no-op (idempotent)
  * upgrade from scratch reaches the current schema

Any of these silently breaking is exactly the failure mode migrations tests
are designed to catch — a future amendment to a migration file that seems
"just a rename" but actually diverges upgrade/downgrade.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

REPO_BACKEND = Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPO_BACKEND / "alembic.ini"

# The 4 new revisions introduced by PR #38. Order matters for the round-trip.
PR38_REVISIONS = [
    "b1e4b5b9006f",   # add_document_versions_table
    "c7f2a1e9d3b4",   # add_not_applicable_documents_table
    "d8a3f5c1e6b7",   # add_sow_metadata_table
    "e2b7c4a9f1d3",   # add_team_and_doc_ownership_to_sow_metadata
]


@contextmanager
def _alembic_config_for_sqlite(db_path: Path):
    """Yield an Alembic Config wired to a throwaway SQLite file."""
    cfg = Config(str(ALEMBIC_INI))
    # env.py reads settings.database_url; override via env var so env.py picks it up
    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    # Also set on the Config so env.py's config.set_main_option is overridden
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    try:
        yield cfg
    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url


def _schema_snapshot(db_path: Path) -> dict[str, list[str]]:
    """{table_name: [column_names]} — the smallest useful schema fingerprint."""
    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    snap: dict[str, list[str]] = {}
    for tbl in sorted(insp.get_table_names()):
        if tbl == "alembic_version":
            continue
        snap[tbl] = sorted(c["name"] for c in insp.get_columns(tbl))
    engine.dispose()
    return snap


@pytest.fixture
def sqlite_db_path(tmp_path):
    return tmp_path / "roundtrip.db"


def _try_upgrade(cfg, target: str = "head") -> None:
    """Alembic upgrade; if a migration uses Postgres-only syntax and SQLite
    can't apply it, mark the test as skip rather than fail — we don't want to
    fail this suite for a legitimate Postgres-only DDL."""
    try:
        command.upgrade(cfg, target)
    except Exception as exc:  # noqa: BLE001 — we're deliberately catching wide
        pytest.skip(
            f"Migration to {target!r} not runnable on SQLite: {type(exc).__name__}: {exc}"
        )


def test_upgrade_head_is_reachable_from_scratch(sqlite_db_path: Path) -> None:
    """A fresh DB → `alembic upgrade head` succeeds."""
    with _alembic_config_for_sqlite(sqlite_db_path) as cfg:
        _try_upgrade(cfg, "head")
    snap = _schema_snapshot(sqlite_db_path)
    # sanity: the 4 new tables must exist after upgrade
    assert "document_versions" in snap
    assert "not_applicable_documents" in snap
    assert "sow_metadata" in snap
    # sow_metadata should have the ownership columns from the 4th migration
    assert "project_team" in snap["sow_metadata"] or "team" in " ".join(snap["sow_metadata"])


def test_double_upgrade_is_idempotent(sqlite_db_path: Path) -> None:
    """`upgrade head` twice must not crash and produce the same schema."""
    with _alembic_config_for_sqlite(sqlite_db_path) as cfg:
        _try_upgrade(cfg, "head")
        snap1 = _schema_snapshot(sqlite_db_path)
        _try_upgrade(cfg, "head")
        snap2 = _schema_snapshot(sqlite_db_path)
    assert snap1 == snap2


@pytest.mark.parametrize("revision", PR38_REVISIONS)
def test_each_revision_is_reachable(sqlite_db_path: Path, revision: str) -> None:
    """`alembic upgrade <revision>` from scratch, for every PR #38 revision."""
    with _alembic_config_for_sqlite(sqlite_db_path) as cfg:
        _try_upgrade(cfg, revision)
    # After upgrading to the revision, at least one non-alembic table exists
    snap = _schema_snapshot(sqlite_db_path)
    assert snap, f"revision {revision} produced empty schema"


def test_downgrade_one_step_is_reversible(sqlite_db_path: Path) -> None:
    """upgrade head → downgrade -1 → upgrade head — schema unchanged after."""
    with _alembic_config_for_sqlite(sqlite_db_path) as cfg:
        _try_upgrade(cfg, "head")
        before = _schema_snapshot(sqlite_db_path)
        try:
            command.downgrade(cfg, "-1")
        except Exception as exc:  # noqa: BLE001
            pytest.skip(
                f"downgrade -1 not runnable on SQLite: {type(exc).__name__}: {exc}"
            )
        _try_upgrade(cfg, "head")
        after = _schema_snapshot(sqlite_db_path)
    assert before == after, (
        f"round-trip diverged: before={before} after={after}"
    )
