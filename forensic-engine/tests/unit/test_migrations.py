"""Packaged migration lookup and migration-runner guards."""

import sys
from pathlib import Path

import pytest

from wfs_engine import db


def test_frozen_build_reads_bundled_migrations(monkeypatch, tmp_path):
    bundled = tmp_path / "meipass"
    target = bundled / "wfs_engine" / "migrations"
    target.mkdir(parents=True)
    (target / "0001_test.sql").write_text("SELECT 1;", encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(bundled), raising=False)
    assert db.migrations_dir() == target


def test_source_run_reads_package_migrations(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert (db.migrations_dir() / "0001_init.sql").is_file()


def test_missing_migrations_fail_loudly(data_dir, monkeypatch, tmp_path):
    empty = tmp_path / "empty-migrations"
    empty.mkdir()
    monkeypatch.setattr(db, "migrations_dir", lambda: empty)
    with pytest.raises(RuntimeError, match="no SQL migrations"):
        db.migrate()


def test_migration_with_trigger_body_is_rejected():
    with pytest.raises(RuntimeError, match="trigger"):
        db._split_statements(
            "CREATE TRIGGER t AFTER INSERT ON x BEGIN SELECT 1; END;")
