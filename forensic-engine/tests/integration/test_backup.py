from pathlib import Path

import pytest

from wfs_engine import backup, cases


def test_encrypted_backup_and_restore(conn, sample_case, tmp_path):
    result = backup.create_backup(conn, sample_case["id"], "correct horse battery",
                                  dest=tmp_path / "case.wfsbak")
    raw = Path(result["path"]).read_bytes()
    assert raw.startswith(b"WFSBAKE1")
    # Ciphertext must not contain the plaintext chat text.
    assert b"boat tour" not in raw

    restored = backup.restore_backup(conn, Path(result["path"]),
                                     "correct horse battery")
    new_case = restored["case"]
    assert new_case["id"] != sample_case["id"]
    original_counts = cases.case_counts(conn, sample_case["id"])
    assert original_counts["messages"] > 0
    assert new_case["counts"]["messages"] == original_counts["messages"]

    original = conn.execute(
        "SELECT body FROM messages WHERE case_id=? ORDER BY sent_at_utc LIMIT 5",
        (sample_case["id"],)).fetchall()
    copied = conn.execute(
        "SELECT body FROM messages WHERE case_id=? ORDER BY sent_at_utc LIMIT 5",
        (new_case["id"],)).fetchall()
    assert [r["body"] for r in original] == [r["body"] for r in copied]
    # FTS is rebuilt for the restored case so search keeps working.
    hits = conn.execute("SELECT COUNT(*) FROM messages_fts WHERE case_id=? AND"
                        " messages_fts MATCH '\"hotel\"'", (new_case["id"],)).fetchone()[0]
    assert hits >= 1


def test_wrong_passphrase_fails_cleanly(conn, sample_case, tmp_path):
    result = backup.create_backup(conn, sample_case["id"], "passphrase-one",
                                  dest=tmp_path / "case.wfsbak")
    with pytest.raises(ValueError):
        backup.restore_backup(conn, Path(result["path"]), "passphrase-two")


def test_tampered_backup_is_rejected(conn, sample_case, tmp_path):
    result = backup.create_backup(conn, sample_case["id"], "passphrase-one",
                                  dest=tmp_path / "case.wfsbak")
    data = bytearray(Path(result["path"]).read_bytes())
    data[-40] ^= 0xFF
    Path(result["path"]).write_bytes(bytes(data))
    with pytest.raises(ValueError):
        backup.restore_backup(conn, Path(result["path"]), "passphrase-one")


def test_restore_rejects_non_backup_files(conn, tmp_path):
    bogus = tmp_path / "not-a-backup.bin"
    bogus.write_bytes(b"hello")
    with pytest.raises(ValueError):
        backup.restore_backup(conn, bogus, "whatever")


def test_case_duplicate_copies_evidence_and_annotations(conn, sample_case):
    first_message = conn.execute(
        "SELECT id FROM messages WHERE case_id=? LIMIT 1", (sample_case["id"],)
    ).fetchone()["id"]
    cases.add_bookmark(conn, sample_case["id"], first_message, "key message")
    cases.add_note(conn, sample_case["id"], "Follow up on this thread")

    original_counts = cases.case_counts(conn, sample_case["id"])
    duplicate = cases.duplicate_case(conn, sample_case["id"], "Copy of case")
    assert duplicate["id"] != sample_case["id"]
    assert duplicate["counts"]["messages"] == original_counts["messages"]
    assert duplicate["counts"]["bookmarks"] == 1
    assert duplicate["counts"]["evidence"] == original_counts["evidence"]
