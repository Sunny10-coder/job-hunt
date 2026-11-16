"""Encrypted case backup and restore.

Backups are AES-256-GCM encrypted with a key derived from the user's passphrase
via scrypt (from the `cryptography` package - no home-grown cryptography). The
archive contains the case directory plus a JSON dump of every case-scoped row.
"""
from __future__ import annotations

import io
import json
import os
import struct
import tarfile
from pathlib import Path
from typing import Any

from . import cases as cases_mod
from . import config, db
from .hashing import sha256_file
from .safety import unique_path

MAGIC = b"WFSBAKE1"

# Upper bound on what a single backup may expand to. Archives are supplied by
# the examiner, but a corrupted or hostile file must not exhaust the disk.
MAX_RESTORE_BYTES = 16 * 1024 ** 3

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    HAVE_CRYPTO = True
except Exception:  # noqa: BLE001
    AESGCM = None  # type: ignore[assignment]
    Scrypt = None  # type: ignore[assignment]
    HAVE_CRYPTO = False

CASE_TABLES: list[tuple[str, dict[str, str | None]]] = [
    ("evidence_sources", {"case_id": None}),
    ("evidence_hashes", {"evidence_id": "evidence_sources"}),
    ("import_jobs", {"case_id": None}),
    ("import_errors", {"case_id": None, "evidence_id": "evidence_sources",
                       "job_id": "import_jobs"}),
    ("contacts", {"case_id": None}),
    ("contact_aliases", {"contact_id": "contacts"}),
    ("conversations", {"case_id": None, "evidence_id": "evidence_sources"}),
    ("conversation_participants", {"conversation_id": "conversations",
                                   "contact_id": "contacts"}),
    ("messages", {"case_id": None, "evidence_id": "evidence_sources",
                  "conversation_id": "conversations", "sender_id": "contacts"}),
    ("message_observations", {"message_id": "messages", "evidence_id": "evidence_sources"}),
    ("message_versions", {"message_id": "messages", "evidence_id": "evidence_sources"}),
    ("message_references", {"message_id": "messages"}),
    ("attachments", {"case_id": None, "evidence_id": "evidence_sources",
                     "message_id": "messages", "conversation_id": "conversations"}),
    ("media_metadata", {"attachment_id": "attachments"}),
    ("audio_transcripts", {"attachment_id": "attachments"}),
    ("group_events", {"case_id": None, "conversation_id": "conversations",
                      "message_id": "messages"}),
    ("message_tags", {"case_id": None, "message_id": "messages"}),
    ("bookmarks", {"case_id": None, "message_id": "messages"}),
    ("investigation_notes", {"case_id": None, "message_id": "messages"}),
    ("saved_searches", {"case_id": None}),
    ("timeline_events", {"case_id": None, "conversation_id": "conversations"}),
    ("analysis_runs", {"case_id": None}),
    ("analysis_results", {"case_id": None}),
    ("ai_queries", {"case_id": None}),
    ("ai_evidence_citations", {"query_id": "ai_queries", "message_id": "messages"}),
    ("recovery_findings", {"case_id": None, "message_id": "messages",
                           "evidence_id": "evidence_sources"}),
    ("reports", {"case_id": None}),
    ("export_jobs", {"case_id": None}),
    ("audit_logs", {"case_id": None}),
]

PATH_COLUMNS = {"stored_path", "relative_path", "path"}


def _derive(password: str, salt: bytes, length: int = 32) -> bytes:
    if not HAVE_CRYPTO:
        raise RuntimeError(
            "the 'cryptography' package is required for encrypted backups; "
            "install it or use an unencrypted case export instead")
    kdf = Scrypt(salt=salt, length=length, n=2 ** 15, r=8, p=1)
    return kdf.derive(password.encode("utf-8"))


def _dump_case(conn, case_id: str, case_root: Path) -> dict[str, Any]:
    dump: dict[str, Any] = {}
    case_row = dict(conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())
    dump["cases"] = [case_row]
    settings_row = conn.execute("SELECT * FROM case_settings WHERE case_id=?",
                                (case_id,)).fetchone()
    dump["case_settings"] = [dict(settings_row)] if settings_row else []
    for table, _fks in CASE_TABLES:
        columns = [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        if "case_id" in columns:
            rows = conn.execute(f'SELECT * FROM "{table}" WHERE case_id=?',
                                (case_id,)).fetchall()
        else:
            # Tables without a direct case column are captured through their parent.
            parent = next((fk for fk in _fks.values() if fk), None)
            if parent is None:
                continue
            ids = [str(r[0]) for r in conn.execute(
                f'SELECT id FROM "{parent}" WHERE case_id=?', (case_id,))]
            if not ids:
                rows = []
            else:
                fk_col = next(k for k, v in _fks.items() if v == parent)
                placeholders = ",".join("?" * len(ids))
                rows = conn.execute(
                    f'SELECT * FROM "{table}" WHERE "{fk_col}" IN ({placeholders})',
                    tuple(ids)).fetchall()
        dump[table] = [dict(r) for r in rows]
    dump["_meta"] = {"case_root": str(case_root), "app": "WhatsApp Forensic Studio AI",
                     "version": config.ENGINE_VERSION}
    return dump


def create_backup(conn, case_id: str, password: str, dest: Path | None = None) -> dict[str, Any]:
    case = cases_mod.get_case(conn, case_id)
    root = Path(case["dir_path"])
    dump = _dump_case(conn, case_id, root)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        payload = json.dumps(dump, ensure_ascii=False, default=str).encode("utf-8")
        info = tarfile.TarInfo("case_rows.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        for file in sorted(root.rglob("*")):
            if file.is_file():
                tar.add(file, arcname=str(Path("case") / file.relative_to(root)))
    plaintext = buffer.getvalue()

    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, MAGIC)
    # A minute-resolution name would let two backups in the same minute
    # overwrite each other; unique_path never returns an existing file.
    out = dest or unique_path(config.data_dir() / "backups",
                              f"{case_id[:8]}-backup", "wfsbak")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(MAGIC + struct.pack(">I", len(salt)))
        fh.write(salt + nonce + ciphertext)
    digest = sha256_file(out)
    db.audit(conn, "case.backup", case_id, "user", {
        "path": str(out), "sha256": digest, "encrypted": True})
    return {"path": str(out), "sha256": digest, "bytes": out.stat().st_size,
            "encrypted": True, "case_id": case_id}


def restore_backup(conn, backup_path: Path, password: str,
                   new_name: str | None = None) -> dict[str, Any]:
    if not HAVE_CRYPTO:
        raise RuntimeError("the 'cryptography' package is required to restore backups")
    raw = Path(backup_path).read_bytes()
    if not raw.startswith(MAGIC):
        raise ValueError("not a WhatsApp Forensic Studio backup file")
    offset = len(MAGIC)
    (salt_len,) = struct.unpack(">I", raw[offset:offset + 4])
    offset += 4
    salt = raw[offset:offset + salt_len]
    offset += salt_len
    nonce = raw[offset:offset + 12]
    offset += 12
    ciphertext = raw[offset:]
    key = _derive(password, salt)
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, MAGIC)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("decryption failed: wrong passphrase or corrupted backup") from exc

    # Stage every member in memory first: nothing is written to the case
    # directory until the whole archive has been validated.
    buffer = io.BytesIO(plaintext)
    rows_json: dict[str, Any] | None = None
    staged: dict[str, bytes] = {}
    total = 0
    with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "case_rows.json":
                handle = tar.extractfile(member)
                if handle is not None:
                    rows_json = json.loads(handle.read().decode("utf-8"))
                continue
            if not member.name.startswith("case/") or not member.isfile():
                continue
            rel = Path(member.name).relative_to("case")
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(
                    f"archive member escapes the case directory: {member.name}")
            handle = tar.extractfile(member)
            data = handle.read() if handle is not None else b""
            if len(data) != member.size:
                raise ValueError(f"archive member is truncated: {member.name}")
            total += len(data)
            if total > MAX_RESTORE_BYTES:
                raise ValueError(
                    f"backup expands beyond the {MAX_RESTORE_BYTES // (1024 ** 3)} GiB "
                    "restore limit")
            staged[str(rel)] = data

    if rows_json is None:
        raise ValueError("backup archive is missing its data manifest")
    if not rows_json.get("cases"):
        raise ValueError("backup contains no case record")

    source_case = rows_json["cases"][0]
    new_case = cases_mod.create_case(
        conn,
        name=new_name or f"{source_case['name']} (restored)",
        description=source_case.get("description", ""),
        examiner=source_case.get("examiner", ""),
        authorization_statement=source_case.get("authorization_statement", ""),
    )
    root = Path(new_case["dir_path"])

    # All-or-nothing: any failure removes the half-built case (rows and files)
    # so a partial restore can never be mistaken for a complete one.
    try:
        for rel, data in staged.items():
            target = (root / rel).resolve()
            if root.resolve() not in target.parents:
                raise ValueError(f"refusing to write outside the case directory: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        old_root = rows_json["_meta"]["case_root"]
        inserted = _reinsert(conn, rows_json, new_case["id"], old_root, str(root))
        _verify_restore(rows_json, inserted)
        cases_mod.write_manifest(conn, new_case["id"])
    except Exception:
        cases_mod.delete_case(conn, new_case["id"], remove_files=True)
        raise

    db.audit(conn, "case.restore", new_case["id"], "user", {
        "backup": str(backup_path), "source_case": source_case["id"],
        "files": len(staged), "bytes": total})
    return {"case": cases_mod.get_case(conn, new_case["id"]),
            "source_case_id": source_case["id"], "restored_files": len(staged)}


def _verify_restore(dump: dict[str, Any], inserted: dict[str, int]) -> None:
    """Prove every dumped row was inserted before reporting success.

    Counts come from ``_reinsert`` itself, so rows created afterwards (audit
    entries, derived timeline events) cannot mask a missing record.
    """
    mismatches: list[str] = []
    for table, rows in dump.items():
        if table in ("_meta", "cases") or not rows:
            continue
        if inserted.get(table, 0) != len(rows):
            mismatches.append(f"{table}: {inserted.get(table, 0)} of {len(rows)}")
    if mismatches:
        raise RuntimeError("restore verification failed: " + ", ".join(mismatches))


def _reinsert(conn, dump: dict[str, Any], new_case_id: str, old_root: str,
              new_root: str) -> dict[str, int]:
    """Insert every dumped row under a new case id, remapping all primary keys.

    Any failed insert aborts the whole restore. Returns per-table insert counts
    so the caller can verify completeness.
    """
    id_maps: dict[str, dict[str, str]] = {}
    inserted: dict[str, int] = {}

    def map_id(table: str, value: str | None) -> str | None:
        if value is None:
            return None
        return id_maps.get(table, {}).get(value)

    ordered = [("evidence_sources",), ("import_jobs",), ("contacts",),
               ("conversations",), ("messages",), ("attachments",),
               ("analysis_runs",), ("ai_queries",)]
    dump_order = [t for (t,) in ordered] + [t for t, _ in CASE_TABLES
                                            if t not in {x for (x,) in ordered}]

    for table in dump_order:
        rows = dump.get(table) or []
        if not rows:
            continue
        columns = [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        fks = dict(CASE_TABLES).get(table, {})
        id_map: dict[str, str] = {}
        for row in rows:
            new_row = {k: v for k, v in row.items() if k in columns}
            old_id = new_row.get("id")
            if old_id:
                id_map[old_id] = db.new_id()
                new_row["id"] = id_map[old_id]
            for fk, parent in fks.items():
                if fk not in new_row:
                    continue
                if parent is None:
                    new_row[fk] = new_case_id
                else:
                    new_row[fk] = map_id(parent, new_row.get(fk))
            for column in PATH_COLUMNS & set(new_row):
                value = new_row.get(column)
                if isinstance(value, str) and old_root and value.startswith(old_root):
                    new_row[column] = value.replace(old_root, new_root, 1)
            cols = ",".join(f'"{c}"' for c in new_row)
            marks = ",".join("?" * len(new_row))
            try:
                conn.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({marks})',
                             tuple(new_row.values()))
            except Exception as exc:  # noqa: BLE001 - abort the whole restore
                raise RuntimeError(
                    f"restore failed inserting into {table}: {exc}") from exc
            inserted[table] = inserted.get(table, 0) + 1
        id_maps[table] = id_map

    # Case settings are keyed by the case id instead of an ``id`` column, so they
    # are restored explicitly here (previously they were silently dropped).
    for row in dump.get("case_settings") or []:
        conn.execute(
            "INSERT OR REPLACE INTO case_settings(case_id, json, updated_at)"
            " VALUES(?,?,?)",
            (new_case_id, row.get("json") or "{}",
             row.get("updated_at") or db.now_utc()))
        inserted["case_settings"] = inserted.get("case_settings", 0) + 1

    # Case-level row: replace the restored id with the freshly created case.
    conn.execute("UPDATE cases SET description=?, examiner=? WHERE id=?",
                 (dump["cases"][0].get("description", ""),
                  dump["cases"][0].get("examiner", ""), new_case_id))
    # Rebuild the FTS index for restored messages.
    conn.execute("DELETE FROM messages_fts WHERE case_id=?", (new_case_id,))
    conn.execute(
        "INSERT INTO messages_fts(message_id, case_id, body, sender, conversation)"
        " SELECT m.id, m.case_id, m.body, m.sender_raw, c.title FROM messages m"
        " JOIN conversations c ON c.id=m.conversation_id WHERE m.case_id=?",
        (new_case_id,))
    from . import importer

    importer.finalize_case(conn, new_case_id)
    return inserted
