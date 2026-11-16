import shutil
from pathlib import Path

import pytest

from wfs_engine import cases, importer, samples
from wfs_engine.hashing import sha256_file


def import_file(conn, case, path: Path, **opts):
    return importer.import_single_file(conn, case["id"], path,
                                       {"source_timezone": "UTC", "date_order": "auto", **opts})


def test_original_evidence_is_never_modified(conn, case, tmp_path):
    source = tmp_path / "WhatsApp Chat with Test.txt"
    source.write_text(samples.DEMO_CHAT, encoding="utf-8")
    before = sha256_file(source)
    mtime_before = source.stat().st_mtime_ns

    evidence = import_file(conn, case, source)

    assert sha256_file(source) == before
    assert source.stat().st_mtime_ns == mtime_before
    stored = Path(evidence["stored_path"])
    assert stored.is_file()
    assert sha256_file(stored) == before


def test_evidence_hash_recorded_and_verifiable(conn, case, tmp_path):
    source = tmp_path / "chat.txt"
    source.write_text(samples.DEMO_CHAT, encoding="utf-8")
    evidence = import_file(conn, case, source)

    results = cases.verify_evidence(conn, case["id"])
    assert results[0]["state"] == "ok"
    assert results[0]["actual_sha256"] == evidence["sha256"]

    # Tamper with the stored copy: verification must fail loudly.
    Path(evidence["stored_path"]).write_text("tampered", encoding="utf-8")
    results = cases.verify_evidence(conn, case["id"])
    assert results[0]["state"] == "mismatch"


def test_reimport_of_identical_file_is_refused(conn, case, tmp_path):
    source = tmp_path / "chat.txt"
    source.write_text(samples.DEMO_CHAT, encoding="utf-8")
    first = import_file(conn, case, source)
    second = import_file(conn, case, source)
    assert second["skipped"] is True
    assert second["id"] == first["id"]
    assert conn.execute("SELECT COUNT(*) FROM evidence_sources").fetchone()[0] == 1


def test_identical_messages_are_both_kept(conn, case, tmp_path):
    source = tmp_path / "dupes.txt"
    source.write_text(
        "01/05/24, 10:00 - Alice: ok\n"
        "01/05/24, 10:00 - Alice: ok\n"
        "01/05/24, 10:01 - Alice: ok\n", encoding="utf-8")
    import_file(conn, case, source)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 3


def test_same_message_in_two_exports_is_one_record_two_observations(conn, case, tmp_path):
    first = tmp_path / "export-1.txt"
    first.write_text("01/05/24, 10:00 - Alice: hello\n01/05/24, 10:05 - Bob: hi\n",
                     encoding="utf-8")
    second = tmp_path / "export-2.txt"
    second.write_text("01/05/24, 10:00 - Alice: hello\n"
                      "01/05/24, 10:05 - Bob: hi\n"          # duplicate
                      "01/06/24, 09:00 - Alice: later message\n", encoding="utf-8")
    import_file(conn, case, first)
    import_file(conn, case, second)

    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert total == 3
    observations = conn.execute(
        "SELECT COUNT(*) FROM message_observations").fetchone()[0]
    assert observations == 5
    duplicated = conn.execute(
        "SELECT COUNT(*) FROM (SELECT message_id FROM message_observations"
        " GROUP BY message_id HAVING COUNT(*) > 1)").fetchone()[0]
    assert duplicated == 2


def test_provenance_and_timestamps_are_preserved(conn, case, tmp_path):
    source = tmp_path / "chat.txt"
    source.write_text("31/12/2023, 23:59 - Priya: Good night\n", encoding="utf-8")
    import_file(conn, case, source)

    row = dict(conn.execute("SELECT * FROM messages").fetchone())
    assert row["original_timestamp"].startswith("31/12/2023")
    assert row["sent_at_local"] == "2023-12-31T23:59:00"
    assert row["sent_at_utc"] == "2023-12-31T23:59:00Z"
    assert row["source_ref"].endswith(":1")
    assert row["evidence_id"] == conn.execute(
        "SELECT id FROM evidence_sources").fetchone()[0]
    assert row["parse_confidence"] >= 0.9


def test_timezone_is_applied_without_altering_original(conn, case, tmp_path):
    source = tmp_path / "chat.txt"
    source.write_text("25/01/2024, 10:00 - Alice: timezone test\n", encoding="utf-8")
    import_file(conn, case, source, source_timezone="Asia/Kolkata")
    row = dict(conn.execute("SELECT * FROM messages").fetchone())
    assert row["original_timestamp"] == "25/01/2024 10:00"
    assert row["sent_at_local"] == "2024-01-25T10:00:00"
    assert row["sent_at_utc"] == "2024-01-25T04:30:00Z"
    assert row["tz_offset_min"] == 330


def test_duplicate_handling_is_deterministic(conn, case, tmp_path):
    source = tmp_path / "chat.txt"
    source.write_text(samples.DEMO_CHAT, encoding="utf-8")
    import_file(conn, case, source)
    hashes_first = [r[0] for r in conn.execute(
        "SELECT content_hash FROM messages ORDER BY content_hash")]

    other = cases.create_case(conn, "Second case")
    import_file(conn, other, source)
    hashes_second = [r[0] for r in conn.execute(
        "SELECT content_hash FROM messages WHERE case_id=? ORDER BY content_hash",
        (other["id"],))]
    assert hashes_first == hashes_second


def test_zip_import_extracts_media_without_linking_guesses(conn, case, tmp_path):
    sample_dir = tmp_path / "samples"
    info = samples.write_sample_files(sample_dir)
    zip_path = Path(info["primary"])
    import_file(conn, case, zip_path)

    attachments = [dict(r) for r in conn.execute(
        "SELECT file_name, linked, missing FROM attachments")]
    assert attachments, "media files from the archive must be registered"
    # WhatsApp text exports do not name media files, so nothing is auto-linked.
    assert all(a["linked"] == 0 for a in attachments)
    assert all(a["missing"] == 0 for a in attachments)


def test_malformed_evidence_is_recorded_not_crashing(conn, case, tmp_path):
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"PK\x03\x04not really a zip")
    with pytest.raises(Exception):
        import_file(conn, case, bad)


def test_unknown_source_type_is_rejected(conn, case, tmp_path):
    noise = tmp_path / "noise.bin"
    noise.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(ValueError):
        import_file(conn, case, noise)


def test_group_events_and_contacts_are_linked(conn, case, tmp_path):
    source = tmp_path / "WhatsApp Chat - Group.txt"
    source.write_text(samples.DEMO_GROUP, encoding="utf-8")
    import_file(conn, case, source)
    kinds = {r["event_type"] for r in conn.execute("SELECT event_type FROM group_events")}
    assert "group_created" in kinds
    assert "participant_removed" in kinds
    assert conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] >= 3
    conv = conn.execute("SELECT kind FROM conversations").fetchone()
    assert conv["kind"] == "group"
