"""Case management: directories, manifests, notes, bookmarks, tags, audit."""
from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

from . import config, db
from .hashing import sha256_text

AUTHORIZATION_TEXT = (
    "I confirm that I am the owner of the imported data or that I have explicit "
    "authorisation to examine it, and that the import was obtained lawfully."
)


def case_dir(case_number: int, case_id: str) -> Path:
    return config.cases_dir() / f"CASE-{case_number:04d}-{case_id[:8]}"


def _scaffold(root: Path) -> None:
    for sub in config.case_subdirs(root):
        (root / sub).mkdir(parents=True, exist_ok=True)


def write_manifest(conn, case_id: str) -> Path:
    case = db.row_to_dict(conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())
    if not case:
        raise KeyError("case not found")
    evidence = db.rows_to_list(conn.execute(
        "SELECT id, original_name, source_type, size_bytes, sha256, imported_at,"
        " message_count FROM evidence_sources WHERE case_id=? ORDER BY imported_at",
        (case_id,)))
    manifest = {
        "schema": "wfs.manifest/1",
        "case": {k: case[k] for k in (
            "id", "case_number", "name", "description", "examiner", "status",
            "authorization_statement", "created_at", "updated_at")},
        "evidence": evidence,
        "counts": {
            "conversations": conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE case_id=?", (case_id,)).fetchone()[0],
            "messages": conn.execute(
                "SELECT COUNT(*) FROM messages WHERE case_id=?", (case_id,)).fetchone()[0],
            "contacts": conn.execute(
                "SELECT COUNT(*) FROM contacts WHERE case_id=?", (case_id,)).fetchone()[0],
            "reports": conn.execute(
                "SELECT COUNT(*) FROM reports WHERE case_id=?", (case_id,)).fetchone()[0],
        },
        "integrity_note": (
            "Originals are stored byte-identical to import and are never modified. "
            "Derived records cite evidence_id + source_ref."),
    }
    path = Path(case["dir_path"]) / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def create_case(conn, name: str, description: str = "", examiner: str = "",
                authorization_statement: str = "") -> dict[str, Any]:
    if not name.strip():
        raise ValueError("case name is required")
    if not authorization_statement.strip():
        authorization_statement = AUTHORIZATION_TEXT
    case_id = db.new_id()
    number = (conn.execute("SELECT COALESCE(MAX(case_number), 0) FROM cases")
              .fetchone()[0] or 0) + 1
    root = case_dir(number, case_id)
    _scaffold(root)
    ts = db.now_utc()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO cases(id, case_number, name, description, examiner, status,"
            " authorization_statement, dir_path, created_at, updated_at)"
            " VALUES(?,?,?,?,?,'active',?,?,?,?)",
            (case_id, number, name.strip(), description.strip(), examiner.strip(),
             authorization_statement.strip(), str(root), ts, ts))
        conn.execute(
            "INSERT INTO case_settings(case_id, json, updated_at) VALUES(?,?,?)",
            (case_id, db.json_dump({"timezone": "UTC", "date_order": "auto"}), ts))
        db.audit(conn, "case.create", case_id, "user", {"name": name, "number": number})
    write_manifest(conn, case_id)
    return get_case(conn, case_id)


def get_case(conn, case_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not row:
        raise KeyError("case not found")
    case = dict(row)
    case["counts"] = case_counts(conn, case_id)
    settings = conn.execute("SELECT json FROM case_settings WHERE case_id=?",
                            (case_id,)).fetchone()
    case["settings"] = db.json_load(settings["json"], {}) if settings else {}
    return case


def case_counts(conn, case_id: str) -> dict[str, int]:
    def scalar(sql: str) -> int:
        return conn.execute(sql, (case_id,)).fetchone()[0] or 0

    return {
        "evidence": scalar("SELECT COUNT(*) FROM evidence_sources WHERE case_id=?"),
        "conversations": scalar("SELECT COUNT(*) FROM conversations WHERE case_id=?"),
        "messages": scalar("SELECT COUNT(*) FROM messages WHERE case_id=?"),
        "contacts": scalar("SELECT COUNT(*) FROM contacts WHERE case_id=?"),
        "groups": scalar("SELECT COUNT(*) FROM conversations WHERE case_id=? AND kind='group'"),
        "attachments": scalar("SELECT COUNT(*) FROM attachments WHERE case_id=?"),
        "bookmarks": scalar("SELECT COUNT(*) FROM bookmarks WHERE case_id=?"),
        "notes": scalar("SELECT COUNT(*) FROM investigation_notes WHERE case_id=?"),
        "reports": scalar("SELECT COUNT(*) FROM reports WHERE case_id=?"),
        "findings": scalar("SELECT COUNT(*) FROM recovery_findings WHERE case_id=?"),
    }


def list_cases(conn, include_archived: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM cases"
    if not include_archived:
        sql += " WHERE status='active'"
    sql += " ORDER BY updated_at DESC"
    out = []
    for row in conn.execute(sql):
        case = dict(row)
        case["counts"] = case_counts(conn, case["id"])
        out.append(case)
    return out


def update_case(conn, case_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    allowed = {"name", "description", "examiner", "status", "authorization_statement"}
    fields = {k: v for k, v in patch.items() if k in allowed}
    if not fields:
        return get_case(conn, case_id)
    sets = ", ".join(f"{k}=?" for k in fields)
    with db.transaction(conn):
        conn.execute(f"UPDATE cases SET {sets}, updated_at=? WHERE id=?",
                     (*fields.values(), db.now_utc(), case_id))
        db.audit(conn, "case.update", case_id, "user", {"fields": sorted(fields)})
    write_manifest(conn, case_id)
    return get_case(conn, case_id)


def touch_case(conn, case_id: str) -> None:
    conn.execute("UPDATE cases SET updated_at=? WHERE id=?", (db.now_utc(), case_id))


def duplicate_case(conn, case_id: str, name: str | None = None) -> dict[str, Any]:
    """Copy a case: evidence files are byte-copied, parsed records are rebuilt
    deterministically, and user annotations are re-linked by content hash."""
    src = get_case(conn, case_id)
    target = create_case(
        conn,
        name=name or f"{src['name']} (copy)",
        description=src["description"],
        examiner=src["examiner"],
        authorization_statement=src["authorization_statement"],
    )
    src_root, dst_root = Path(src["dir_path"]), Path(target["dir_path"])

    evidence_rows = db.rows_to_list(conn.execute(
        "SELECT * FROM evidence_sources WHERE case_id=? ORDER BY imported_at", (case_id,)))
    from . import importer  # local import to avoid a cycle

    for ev in evidence_rows:
        original = Path(ev["stored_path"])
        if not original.is_file():
            continue
        copied = dst_root / "evidence" / "originals" / original.name
        shutil.copy2(original, copied)
        importer.import_single_file(conn, target["id"], copied, {
            "date_order": "auto",
            "source_timezone": json.loads(ev["extra_json"] or "{}").get("timezone", "UTC"),
            "force": True,
            "keep_copy": True,
        })

    # Re-link annotations through content hashes (ids differ between cases).
    mapping = {}
    for row in conn.execute(
            "SELECT id, content_hash FROM messages WHERE case_id=?", (target["id"],)):
        mapping[row["content_hash"]] = row["id"]
    for row in conn.execute(
            "SELECT m.content_hash, b.label, b.created_at FROM bookmarks b"
            " JOIN messages m ON m.id=b.message_id WHERE b.case_id=?", (case_id,)):
        new_mid = mapping.get(row["content_hash"])
        if new_mid:
            conn.execute(
                "INSERT OR IGNORE INTO bookmarks(id, case_id, message_id, label, created_at)"
                " VALUES(?,?,?,?,?)",
                (db.new_id(), target["id"], new_mid, row["label"], row["created_at"]))
    for row in conn.execute(
            "SELECT m.content_hash, t.tag FROM message_tags t JOIN messages m ON m.id=t.message_id"
            " WHERE t.case_id=?", (case_id,)):
        new_mid = mapping.get(row["content_hash"])
        if new_mid:
            conn.execute(
                "INSERT OR IGNORE INTO message_tags(id, case_id, message_id, tag, created_at)"
                " VALUES(?,?,?,?,?)",
                (db.new_id(), target["id"], new_mid, row["tag"], db.now_utc()))
    for row in conn.execute(
            "SELECT body, author, created_at FROM investigation_notes WHERE case_id=?",
            (case_id,)):
        conn.execute(
            "INSERT INTO investigation_notes(id, case_id, message_id, author, body,"
            " created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (db.new_id(), target["id"], None, row["author"], row["body"],
             row["created_at"], db.now_utc()))
    db.audit(conn, "case.duplicate", target["id"], "user", {"source_case": case_id})
    write_manifest(conn, target["id"])
    return get_case(conn, target["id"])


def delete_case(conn, case_id: str, remove_files: bool = False) -> None:
    case = get_case(conn, case_id)
    with db.transaction(conn):
        conn.execute("DELETE FROM messages_fts WHERE case_id=?", (case_id,))
        conn.execute("DELETE FROM cases WHERE id=?", (case_id,))
        db.audit(conn, "case.delete", None, "user", {"case_id": case_id})
    if remove_files:
        shutil.rmtree(case["dir_path"], ignore_errors=True)


# --------------------------------------------------------------------- notes etc.
def add_note(conn, case_id: str, body: str, message_id: str | None = None,
             author: str = "user") -> dict[str, Any]:
    note_id = db.new_id()
    ts = db.now_utc()
    conn.execute(
        "INSERT INTO investigation_notes(id, case_id, message_id, author, body,"
        " created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
        (note_id, case_id, message_id, author, body, ts, ts))
    db.audit(conn, "note.create", case_id, author, {"note_id": note_id})
    return dict(conn.execute("SELECT * FROM investigation_notes WHERE id=?",
                             (note_id,)).fetchone())


def list_notes(conn, case_id: str) -> list[dict[str, Any]]:
    return db.rows_to_list(conn.execute(
        "SELECT n.*, m.body AS message_body, m.sent_at_utc FROM investigation_notes n"
        " LEFT JOIN messages m ON m.id=n.message_id WHERE n.case_id=?"
        " ORDER BY n.created_at DESC", (case_id,)))


def delete_note(conn, case_id: str, note_id: str) -> None:
    conn.execute("DELETE FROM investigation_notes WHERE id=? AND case_id=?", (note_id, case_id))


def add_bookmark(conn, case_id: str, message_id: str, label: str = "") -> dict[str, Any]:
    bid = db.new_id()
    conn.execute(
        "INSERT INTO bookmarks(id, case_id, message_id, label, created_at) VALUES(?,?,?,?,?)"
        " ON CONFLICT(message_id) DO UPDATE SET label=excluded.label",
        (bid, case_id, message_id, label, db.now_utc()))
    db.audit(conn, "bookmark.add", case_id, "user", {"message_id": message_id})
    return dict(conn.execute("SELECT * FROM bookmarks WHERE message_id=?",
                             (message_id,)).fetchone())


def remove_bookmark(conn, case_id: str, message_id: str) -> None:
    conn.execute("DELETE FROM bookmarks WHERE message_id=? AND case_id=?", (message_id, case_id))


def list_bookmarks(conn, case_id: str) -> list[dict[str, Any]]:
    return db.rows_to_list(conn.execute(
        "SELECT b.*, m.body, m.sent_at_utc, m.sender_raw, c.title AS conversation_title"
        " FROM bookmarks b JOIN messages m ON m.id=b.message_id"
        " JOIN conversations c ON c.id=m.conversation_id"
        " WHERE b.case_id=? ORDER BY m.sent_at_utc DESC", (case_id,)))


def add_tag(conn, case_id: str, message_id: str, tag: str) -> dict[str, Any]:
    tag = tag.strip()[:60]
    conn.execute(
        "INSERT OR IGNORE INTO message_tags(id, case_id, message_id, tag, created_at)"
        " VALUES(?,?,?,?,?)", (db.new_id(), case_id, message_id, tag, db.now_utc()))
    return {"message_id": message_id, "tag": tag}


def remove_tag(conn, case_id: str, message_id: str, tag: str) -> None:
    conn.execute("DELETE FROM message_tags WHERE case_id=? AND message_id=? AND tag=?",
                 (case_id, message_id, tag))


def list_tags(conn, case_id: str) -> list[dict[str, Any]]:
    return db.rows_to_list(conn.execute(
        "SELECT tag, COUNT(*) AS count FROM message_tags WHERE case_id=?"
        " GROUP BY tag ORDER BY count DESC", (case_id,)))


def audit_log(conn, case_id: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
    if case_id:
        rows = conn.execute(
            "SELECT * FROM audit_logs WHERE case_id=? OR case_id IS NULL"
            " ORDER BY at DESC LIMIT ?", (case_id, limit))
    else:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY at DESC LIMIT ?", (limit,))
    out = []
    for row in rows:
        entry = dict(row)
        entry["detail"] = db.json_load(entry.pop("detail_json"), {})
        out.append(entry)
    return out


def prune_audit(conn, retention_days: int) -> int:
    cutoff = (db.now_utc()[:10])
    from datetime import date
    keep_from = (date.fromisoformat(cutoff) - timedelta(days=retention_days)).isoformat()
    cur = conn.execute("DELETE FROM audit_logs WHERE substr(at,1,10) < ?", (keep_from,))
    return cur.rowcount or 0


def chain_of_custody(conn, case_id: str) -> list[dict[str, Any]]:
    """Evidence-handling events only, in chronological order."""
    rows = conn.execute(
        "SELECT at, action, detail_json FROM audit_logs WHERE case_id=?"
        " AND (action LIKE 'evidence.%' OR action LIKE 'case.%' OR action LIKE 'report.%')"
        " ORDER BY at", (case_id,))
    return [{**dict(r), "detail": db.json_load(r["detail_json"], {})} for r in rows]


def verify_evidence(conn, case_id: str) -> list[dict[str, Any]]:
    from .hashing import sha256_file
    results = []
    for ev in conn.execute(
            "SELECT * FROM evidence_sources WHERE case_id=?", (case_id,)):
        path = Path(ev["stored_path"])
        if not path.is_file():
            state, actual = "missing", None
        else:
            actual = sha256_file(path)
            state = "ok" if actual == ev["sha256"] else "mismatch"
        conn.execute(
            "INSERT INTO evidence_hashes(id, evidence_id, algo, hash, verified_at, ok, note)"
            " VALUES(?,?,?,?,?,?,?)",
            (db.new_id(), ev["id"], "sha256", actual or ev["sha256"], db.now_utc(),
             1 if state == "ok" else 0, state))
        results.append({
            "evidence_id": ev["id"], "original_name": ev["original_name"],
            "expected_sha256": ev["sha256"], "actual_sha256": actual, "state": state,
        })
    ok = all(r["state"] == "ok" for r in results)
    db.audit(conn, "evidence.verify", case_id, "user",
             {"items": len(results), "all_ok": ok})
    return results


def fingerprint_case(conn, case_id: str) -> str:
    rows = conn.execute(
        "SELECT sha256 FROM evidence_sources WHERE case_id=? ORDER BY id", (case_id,))
    return sha256_text("".join(r["sha256"] for r in rows))
