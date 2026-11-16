"""Evidence import: hashing, safe copying, parsing, indexing and provenance.

Original evidence is copied byte-for-byte and never modified afterwards. Every
parsed record carries the evidence id plus a source reference (file:line, or
database row) so a finding can always be traced back to the artifact.
"""
from __future__ import annotations

import mimetypes
import shutil
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import cases as cases_mod
from . import config, db, textutil
from .hashing import message_fingerprint, sha256_file
from .parsers import archive, detect, sqlite_wa
from .parsers.whatsapp_txt import ParsedMessage, WhatsAppTxtParser

BATCH_SIZE = 1000
MEDIA_TYPES = {
    "image": "image", "video": "video", "audio": "audio", "document": "document",
}
PLACEHOLDER_MEDIA_TYPE = {
    "image": "image", "video": "video", "audio": "audio", "sticker": "image",
    "gif": "video", "document": "document", "contact_card": "document",
}


class ImportCancelled(Exception):
    pass


@dataclass
class ImportOptions:
    date_order: str = "auto"
    source_timezone: str = "UTC"
    force: bool = False
    keep_copy: bool = True
    self_names: tuple[str, ...] = ("You",)
    tags: list[str] = field(default_factory=list)
    license_acknowledged: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ImportOptions":
        data = data or {}
        return cls(
            date_order=data.get("date_order", "auto"),
            source_timezone=data.get("source_timezone", "UTC") or "UTC",
            force=bool(data.get("force", False)),
            keep_copy=bool(data.get("keep_copy", True)),
            tags=list(data.get("tags") or []),
            license_acknowledged=bool(data.get("license_acknowledged", False)),
        )


def _safe_stem(name: str) -> str:
    return archive._safe_name(name)


# --------------------------------------------------------------------- job control
def create_job(conn, case_id: str, paths: Iterable[str],
               options: ImportOptions) -> dict[str, Any]:
    """Register an import job without starting it (callers then run_job)."""
    case = cases_mod.get_case(conn, case_id)
    resolved = [str(Path(p).expanduser().resolve()) for p in paths]
    if not resolved:
        raise ValueError("no files selected")
    job_id = db.new_id()
    payload = {
        "paths": resolved,
        "date_order": options.date_order,
        "source_timezone": options.source_timezone,
        "force": options.force,
        "keep_copy": options.keep_copy,
        "tags": options.tags,
        "license_acknowledged": options.license_acknowledged,
    }
    conn.execute(
        "INSERT INTO import_jobs(id, case_id, status, stage, progress, options_json,"
        " created_at, log_json) VALUES(?,?,'queued','queued',0,?,?,'[]')",
        (job_id, case_id, db.json_dump(payload), db.now_utc()))
    conn.execute("UPDATE cases SET updated_at=? WHERE id=?", (db.now_utc(), case_id))
    return {"job_id": job_id, "case_id": case["id"], "status": "queued",
            "files_total": len(resolved)}


def start_import(conn, case_id: str, paths: Iterable[str],
                 options: ImportOptions) -> dict[str, Any]:
    """Register a job and process it on a worker thread."""
    job = create_job(conn, case_id, paths, options)
    thread = threading.Thread(target=run_job, args=(job["job_id"],), daemon=True,
                              name=f"import-{job['job_id'][:8]}")
    thread.start()
    return job


def _log(conn, job_id: str, stage: str, message: str) -> None:
    row = conn.execute("SELECT log_json FROM import_jobs WHERE id=?", (job_id,)).fetchone()
    entries = db.json_load(row["log_json"], []) if row else []
    entries.append({"at": db.now_utc(), "stage": stage, "message": message})
    conn.execute("UPDATE import_jobs SET log_json=? WHERE id=?",
                 (db.json_dump(entries[-200:]), job_id))


def _progress(conn, job_id: str, progress: float, stage: str) -> None:
    conn.execute("UPDATE import_jobs SET progress=?, stage=? WHERE id=?",
                 (max(0.0, min(1.0, progress)), stage, job_id))


def _check_cancel(conn, job_id: str) -> None:
    row = conn.execute("SELECT status FROM import_jobs WHERE id=?", (job_id,)).fetchone()
    if row and row["status"] == "cancelled":
        raise ImportCancelled()


def cancel_job(conn, job_id: str) -> dict[str, Any]:
    conn.execute("UPDATE import_jobs SET status='cancelled', stage='cancelled'"
                 " WHERE id=? AND status IN ('queued','running')", (job_id,))
    return get_job(conn, job_id)


def get_job(conn, job_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise KeyError("job not found")
    job = dict(row)
    job["options"] = db.json_load(job.pop("options_json"), {})
    job["log"] = db.json_load(job.pop("log_json"), [])
    job["errors"] = db.rows_to_list(conn.execute(
        "SELECT severity, code, message, line_no FROM import_errors WHERE job_id=?"
        " ORDER BY rowid LIMIT 200", (job_id,)))
    return job


def run_job(job_id: str) -> None:
    """Synchronous import execution. Called from a worker thread or by tests."""
    with db.session() as conn:
        job = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        # Guard against double execution: only a queued job may start.
        if not job or job["status"] != "queued":
            return
        opts = ImportOptions.from_dict(db.json_load(job["options_json"], {}))
        payload = db.json_load(job["options_json"], {})
        paths = [Path(p) for p in payload.get("paths", [])]
        case_id = job["case_id"]
        conn.execute("UPDATE import_jobs SET status='running', started_at=?, stage='starting'"
                     " WHERE id=?", (db.now_utc(), job_id))
        failed = False
        try:
            for index, path in enumerate(paths):
                _check_cancel(conn, job_id)
                base = index / max(1, len(paths))
                span = 1 / max(1, len(paths))
                _progress(conn, job_id, base, f"importing {path.name}")
                try:
                    import_single_file(conn, case_id, path, {
                        "date_order": opts.date_order,
                        "source_timezone": opts.source_timezone,
                        "force": opts.force,
                        "j_tags": opts.tags,
                        "job_id": job_id,
                        "progress_base": base,
                        "progress_span": span,
                    })
                except ImportCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001 - one bad file must not abort the batch
                    failed = True
                    _record_error(conn, job_id, case_id, None, "error",
                                  "import_failed", f"{path.name}: {exc}", None,
                                  traceback.format_exc(limit=3))
                    _log(conn, job_id, "error", f"{path.name}: {exc}")
            _check_cancel(conn, job_id)
            _progress(conn, job_id, 0.98, "finalising")
            finalize_case(conn, case_id)
            _progress(conn, job_id, 1.0, "done")
            conn.execute(
                "UPDATE import_jobs SET status=?, finished_at=?, stage='done' WHERE id=?",
                ("failed" if failed else "done", db.now_utc(), job_id))
            cases_mod.write_manifest(conn, case_id)
        except ImportCancelled:
            conn.execute("UPDATE import_jobs SET status='cancelled', finished_at=?"
                         " WHERE id=?", (db.now_utc(), job_id))
        except Exception as exc:  # noqa: BLE001
            conn.execute(
                "UPDATE import_jobs SET status='failed', finished_at=?, error=? WHERE id=?",
                (db.now_utc(), str(exc)[:2000], job_id))
            _record_error(conn, job_id, case_id, None, "error", "job_failed",
                          str(exc)[:2000], None, traceback.format_exc(limit=6))


def _record_error(conn, job_id: str | None, case_id: str, evidence_id: str | None,
                  severity: str, code: str, message: str, line_no: int | None,
                  raw: str | None) -> None:
    conn.execute(
        "INSERT INTO import_errors(id, job_id, case_id, evidence_id, severity, code,"
        " message, line_no, raw) VALUES(?,?,?,?,?,?,?,?,?)",
        (db.new_id(), job_id, case_id, evidence_id, severity, code, message[:4000],
         line_no, (raw or "")[:4000]))


# -------------------------------------------------------------------- single file
def import_single_file(conn, case_id: str, path: Path, opts: dict[str, Any] | None = None,
                       ) -> dict[str, Any]:
    opts = opts or {}
    case = cases_mod.get_case(conn, case_id)
    root = Path(case["dir_path"])
    job_id = opts.get("job_id")
    tz = opts.get("source_timezone") or "UTC"
    job_tag = f"job:{job_id}" if job_id else "direct"

    sniff = detect.sniff(path)
    if sniff.source_type == "unknown":
        raise ValueError(f"Unsupported or unrecognised source: {sniff.detail}")

    if sniff.source_type == "case_package":
        raise ValueError(
            "Case packages are restored through Case Management → Restore, not imported")

    # 1. Copy original byte-for-byte, then verify the copy.
    source_hash = sha256_file(path)
    existing = conn.execute(
        "SELECT * FROM evidence_sources WHERE case_id=? AND sha256=?",
        (case_id, source_hash)).fetchone()
    if existing and not opts.get("force"):
        _record_error(conn, job_id, case_id, existing["id"], "info", "already_imported",
                      f"{path.name} was already imported as evidence "
                      f"{existing['id'][:8]}. Nothing was re-imported.", None, None)
        return {**dict(existing), "skipped": True}

    keep_copy = opts.get("keep_copy", True)
    if keep_copy:
        originals = root / "evidence" / "originals"
        originals.mkdir(parents=True, exist_ok=True)
        stored = originals / f"{source_hash[:12]}_{_safe_stem(path.name)}"
        if not stored.exists():
            tmp = stored.with_name(f"{stored.name}.{db.new_id()[:8]}.part")
            shutil.copy2(path, tmp)
            if sha256_file(tmp) != source_hash:
                tmp.unlink(missing_ok=True)
                raise ValueError("copy verification failed - evidence was not stored")
            tmp.replace(stored)
        stored_path = stored
    else:
        stored_path = path.resolve()

    evidence_id = db.new_id()
    ts = db.now_utc()
    extra = {"sniff": sniff.detail, "timezone": tz, "media_linked": 0,
             "media_unlinked": 0, "duplicates": 0, "unresolved_lines": 0,
             "ambiguous_timestamps": 0, "encoding": None}
    conn.execute(
        "INSERT INTO evidence_sources(id, case_id, original_name, stored_path, source_type,"
        " size_bytes, sha256, imported_at, status, extra_json) VALUES(?,?,?,?,?,?,?,?,'parsing',?)",
        (evidence_id, case_id, path.name, str(stored_path), sniff.source_type,
         stored_path.stat().st_size, source_hash, ts, db.json_dump(extra)))
    conn.execute(
        "INSERT INTO evidence_hashes(id, evidence_id, algo, hash, verified_at, ok, note)"
        " VALUES(?,?,?,?,?,1,'ingest')",
        (db.new_id(), evidence_id, "sha256", source_hash, ts))
    db.audit(conn, "evidence.import", case_id, "user", {
        "evidence_id": evidence_id, "file": path.name, "sha256": source_hash,
        "source_type": sniff.source_type, "job": job_tag})
    _log(conn, job_id, "hash", f"{path.name} sha256={source_hash[:16]}…") if job_id else None

    try:
        if sniff.source_type == "whatsapp_zip":
            stats = _import_zip(conn, case, evidence_id, stored_path, opts, job_id)
        elif sniff.source_type == "whatsapp_txt":
            stats = _import_chat_file(conn, case, evidence_id, stored_path, opts,
                                     title_hint=path.stem, job_id=job_id)
        elif sniff.source_type == "sqlite":
            stats = _import_sqlite(conn, case, evidence_id, stored_path, opts, job_id)
        else:
            stats = _import_standalone_media(conn, case, evidence_id, stored_path,
                                             sniff.media_type or "document", opts)
    except ImportCancelled:
        conn.execute("UPDATE evidence_sources SET status='cancelled' WHERE id=?",
                     (evidence_id,))
        raise
    except Exception as exc:
        conn.execute("UPDATE evidence_sources SET status='failed', notes=? WHERE id=?",
                     (str(exc)[:1000], evidence_id))
        raise

    extra.update(stats.pop("extra", {}))
    stats_extra = extra
    conn.execute(
        "UPDATE evidence_sources SET status='imported', message_count=?, language=?,"
        " date_order=?, date_order_confidence=?, parse_confidence=?, extra_json=? WHERE id=?",
        (stats.get("message_count", 0), stats.get("language", "unknown"),
         stats.get("date_order", "n/a"), stats.get("date_order_confidence", 0.0),
         stats.get("parse_confidence", 1.0), db.json_dump(stats_extra), evidence_id))

    if job_id:
        _log(conn, job_id, "done",
             f"{path.name}: {stats.get('message_count', 0)} messages, "
             f"{stats_extra.get('duplicates', 0)} duplicates skipped")
        base = float(opts.get("progress_base", 0.0))
        span = float(opts.get("progress_span", 1.0))
        _progress(conn, job_id, base + span * 0.9, f"parsed {path.name}")

    row = conn.execute("SELECT * FROM evidence_sources WHERE id=?", (evidence_id,)).fetchone()
    result = dict(row)
    result["skipped"] = False
    return result


def _import_chat_file(conn, case, evidence_id: str, txt_path: Path,
                      opts: dict[str, Any], title_hint: str,
                      job_id: str | None = None,
                      media_files: list[Path] | None = None) -> dict[str, Any]:
    tz = opts.get("source_timezone") or "UTC"
    parser = WhatsAppTxtParser(timezone_name=tz, date_order=opts.get("date_order", "auto"))
    label = f"evidence:{evidence_id[:8]}/{txt_path.name}"

    # Conversation is created up-front from the file name so messages can be
    # inserted in a single streaming pass.
    title = parser._conversation_title(Path(title_hint), "")
    conv_id = _upsert_conversation(conn, case["id"], evidence_id, title, "chat")
    contact_cache: dict[str, str] = {}
    ordinals: dict[tuple[str, str, str], int] = {}
    buffer: list[ParsedMessage] = []
    counts = {"messages": 0, "duplicates": 0, "system": 0, "media": 0, "unresolved": 0}
    seen_senders: set[str] = set()

    for msg in parser.parse_file(txt_path, source_label=label):
        if job_id and counts["messages"] % 2000 == 0:
            _check_cancel(conn, job_id)
        seen_senders.add(msg.sender_raw)
        buffer.append(msg)
        counts["messages"] += 1
        if msg.group_event:
            _add_group_event(conn, case["id"], conv_id, msg)
        if len(buffer) >= BATCH_SIZE:
            inserted, dups = _flush(conn, case["id"], evidence_id, conv_id,
                                    buffer, contact_cache, ordinals, opts.get("tags") or [])
            counts["duplicates"] += dups
            buffer.clear()
    if buffer:
        _, dups = _flush(conn, case["id"], evidence_id, conv_id, buffer, contact_cache,
                         ordinals, opts.get("tags") or [])
        counts["duplicates"] += dups

    kind = "group" if parser.stats.is_group else "chat"
    conn.execute("UPDATE conversations SET kind=?, chat_identifier=? WHERE id=?",
                 (kind, None, conv_id))

    linked = 0
    if media_files:
        linked = _link_media(conn, case, evidence_id, conv_id, media_files)

    stats = parser.stats
    for issue in stats.issues[:200]:
        _record_error(conn, job_id, case["id"], evidence_id, issue.severity, issue.code,
                      issue.message, issue.line_no, issue.raw)
    return {
        "message_count": counts["messages"] - counts["duplicates"],
        "language": stats.language,
        "date_order": stats.date_order,
        "date_order_confidence": stats.date_order_confidence,
        "parse_confidence": 0.98 if stats.unresolved_lines == 0 else 0.9,
        "conversation_id": conv_id,
        "extra": {
            "duplicates": counts["duplicates"],
            "unresolved_lines": stats.unresolved_lines,
            "ambiguous_timestamps": stats.ambiguous_timestamps,
            "encoding": stats.encoding,
            "system_messages": stats.system_messages,
            "media_messages": stats.media_messages,
            "deleted_markers": stats.deleted_messages,
            "edited_markers": stats.edited_messages,
            "multiline_messages": stats.multiline_messages,
            "participants": len(seen_senders),
            "media_linked": linked,
            "date_order_reason": (
                "proven from observed day/month values" if stats.date_order_confidence >= 0.9
                else "assumed - verify timestamps"),
        },
    }


def _import_zip(conn, case, evidence_id: str, zip_path: Path, opts: dict[str, Any],
                job_id: str | None) -> dict[str, Any]:
    root = Path(case["dir_path"])
    dest = root / "evidence" / "extracted" / evidence_id[:8]
    ok, problems = archive.inspect_archive(zip_path)
    if not ok:
        raise archive.UnsafeArchiveError("; ".join(problems[:4]))
    report = archive.extract(zip_path, dest)
    _log(conn, job_id, "extract", f"{len(report.files)} files extracted") if job_id else None

    texts: list[Path] = []
    media: list[Path] = []
    for item in report.files:
        sniff = detect.sniff(item.path)
        if sniff.source_type == "whatsapp_txt" and item.path.suffix.lower() in (".txt", ".text"):
            texts.append(item.path)
        elif sniff.source_type in ("image", "video", "audio", "document"):
            media.append(item.path)

    if not texts:
        raise ValueError("archive contains no WhatsApp text export")

    combined = {"message_count": 0, "duplicates": 0, "media_linked": 0,
                "unresolved_lines": 0, "ambiguous_timestamps": 0}
    language = "unknown"
    order = "n/a"
    conf = 0.0
    for txt in texts:
        stats = _import_chat_file(conn, case, evidence_id, txt, opts,
                                 title_hint=_zip_chat_title(zip_path, txt), job_id=job_id,
                                 media_files=media)
        combined["message_count"] += stats["message_count"]
        combined["duplicates"] += stats["extra"].get("duplicates", 0)
        combined["media_linked"] += stats["extra"].get("media_linked", 0)
        combined["unresolved_lines"] += stats["extra"].get("unresolved_lines", 0)
        combined["ambiguous_timestamps"] += stats["extra"].get("ambiguous_timestamps", 0)
        language = stats["language"] if language == "unknown" else language
        order = stats["date_order"]
        conf = stats["date_order_confidence"]
    unlinked = _register_unlinked_media(conn, case, evidence_id, media)
    return {
        "message_count": combined["message_count"],
        "language": language,
        "date_order": order,
        "date_order_confidence": conf,
        "parse_confidence": 0.95 if combined["unresolved_lines"] == 0 else 0.88,
        "extra": {
            "archive_entries": report.entry_count,
            "archive_bytes": report.total_bytes,
            "archive_skipped": len(report.skipped),
            "duplicates": combined["duplicates"],
            "media_linked": combined["media_linked"],
            "media_unlinked": unlinked,
            "unresolved_lines": combined["unresolved_lines"],
            "ambiguous_timestamps": combined["ambiguous_timestamps"],
        },
    }


def _zip_chat_title(zip_path: Path, txt: Path) -> str:
    base = zip_path.stem
    base = base.replace("WhatsApp Chat with", "").replace("WhatsApp Chat -", "")
    if base.strip() and base.strip() != zip_path.stem:
        return base.strip()
    return txt.stem


def _import_sqlite(conn, case, evidence_id: str, db_path: Path, opts: dict[str, Any],
                   job_id: str | None) -> dict[str, Any]:
    info = sqlite_wa.inspect_db(db_path)
    if not info.supported:
        raise ValueError(f"Unsupported database: {info.reason}")
    label = f"evidence:{evidence_id[:8]}/{db_path.name}"
    title = db_path.stem
    conv_id = _upsert_conversation(conn, case["id"], evidence_id, title, "chat")
    tz = opts.get("source_timezone") or "UTC"
    contact_cache: dict[str, str] = {}
    count = 0
    for record in sqlite_wa.iter_messages(db_path, label, tz):
        sender = record["sender_raw"]
        sender_id = _contact_id(conn, case["id"], sender, contact_cache)
        mid = db.new_id()
        body = record["body"] or ""
        content_hash = message_fingerprint(record["sent_at_utc"], sender, body)
        exists = conn.execute(
            "SELECT id FROM messages WHERE case_id=? AND content_hash=?",
            (case["id"], content_hash)).fetchone()
        if exists:
            _observe(conn, exists["id"], evidence_id, record["source_ref"], content_hash)
            continue
        conn.execute(
            "INSERT INTO messages(id, case_id, evidence_id, conversation_id, sender_id,"
            " sender_raw, original_timestamp, sent_at_local, sent_at_utc, tz_offset_min,"
            " tz_ambiguous, raw_text, body, message_type, source_ref, parse_confidence,"
            " content_hash, imported_at, word_count, char_count)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, case["id"], evidence_id, conv_id, sender_id, sender,
             record["original_timestamp"], record["sent_at_local"], record["sent_at_utc"],
             record["tz_offset_min"], int(record["tz_ambiguous"]), record["raw_text"],
             body, record["message_type"], record["source_ref"], 1.0, content_hash,
             db.now_utc(), record["word_count"], record["char_count"]))
        conn.execute(
            "INSERT INTO messages_fts(message_id, case_id, body, sender, conversation)"
            " VALUES(?,?,?,?,?)", (mid, case["id"], body, sender, title))
        _observe(conn, mid, evidence_id, record["source_ref"], content_hash)
        count += 1
        if count % 2000 == 0 and job_id:
            _check_cancel(conn, job_id)
    if job_id:
        _log(conn, job_id, "parse", f"{db_path.name}: {count} rows read")
    return {"message_count": count, "language": "unknown", "date_order": "n/a",
            "date_order_confidence": 0.0, "parse_confidence": 1.0,
            "conversation_id": conv_id, "extra": {"sqlite_rows": count}}


def _import_standalone_media(conn, case, evidence_id: str, path: Path,
                             media_type: str, opts: dict[str, Any]) -> dict[str, Any]:
    _register_attachment(conn, case, evidence_id, path, None, media_type)
    return {"message_count": 0, "language": "n/a", "date_order": "n/a",
            "date_order_confidence": 0.0, "parse_confidence": 1.0,
            "extra": {"standalone_media": 1, "media_unlinked": 1}}


# ------------------------------------------------------------------ record helpers
def _upsert_conversation(conn, case_id: str, evidence_id: str, title: str,
                         kind: str) -> str:
    row = conn.execute(
        "SELECT id FROM conversations WHERE case_id=? AND title=? AND kind=?",
        (case_id, title, kind)).fetchone()
    if row:
        return row["id"]
    other = conn.execute(
        "SELECT id, kind FROM conversations WHERE case_id=? AND title=?",
        (case_id, title)).fetchone()
    if other:
        return other["id"]
    conv_id = db.new_id()
    conn.execute(
        "INSERT INTO conversations(id, case_id, title, kind, evidence_id, message_count,"
        " media_count) VALUES(?,?,?,?,?,0,0)",
        (conv_id, case_id, title, kind, evidence_id))
    return conv_id


def _contact_id(conn, case_id: str, name: str, cache: dict[str, str],
                is_self: bool | None = None) -> str:
    if name in cache:
        return cache[name]
    row = conn.execute("SELECT id FROM contacts WHERE case_id=? AND display_name=?",
                       (case_id, name)).fetchone()
    if row:
        cache[name] = row["id"]
        return row["id"]
    cid = db.new_id()
    if is_self is None:
        is_self = name.strip().lower() in {"you", "me", "self"}
    conn.execute(
        "INSERT INTO contacts(id, case_id, display_name, is_self) VALUES(?,?,?,?)",
        (cid, case_id, name, 1 if is_self else 0))
    cache[name] = cid
    return cid


def _observe(conn, message_id: str, evidence_id: str, source_ref: str,
             body_hash: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO message_observations(id, message_id, evidence_id,"
        " source_ref, observed_at, body_hash) VALUES(?,?,?,?,?,?)",
        (db.new_id(), message_id, evidence_id, source_ref, db.now_utc(), body_hash))


def _flush(conn, case_id: str, evidence_id: str, conv_id: str,
           buffer: list[ParsedMessage], contact_cache: dict[str, str],
           ordinals: dict[tuple[str, str, str], int], tags: list[str]) -> tuple[int, int]:
    """Insert one batch, deduplicating by content fingerprint."""
    conv_title = conn.execute("SELECT title FROM conversations WHERE id=?",
                              (conv_id,)).fetchone()["title"]
    hashes: list[str] = []
    for msg in buffer:
        key = (msg.sent_at_utc, msg.sender_raw, msg.body)
        ordinals[key] = ordinals.get(key, 0) + 1
        msg.content_hash = message_fingerprint(
            msg.sent_at_utc, msg.sender_raw, msg.body, str(ordinals[key]))
        hashes.append(msg.content_hash)

    existing: dict[str, dict[str, Any]] = {}
    for chunk_start in range(0, len(hashes), 300):
        chunk = hashes[chunk_start:chunk_start + 300]
        placeholders = ",".join("?" * len(chunk))
        for row in conn.execute(
                f"SELECT id, content_hash, body, sent_at_utc, sender_raw FROM messages"
                f" WHERE case_id=? AND content_hash IN ({placeholders})",
                (case_id, *chunk)):
            existing[row["content_hash"]] = dict(row)

    ts = db.now_utc()
    inserted = duplicates = 0
    rows: list[tuple] = []
    fts_rows: list[tuple] = []
    new_ids: list[tuple[str, str]] = []   # (message_id, body) for tagging
    pending_refs: list[tuple] = []        # inserted after the message rows exist
    pending_obs: list[tuple] = []         # observations need the message row first
    for msg, content_hash in zip(buffer, hashes):
        hit = existing.get(content_hash)
        if hit:
            duplicates += 1
            _observe(conn, hit["id"], evidence_id, msg.source_ref, content_hash)
            if hit["body"] != msg.body:
                _add_version(conn, hit["id"], msg.body, evidence_id)
            continue
        mid = db.new_id()
        sender_id = _contact_id(conn, case_id, msg.sender_raw or "(system)",
                                contact_cache) if msg.sender_raw else None
        rows.append((
            mid, case_id, evidence_id, conv_id, sender_id, msg.sender_raw,
            msg.original_timestamp, msg.sent_at_local, msg.sent_at_utc,
            msg.tz_offset_min, int(msg.tz_ambiguous), msg.raw_text, msg.body,
            msg.message_type, int(msg.is_system), int(msg.is_deleted),
            int(msg.is_edited), int(msg.is_forwarded), int(msg.has_media),
            msg.media_ref, msg.source_ref, msg.parse_confidence, content_hash,
            ts, msg.word_count, msg.char_count, msg.session_id))
        fts_rows.append((mid, case_id, msg.body, msg.sender_raw, conv_title))
        new_ids.append((mid, msg.body))
        inserted += 1
        pending_obs.append((db.new_id(), mid, evidence_id, msg.source_ref, ts, content_hash))
        for ref_type, values in (("url", msg.urls), ("email", msg.emails),
                                 ("phone", msg.phones)):
            for value in values[:5]:
                pending_refs.append((db.new_id(), mid, ref_type, value[:500]))

    if rows:
        # One commit per batch: with autocommit connections each statement would
        # otherwise pay its own WAL commit, which dominated import time.
        with db.batch(conn):
            conn.executemany(
                "INSERT INTO messages(id, case_id, evidence_id, conversation_id, sender_id,"
            " sender_raw, original_timestamp, sent_at_local, sent_at_utc, tz_offset_min,"
            " tz_ambiguous, raw_text, body, message_type, is_system, is_deleted, is_edited,"
            " is_forwarded, has_media, media_ref, source_ref, parse_confidence, content_hash,"
            " imported_at, word_count, char_count, session_id)"
            " VALUES(" + ",".join("?" * 27) + ")", rows)
            conn.executemany(
                "INSERT INTO messages_fts(message_id, case_id, body, sender, conversation)"
                " VALUES(?,?,?,?,?)", fts_rows)
            if pending_refs:
                conn.executemany(
                    "INSERT INTO message_references(id, message_id, ref_type, ref_value)"
                    " VALUES(?,?,?,?)", pending_refs)
            if pending_obs:
                conn.executemany(
                    "INSERT OR IGNORE INTO message_observations(id, message_id, evidence_id,"
                    " source_ref, observed_at, body_hash) VALUES(?,?,?,?,?,?)", pending_obs)
        if tags:
            with db.batch(conn):
                conn.executemany(
                    "INSERT OR IGNORE INTO message_tags(id, case_id, message_id, tag, created_at)"
                    " VALUES(?,?,?,?,?)",
                    [(db.new_id(), case_id, mid, tag[:60], ts)
                     for tag in tags for mid, _ in new_ids])
    return inserted, duplicates


def _add_version(conn, message_id: str, body: str, evidence_id: str) -> None:
    row = conn.execute("SELECT COALESCE(MAX(version),0) AS v FROM message_versions"
                       " WHERE message_id=?", (message_id,)).fetchone()
    conn.execute(
        "INSERT INTO message_versions(id, message_id, version, body, observed_at,"
        " evidence_id, note) VALUES(?,?,?,?,?,?,?)",
        (db.new_id(), message_id, (row["v"] or 0) + 1, body, db.now_utc(), evidence_id,
         "text differs in another evidence snapshot"))


def _add_group_event(conn, case_id: str, conv_id: str, msg: ParsedMessage) -> None:
    event = msg.group_event
    if not event:
        return
    kind, actor, target = event
    conn.execute(
        "INSERT INTO group_events(id, case_id, conversation_id, message_id, event_type,"
        " actor, target, occurred_at, raw_text) VALUES(?,?,?,?,?,?,?,?,?)",
        (db.new_id(), case_id, conv_id, None, kind, actor, target, msg.sent_at_utc,
         msg.raw_text[:500]))


def _register_attachment(conn, case, evidence_id: str, path: Path,
                         message_id: str | None, media_type: str) -> str | None:
    if not path.is_file():
        return None
    digest = sha256_file(path)
    if message_id:
        dup = conn.execute(
            "SELECT id FROM attachments WHERE case_id=? AND sha256=? AND message_id=?",
            (case["id"], digest, message_id)).fetchone()
        if dup:
            return dup["id"]
    mime = mimetypes.guess_type(path.name)[0]
    aid = db.new_id()
    conn.execute(
        "INSERT INTO attachments(id, case_id, evidence_id, message_id, conversation_id,"
        " file_name, relative_path, stored_path, media_type, mime, size_bytes, sha256,"
        " missing, linked, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
        (aid, case["id"], evidence_id, message_id, None, path.name, path.name, str(path),
         media_type, mime, path.stat().st_size, digest, 1 if message_id else 0,
         db.now_utc()))
    return aid


def _link_media(conn, case, evidence_id: str, conv_id: str,
                media_files: list[Path]) -> int:
    """Attach media files to messages by filename reference (never guessed)."""
    by_name: dict[str, Path] = {p.name.lower(): p for p in media_files}
    linked = 0
    rows = conn.execute(
        "SELECT id, body, media_ref FROM messages WHERE conversation_id=?"
        " AND has_media=1 AND id NOT IN (SELECT COALESCE(message_id,'') FROM attachments)",
        (conv_id,))
    for row in rows:
        candidates = set()
        for text in (row["media_ref"] or "", row["body"] or ""):
            name = textutil.attached_filename(text) if text else None
            if name:
                candidates.add(Path(name).name.lower())
            for token in text.split():
                if token.lower() in by_name:
                    candidates.add(token.lower())
        for cand in candidates:
            path = by_name.get(cand)
            if not path:
                continue
            aid = _register_attachment(conn, case, evidence_id, path, row["id"], "document")
            if aid:
                kind = detect.sniff(path).media_type or "document"
                conn.execute(
                    "UPDATE attachments SET media_type=?, conversation_id=? WHERE id=?",
                    (kind, conv_id, aid))
                linked += 1
            break
    return linked


def _register_unlinked_media(conn, case, evidence_id: str, media: list[Path]) -> int:
    existing = {r["sha256"] for r in conn.execute(
        "SELECT sha256 FROM attachments WHERE case_id=?", (case["id"],))}
    added = 0
    for path in media:
        digest = sha256_file(path)
        if digest in existing:
            continue
        kind = detect.sniff(path).media_type or "document"
        if _register_attachment(conn, case, evidence_id, path, None, kind):
            existing.add(digest)
            added += 1
    return added


# ------------------------------------------------------------------------- finalise
def finalize_case(conn, case_id: str) -> None:
    """Recompute denormalised aggregates after any import."""
    conn.execute(
        "UPDATE conversations SET"
        " message_count=(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=conversations.id),"
        " media_count=(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=conversations.id"
        "   AND m.has_media=1),"
        " first_at=(SELECT MIN(sent_at_utc) FROM messages m WHERE m.conversation_id=conversations.id),"
        " last_at=(SELECT MAX(sent_at_utc) FROM messages m WHERE m.conversation_id=conversations.id)"
        " WHERE case_id=?", (case_id,))
    conn.execute(
        "UPDATE contacts SET"
        " first_seen=(SELECT MIN(sent_at_utc) FROM messages m WHERE m.sender_id=contacts.id),"
        " last_seen=(SELECT MAX(sent_at_utc) FROM messages m WHERE m.sender_id=contacts.id)"
        " WHERE case_id=?", (case_id,))
    conn.execute(
        "DELETE FROM conversation_participants WHERE conversation_id IN"
        " (SELECT id FROM conversations WHERE case_id=?)", (case_id,))
    conn.execute(
        "INSERT INTO conversation_participants(id, conversation_id, contact_id,"
        " message_count, first_at, last_at)"
        " SELECT lower(hex(randomblob(16))), conversation_id, sender_id, COUNT(*),"
        " MIN(sent_at_utc), MAX(sent_at_utc) FROM messages"
        " WHERE case_id=? AND sender_id IS NOT NULL AND is_system=0"
        " GROUP BY conversation_id, sender_id", (case_id,))
    conn.execute(
        "UPDATE attachments SET conversation_id=(SELECT conversation_id FROM messages m"
        " WHERE m.id=attachments.message_id) WHERE case_id=? AND message_id IS NOT NULL",
        (case_id,))
    conn.execute(
        "INSERT INTO timeline_events(id, case_id, occurred_at, kind, title, detail,"
        " ref_table, ref_id) SELECT lower(hex(randomblob(16))), case_id, imported_at,"
        " 'import', 'Evidence imported: ' || original_name, sha256, 'evidence_sources', id"
        " FROM evidence_sources WHERE case_id=? AND id NOT IN"
        " (SELECT ref_id FROM timeline_events WHERE case_id=? AND kind='import')",
        (case_id, case_id))
    cases_mod.touch_case(conn, case_id)


def import_quality(conn, evidence_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM evidence_sources WHERE id=?", (evidence_id,)).fetchone()
    if not row:
        raise KeyError("evidence not found")
    extra = db.json_load(row["extra_json"], {})
    errors = db.rows_to_list(conn.execute(
        "SELECT severity, code, message, line_no FROM import_errors WHERE evidence_id=?"
        " ORDER BY rowid LIMIT 200", (evidence_id,)))
    return {
        "evidence_id": evidence_id,
        "original_name": row["original_name"],
        "source_type": row["source_type"],
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
        "message_count": row["message_count"],
        "date_order": row["date_order"],
        "date_order_confidence": row["date_order_confidence"],
        "parse_confidence": row["parse_confidence"],
        "language": row["language"],
        "encoding": extra.get("encoding"),
        "duplicates": extra.get("duplicates", 0),
        "unresolved_lines": extra.get("unresolved_lines", 0),
        "ambiguous_timestamps": extra.get("ambiguous_timestamps", 0),
        "media_linked": extra.get("media_linked", 0),
        "media_unlinked": extra.get("media_unlinked", 0),
        "system_messages": extra.get("system_messages", 0),
        "deleted_markers": extra.get("deleted_markers", 0),
        "edited_markers": extra.get("edited_markers", 0),
        "date_order_reason": extra.get("date_order_reason", ""),
        "issues": errors,
    }
