"""Conversation identity must be part of message identity.

Two different chats can legitimately contain the same sender, the same timestamp
and the same text. Treating them as duplicates would silently delete evidence.
"""

from pathlib import Path

from wfs_engine import importer

LINE = "12/10/2024, 10:00 - Alice: identical text in two chats"
GROUP_ONE = ("12/10/2024, 10:00 - Alice: identical text in two chats\n"
             "12/10/2024, 10:01 - Bob: first group only\n")
GROUP_TWO = ("12/10/2024, 10:00 - Alice: identical text in two chats\n"
             "12/10/2024, 10:01 - Carol: second group only\n")


def _import(conn, case_id, files):
    opts = importer.ImportOptions()
    job = importer.create_job(conn, case_id, [str(p) for p in files], opts)
    importer.run_job(job["job_id"])
    row = conn.execute("SELECT status FROM import_jobs WHERE id=?",
                       (job["job_id"],)).fetchone()
    assert row["status"] == "done"


def test_identical_text_in_two_chats_stays_two_messages(conn, case, tmp_path):
    # Alice writes the same words at the same time in two different groups. The
    # participant sets differ, so these are two conversations and two messages.
    first = tmp_path / "project-group.txt"
    second = tmp_path / "family-group.txt"
    first.write_text(GROUP_ONE, encoding="utf-8")
    second.write_text(GROUP_TWO, encoding="utf-8")

    _import(conn, case["id"], [first, second])

    conversations = conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE case_id=?", (case["id"],)).fetchone()[0]
    messages = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE case_id=?", (case["id"],)).fetchone()[0]
    assert conversations == 2
    assert messages == 4

    rows = conn.execute(
        "SELECT conversation_id, content_hash FROM messages"
        " WHERE case_id=? AND body='identical text in two chats'",
        (case["id"],)).fetchall()
    assert len(rows) == 2
    assert len({r["conversation_id"] for r in rows}) == 2
    assert len({r["content_hash"] for r in rows}) == 2


def test_reimport_of_the_same_chat_still_reconciles(conn, case, tmp_path):
    path = tmp_path / "chat-with-alice.txt"
    path.write_text(LINE + "\n", encoding="utf-8")
    _import(conn, case["id"], [path])
    _import(conn, case["id"], [path])

    messages = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE case_id=?", (case["id"],)).fetchone()[0]
    assert messages == 1, "the same chat must reconcile across snapshots"
    observations = conn.execute(
        "SELECT COUNT(*) FROM message_observations o JOIN messages m"
        " ON m.id=o.message_id WHERE m.case_id=?", (case["id"],)).fetchone()[0]
    assert observations >= 1
