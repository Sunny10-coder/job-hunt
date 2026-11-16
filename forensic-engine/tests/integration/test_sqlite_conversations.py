"""Accessible database import must reconstruct real conversations.

The importer previously put every row of a database into one conversation named
after the file and assigned confidence 1.0 to every row. Both are wrong: a
database holds many chats, and readable bytes are not the same as fully
understood semantics.
"""

import sqlite3
from pathlib import Path

from wfs_engine import importer
from wfs_engine.parsers import sqlite_wa


def _build_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE message (_id INTEGER PRIMARY KEY, key_remote_jid TEXT,"
        " from_me INTEGER, timestamp INTEGER, data TEXT, media_wa_type INTEGER,"
        " remote_resource TEXT)")
    con.execute("CREATE TABLE chat (jid TEXT, subject TEXT)")
    con.executemany("INSERT INTO chat(jid, subject) VALUES(?,?)", [
        ("111@s.whatsapp.net", "Alice"),
        ("222@g.us", "Project Group"),
    ])
    rows = [
        # Alice, 1:1 chat
        ("111@s.whatsapp.net", 1, 1728727200000, "hello alice", 0, None),
        ("111@s.whatsapp.net", 0, 1728727260000, "hi", 0, None),
        ("111@s.whatsapp.net", 1, 1728727320000, "same words", 0, None),
        # group chat, two participants plus the owner
        ("222@g.us", 0, 1728727200000, "group one", 0, "333@s.whatsapp.net"),
        ("222@g.us", 0, 1728727260000, "group two", 0, "444@s.whatsapp.net"),
        # second 1:1 chat with an identical (sender, time, text) pair
        ("555@s.whatsapp.net", 1, 1728727320000, "same words", 0, None),
    ]
    con.executemany(
        "INSERT INTO message(key_remote_jid, from_me, timestamp, data, media_wa_type,"
        " remote_resource) VALUES(?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def test_conversations_come_from_the_database_not_the_filename(conn, case, tmp_path):
    db_file = _build_db(tmp_path / "msgstore.db")
    opts = importer.ImportOptions()
    job = importer.create_job(conn, case["id"], [str(db_file)], opts)
    importer.run_job(job["job_id"])
    status = conn.execute("SELECT status FROM import_jobs WHERE id=?",
                          (job["job_id"],)).fetchone()
    assert status["status"] == "done"

    conversations = conn.execute(
        "SELECT title, kind FROM conversations WHERE case_id=? ORDER BY title",
        (case["id"],)).fetchall()
    titles = {r["title"]: r["kind"] for r in conversations}
    assert titles == {"Alice": "chat", "Project Group": "group",
                      "555@s.whatsapp.net": "chat"}

    total = conn.execute("SELECT COUNT(*) FROM messages WHERE case_id=?",
                         (case["id"],)).fetchone()[0]
    assert total == 6

    # Identical text/time/sender in different chats stays two messages.
    same = conn.execute(
        "SELECT COUNT(DISTINCT conversation_id) AS chats FROM messages"
        " WHERE case_id=? AND body='same words'", (case["id"],)).fetchone()
    assert same["chats"] == 2

    # Group senders are participants, not the group JID.
    group_senders = {r["sender_raw"] for r in conn.execute(
        "SELECT m.sender_raw FROM messages m JOIN conversations c"
        " ON c.id=m.conversation_id WHERE m.case_id=? AND c.kind='group'",
        (case["id"],))}
    assert group_senders == {"333@s.whatsapp.net", "444@s.whatsapp.net"}


def test_readable_rows_do_not_get_perfect_confidence(conn, case, tmp_path):
    db_file = _build_db(tmp_path / "msgstore.db")
    job = importer.create_job(conn, case["id"], [str(db_file)],
                              importer.ImportOptions())
    importer.run_job(job["job_id"])
    scores = [r["parse_confidence"] for r in conn.execute(
        "SELECT parse_confidence FROM messages WHERE case_id=?", (case["id"],))]
    assert scores
    assert max(scores) <= sqlite_wa.BASE_CONFIDENCE < 1.0

    evidence = conn.execute(
        "SELECT notes FROM evidence_sources WHERE case_id=?", (case["id"],)).fetchone()
    assert evidence is not None


def test_database_without_timestamps_is_rejected_with_a_reason(tmp_path):
    path = tmp_path / "unknown.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE message (_id INTEGER PRIMARY KEY, data TEXT)")
    con.commit()
    con.close()
    info = sqlite_wa.inspect_db(path)
    assert info.supported is False
    assert info.reason


def test_database_without_conversation_identity_is_rejected(tmp_path):
    path = tmp_path / "single.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE message (_id INTEGER PRIMARY KEY, timestamp INTEGER,"
                " data TEXT)")
    con.commit()
    con.close()
    info = sqlite_wa.inspect_db(path)
    assert info.supported is False
    assert "conversation" in info.reason
