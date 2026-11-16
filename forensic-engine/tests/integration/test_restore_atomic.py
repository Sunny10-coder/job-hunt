"""Restore must be all-or-nothing.

The previous implementation created the case, wrote files and then continued
after row-insert failures, leaving a case that looked restored but was not.
"""

import os
from pathlib import Path

import pytest

from wfs_engine import backup


def _case_dirs(sample_case) -> set[str]:
    root = Path(sample_case["dir_path"]).parent
    return {p.name for p in root.iterdir() if p.is_dir()}


def test_failed_row_insert_removes_the_half_built_case(conn, sample_case, tmp_path,
                                                       monkeypatch):
    result = backup.create_backup(conn, sample_case["id"], "pw",
                                  dest=tmp_path / "case.wfsbak")
    before_cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    before_dirs = _case_dirs(sample_case)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated insert failure")

    monkeypatch.setattr(backup, "_reinsert", boom)
    with pytest.raises(RuntimeError):
        backup.restore_backup(conn, Path(result["path"]), "pw")

    assert conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == before_cases
    assert _case_dirs(sample_case) == before_dirs
    assert os.path.isdir(sample_case["dir_path"])


def test_row_count_mismatch_aborts_the_restore(conn, sample_case, tmp_path,
                                               monkeypatch):
    result = backup.create_backup(conn, sample_case["id"], "pw",
                                  dest=tmp_path / "case.wfsbak")
    before_cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]

    def short_restore(*args, **kwargs):
        return {}  # behaves like a restore that silently inserted nothing

    monkeypatch.setattr(backup, "_reinsert", short_restore)
    with pytest.raises(RuntimeError, match="verification failed"):
        backup.restore_backup(conn, Path(result["path"]), "pw")
    assert conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == before_cases


def test_successful_restore_reports_verified_file_count(conn, sample_case, tmp_path):
    result = backup.create_backup(conn, sample_case["id"], "pw",
                                  dest=tmp_path / "case.wfsbak")
    restored = backup.restore_backup(conn, Path(result["path"]), "pw")
    assert restored["restored_files"] >= 1
    assert restored["case"]["counts"]["messages"] > 0
