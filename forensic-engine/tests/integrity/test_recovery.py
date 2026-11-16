import pytest

from wfs_engine import importer
from wfs_engine.analytics import recovery


def test_deletion_indicator_is_reported_as_indicator_only(conn, sample_case):
    result = recovery.analyze(conn, sample_case["id"])
    deletion = [f for f in result["findings"] if f["kind"] == "deleted_message"]
    assert deletion
    assert deletion[0]["status"] == "deletion_indicator"
    # The placeholder text must never be presented as recovered content.
    assert "recovered" not in deletion[0]["summary"].lower()


def test_missing_attachment_detected_for_media_placeholders(conn, sample_case):
    result = recovery.analyze(conn, sample_case["id"])
    missing = [f for f in result["findings"] if f["status"] == "missing_attachment"]
    assert missing
    assert "not present in the imported artifacts" in missing[0]["detail"]["note"]


def test_snapshot_comparison_only_uses_shared_conversations(conn, sample_case, tmp_path):
    first = tmp_path / "one.txt"
    first.write_text("01/05/24, 10:00 - Alice: alpha\n01/05/24, 10:01 - Bob: beta\n",
                     encoding="utf-8")
    # Same participants as ``one.txt``: this is a later snapshot of one chat, not
    # a different conversation.
    second = tmp_path / "two.txt"
    second.write_text("01/05/24, 10:00 - Alice: alpha\n"
                      "01/05/24, 10:02 - Bob: gamma\n", encoding="utf-8")
    unrelated = tmp_path / "three.txt"
    unrelated.write_text("02/05/24, 10:00 - Carol: something else entirely\n",
                         encoding="utf-8")
    for path in (first, second, unrelated):
        importer.import_single_file(conn, sample_case["id"], path,
                                    {"source_timezone": "UTC"})

    comparisons = recovery.compare_snapshots(conn, sample_case["id"])
    assert comparisons
    for comp in comparisons:
        if comp["evidence_a"]["original_name"] == "one.txt" and \
                comp["evidence_b"]["original_name"] == "two.txt":
            assert comp["shared"] == 1
            assert len(comp["only_in_a"]) == 1
            assert comp["only_in_a"][0]["body"] == "beta"
            assert comp["excluded_conversations"]["only_in_a"] == 0
        # Never compares the unrelated conversation.
        for item in comp["only_in_a"] + comp["only_in_b"]:
            assert "something else" not in (item["body"] or "")


def test_ai_interpretation_does_not_change_evidence(conn, sample_case):
    from wfs_engine.ai import assistant

    before = conn.execute("SELECT COUNT(*), SUM(char_count) FROM messages").fetchone()
    answer = assistant.ask(conn, sample_case["id"], "What did they discuss about travel?")
    after = conn.execute("SELECT COUNT(*), SUM(char_count) FROM messages").fetchone()
    assert tuple(before) == tuple(after)
    assert answer["observed"]["stats"]["overview"]["real_messages"] > 0


def test_recovery_analysis_is_idempotent(conn, sample_case):
    first = recovery.analyze(conn, sample_case["id"])
    second = recovery.analyze(conn, sample_case["id"])
    assert len(first["findings"]) == len(second["findings"])


def test_classifications_cover_required_vocabulary():
    required = {
        "recovered_from_evidence", "present_in_earlier_snapshot",
        "deletion_indicator", "missing_attachment", "unverified_discrepancy",
        "not_recoverable",
    }
    assert required <= set(recovery.CLASSIFICATIONS)
