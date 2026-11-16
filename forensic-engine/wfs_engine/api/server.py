"""Local HTTP API for the desktop UI.

Binds to loopback only, optionally requires a bearer token, and never serves
files outside the application data directory.
"""
from __future__ import annotations

import json
import mimetypes
import os
import platform
import re
import shutil
import sqlite3
import sys
import threading
import traceback
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from .. import (audio, backup, cases as cases_mod, config, db, importer, media,
                reporting, samples, search as search_mod)
from ..ai import assistant as ai_assistant
from ..ai import providers as ai_providers
from ..analytics import anomalies, metrics, network, recovery, sentiment
from ..config import ENGINE_VERSION

MAX_BODY = 8 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class FileResponse:
    path: Path
    mime: str = "application/octet-stream"


def api_key_from_env() -> str | None:
    return os.environ.get("WFS_TOKEN") or None


# --------------------------------------------------------------------- handlers
def h_health(conn, params, query, body):
    return {"ok": True, "engine": ENGINE_VERSION, "python": sys.version.split()[0],
            "offline": True, "time": db.now_utc()}


def h_version(conn, params, query, body):
    return {"engine": ENGINE_VERSION, "schema": "wfs/1"}


def h_settings(conn, params, query, body):
    return db.get_settings(conn)


def h_settings_patch(conn, params, query, body):
    if not isinstance(body, dict):
        raise ApiError("settings payload must be an object")
    return db.set_settings(conn, body)


def h_diagnostics(conn, params, query, body):
    usage = shutil.disk_usage(str(config.data_dir()))
    db_file = config.db_path()
    ai_status = ai_providers.status(db.get_settings(conn))
    engines = audio.engine_status()
    tools = media.tools()
    fts_ok = True
    try:
        conn.execute("SELECT count(*) FROM messages_fts")
    except sqlite3.Error:
        fts_ok = False
    return {
        "engine_version": ENGINE_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "fts5": fts_ok,
        "data_dir": str(config.data_dir()),
        "db_path": str(db_file),
        "db_bytes": db_file.stat().st_size if db_file.exists() else 0,
        "disk_free_bytes": usage.free,
        "disk_total_bytes": usage.total,
        "cases": conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0],
        "messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "settings": db.get_settings(conn),
        "ai": ai_status,
        "transcription": engines,
        "media_tools": {"exiftool": tools.exiftool, "ffprobe": tools.ffprobe,
                        "ffmpeg": tools.ffmpeg, "pillow": media.HAVE_PIL},
        "offline_capable": True,
        "audit_entries": conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
    }


def h_cases(conn, params, query, body):
    if query.get("archived", "1") == "1":
        return cases_mod.list_cases(conn, include_archived=True)
    return cases_mod.list_cases(conn, include_archived=False)


def h_case_create(conn, params, query, body):
    if not isinstance(body, dict):
        raise ApiError("payload required")
    if not body.get("name"):
        raise ApiError("case name is required")
    if not body.get("authorization_acknowledged"):
        raise ApiError("the evidence authorisation declaration must be acknowledged")
    return cases_mod.create_case(
        conn, body["name"], body.get("description", ""), body.get("examiner", ""),
        body.get("authorization_statement", ""))


def h_case_get(conn, params, query, body):
    return cases_mod.get_case(conn, params["case_id"])


def h_case_patch(conn, params, query, body):
    return cases_mod.update_case(conn, params["case_id"], body or {})


def h_case_delete(conn, params, query, body):
    remove = bool((body or {}).get("remove_files"))
    cases_mod.delete_case(conn, params["case_id"], remove_files=remove)
    return {"deleted": True}


def h_case_archive(conn, params, query, body):
    return cases_mod.update_case(conn, params["case_id"], {"status": "archived"})


def h_case_restore_status(conn, params, query, body):
    return cases_mod.update_case(conn, params["case_id"], {"status": "active"})


def h_case_duplicate(conn, params, query, body):
    return cases_mod.duplicate_case(conn, params["case_id"], (body or {}).get("name"))


def h_case_manifest(conn, params, query, body):
    path = cases_mod.write_manifest(conn, params["case_id"])
    return json.loads(path.read_text(encoding="utf-8"))


def h_audit(conn, params, query, body):
    return cases_mod.audit_log(conn, params["case_id"],
                               int(query.get("limit", 300)))


def h_custody(conn, params, query, body):
    return cases_mod.chain_of_custody(conn, params["case_id"])


def h_notes(conn, params, query, body):
    return cases_mod.list_notes(conn, params["case_id"])


def h_note_create(conn, params, query, body):
    if not (body or {}).get("body"):
        raise ApiError("note body is required")
    return cases_mod.add_note(conn, params["case_id"], body["body"],
                              body.get("message_id"), body.get("author") or "user")


def h_note_delete(conn, params, query, body):
    cases_mod.delete_note(conn, params["case_id"], params["note_id"])
    return {"deleted": True}


def h_bookmarks(conn, params, query, body):
    return cases_mod.list_bookmarks(conn, params["case_id"])


def h_bookmark_create(conn, params, query, body):
    if not (body or {}).get("message_id"):
        raise ApiError("message_id is required")
    return cases_mod.add_bookmark(conn, params["case_id"], body["message_id"],
                                  body.get("label", ""))


def h_bookmark_delete(conn, params, query, body):
    cases_mod.remove_bookmark(conn, params["case_id"], params["message_id"])
    return {"deleted": True}


def h_tags(conn, params, query, body):
    return cases_mod.list_tags(conn, params["case_id"])


def h_tag_create(conn, params, query, body):
    if not (body or {}).get("message_id") or not (body or {}).get("tag"):
        raise ApiError("message_id and tag are required")
    return cases_mod.add_tag(conn, params["case_id"], body["message_id"], body["tag"])


def h_tag_delete(conn, params, query, body):
    cases_mod.remove_tag(conn, params["case_id"], params["message_id"],
                         query.get("tag", ""))
    return {"deleted": True}


def h_evidence(conn, params, query, body):
    rows = db.rows_to_list(conn.execute(
        "SELECT * FROM evidence_sources WHERE case_id=? ORDER BY imported_at",
        (params["case_id"],)))
    for row in rows:
        row["extra"] = db.json_load(row.pop("extra_json"), {})
    return rows


def h_evidence_quality(conn, params, query, body):
    return importer.import_quality(conn, params["evidence_id"])


def h_evidence_verify(conn, params, query, body):
    return cases_mod.verify_evidence(conn, params["case_id"])


def h_import(conn, params, query, body):
    body = body or {}
    paths = body.get("paths") or []
    if not paths:
        raise ApiError("no file paths supplied")
    options = importer.ImportOptions.from_dict(body.get("options") or {})
    return importer.start_import(conn, params["case_id"], paths, options)


def h_import_sample(conn, params, query, body):
    case = cases_mod.get_case(conn, params["case_id"])
    target = Path(case["dir_path"]) / "derived" / "sample-dataset"
    info = samples.write_sample_files(target)
    options = importer.ImportOptions.from_dict(
        (body or {}).get("options") or {"date_order": "auto", "source_timezone": "UTC"})
    job = importer.start_import(conn, params["case_id"], info["files"], options)
    db.audit(conn, "evidence.import_sample", params["case_id"], "user", info)
    return {**job, "sample": info}


def h_job(conn, params, query, body):
    return importer.get_job(conn, params["job_id"])


def h_job_cancel(conn, params, query, body):
    return importer.cancel_job(conn, params["job_id"])


def h_jobs(conn, params, query, body):
    rows = db.rows_to_list(conn.execute(
        "SELECT id, case_id, status, stage, progress, started_at, finished_at, error"
        " FROM import_jobs WHERE case_id=? ORDER BY created_at DESC LIMIT 40",
        (params["case_id"],)))
    return rows


def h_conversations(conn, params, query, body):
    return metrics.conversation_summaries(conn, params["case_id"])


def h_conversation(conn, params, query, body):
    case_id = params["case_id"]
    conv_id = params["conversation_id"]
    row = conn.execute("SELECT * FROM conversations WHERE id=? AND case_id=?",
                       (conv_id, case_id)).fetchone()
    if not row:
        raise ApiError("conversation not found", 404)
    participants = db.rows_to_list(conn.execute(
        "SELECT ct.id, ct.display_name, p.message_count FROM conversation_participants p"
        " JOIN contacts ct ON ct.id=p.contact_id WHERE p.conversation_id=?"
        " ORDER BY p.message_count DESC", (conv_id,)))
    count = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?",
                         (conv_id,)).fetchone()[0]
    return {**dict(row), "participants": participants, "message_total": count}


def h_messages(conn, params, query, body):
    case_id = params["case_id"]
    conv_id = params["conversation_id"]
    limit = min(int(query.get("limit", 120)), 500)
    anchor = query.get("anchor")
    direction = query.get("direction", "backward")
    sql_base = ("SELECT m.id, m.sender_id, m.sender_raw, m.sent_at_utc, m.sent_at_local,"
                " m.body, m.message_type, m.is_system, m.is_deleted, m.is_edited,"
                " m.is_forwarded, m.has_media, m.media_ref, m.source_ref, m.evidence_id,"
                " m.parse_confidence, m.original_timestamp, m.tz_offset_min,"
                " (SELECT COUNT(*) FROM attachments a WHERE a.message_id=m.id) AS attachments"
                " FROM messages m")
    if anchor:
        anchor_row = conn.execute("SELECT sent_at_utc FROM messages WHERE id=? AND case_id=?",
                                  (anchor, case_id)).fetchone()
        if not anchor_row:
            raise ApiError("anchor message not found", 404)
        if direction == "forward":
            rows = conn.execute(
                f"{sql_base} WHERE m.conversation_id=? AND m.sent_at_utc >= ?"
                " ORDER BY m.sent_at_utc LIMIT ?",
                (conv_id, anchor_row["sent_at_utc"], limit)).fetchall()
        else:
            rows = conn.execute(
                f"{sql_base} WHERE m.conversation_id=? AND m.sent_at_utc <= ?"
                " ORDER BY m.sent_at_utc DESC LIMIT ?",
                (conv_id, anchor_row["sent_at_utc"], limit)).fetchall()
        rows = list(reversed(rows)) if direction != "forward" else rows
    else:
        offset = max(0, int(query.get("offset", 0)))
        rows = conn.execute(
            f"{sql_base} WHERE m.conversation_id=? ORDER BY m.sent_at_utc LIMIT ? OFFSET ?",
            (conv_id, limit, offset)).fetchall()
    messages = [dict(r) for r in rows]
    total = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?",
                         (conv_id,)).fetchone()[0]
    bookmarks = {r["message_id"] for r in conn.execute(
        "SELECT message_id FROM bookmarks WHERE case_id=?", (case_id,))}
    tags: dict[str, list[str]] = {}
    for row in conn.execute(
            "SELECT message_id, tag FROM message_tags WHERE case_id=?", (case_id,)):
        tags.setdefault(row["message_id"], []).append(row["tag"])
    for msg in messages:
        msg["bookmarked"] = msg["id"] in bookmarks
        msg["tags"] = tags.get(msg["id"], [])
    return {"messages": messages, "total": total, "limit": limit}


def h_message_detail(conn, params, query, body):
    case_id = params["case_id"]
    message_id = params["message_id"]
    row = conn.execute(
        "SELECT m.*, c.title AS conversation_title, c.kind FROM messages m"
        " JOIN conversations c ON c.id=m.conversation_id WHERE m.id=? AND m.case_id=?",
        (message_id, case_id)).fetchone()
    if not row:
        raise ApiError("message not found", 404)
    message = dict(row)
    message["attachments"] = db.rows_to_list(conn.execute(
        "SELECT id, file_name, media_type, size_bytes, sha256, missing, duration_ms,"
        " width, height FROM attachments WHERE message_id=?", (message_id,)))
    message["references"] = db.rows_to_list(conn.execute(
        "SELECT ref_type, ref_value FROM message_references WHERE message_id=?",
        (message_id,)))
    message["versions"] = db.rows_to_list(conn.execute(
        "SELECT version, body, observed_at, evidence_id FROM message_versions"
        " WHERE message_id=? ORDER BY version", (message_id,)))
    message["observations"] = db.rows_to_list(conn.execute(
        "SELECT o.evidence_id, o.source_ref, e.original_name, e.sha256"
        " FROM message_observations o JOIN evidence_sources e ON e.id=o.evidence_id"
        " WHERE o.message_id=?", (message_id,)))
    message["tags"] = [r["tag"] for r in conn.execute(
        "SELECT tag FROM message_tags WHERE message_id=?", (message_id,))]
    bookmark = conn.execute("SELECT * FROM bookmarks WHERE message_id=?",
                            (message_id,)).fetchone()
    message["bookmark"] = dict(bookmark) if bookmark else None
    message["notes"] = db.rows_to_list(conn.execute(
        "SELECT * FROM investigation_notes WHERE case_id=? AND message_id=?",
        (case_id, message_id)))
    return message


def h_dashboard(conn, params, query, body):
    case_id = params["case_id"]
    overview = metrics.overview(conn, case_id)
    daily = metrics.activity_series(conn, case_id, "day")
    hourly = metrics.activity_series(conn, case_id, "hour")
    heat = metrics.heatmap(conn, case_id)
    evidence = db.rows_to_list(conn.execute(
        "SELECT id, original_name, source_type, message_count, imported_at, sha256"
        " FROM evidence_sources WHERE case_id=? ORDER BY imported_at DESC LIMIT 5",
        (case_id,)))
    findings = conn.execute(
        "SELECT COUNT(*) FROM recovery_findings WHERE case_id=?", (case_id,)).fetchone()[0]
    recent_notes = cases_mod.list_notes(conn, case_id)[:5]
    bookmarks = cases_mod.list_bookmarks(conn, case_id)[:5]
    conversations = metrics.conversation_summaries(conn, case_id)
    activity_30 = daily["series"][-30:]
    return {
        "overview": overview,
        "daily": activity_30,
        "hourly": hourly["series"],
        "heatmap": heat,
        "top_contacts": metrics.contacts(conn, case_id)[:6],
        "conversations": conversations[:6],
        "evidence": evidence,
        "findings": findings,
        "notes": recent_notes,
        "bookmarks": bookmarks,
        "sentiment_enabled": bool(db.get_settings(conn).get("interpretive_analysis")),
        "quick_actions": [
            {"label": "Import evidence", "route": "import"},
            {"label": "Open latest conversation",
             "route": f"explorer/{conversations[0]['id']}" if conversations else "explorer"},
            {"label": "Run recovery analysis", "route": "recovery"},
            {"label": "Ask the AI assistant", "route": "assistant"},
            {"label": "Build a report", "route": "reports"},
        ],
    }


def h_analytics(conn, params, query, body):
    case_id = params["case_id"]
    conversation_id = query.get("conversation_id") or None
    date_from = query.get("from") or None
    date_to = query.get("to") or None
    return metrics.analytics_bundle(conn, case_id, conversation_id=conversation_id,
                                    date_from=date_from, date_to=date_to)


def h_sentiment(conn, params, query, body):
    settings = db.get_settings(conn)
    if not settings.get("interpretive_analysis"):
        return {"disabled": True, "message": "Interpretive analysis is disabled in Settings."}
    return sentiment.analyze(conn, params["case_id"],
                            conversation_id=query.get("conversation_id") or None)


def h_anomalies(conn, params, query, body):
    sensitivity = float(query.get("sensitivity")
                        or db.get_settings(conn).get("anomaly_sensitivity", 3.0))
    return anomalies.detect(conn, params["case_id"], sensitivity=sensitivity,
                            conversation_id=query.get("conversation_id") or None)


def h_contacts(conn, params, query, body):
    return metrics.contacts(conn, params["case_id"])


def h_contact(conn, params, query, body):
    return metrics.contact_profile(conn, params["case_id"], params["contact_id"])


def h_contact_compare(conn, params, query, body):
    ids = (body or {}).get("contact_ids") or []
    if len(ids) < 2:
        raise ApiError("select at least two contacts")
    return metrics.compare_contacts(conn, params["case_id"], ids)


def h_groups(conn, params, query, body):
    rows = db.rows_to_list(conn.execute(
        "SELECT c.*, (SELECT COUNT(DISTINCT sender_id) FROM messages m"
        "  WHERE m.conversation_id=c.id) AS participants"
        " FROM conversations c WHERE c.case_id=? AND c.kind='group'"
        " ORDER BY c.message_count DESC", (params["case_id"],)))
    return rows


def h_group(conn, params, query, body):
    return metrics.group_analysis(conn, params["case_id"], params["conversation_id"])


def h_network(conn, params, query, body):
    return network.build(conn, params["case_id"], date_from=query.get("from"),
                         date_to=query.get("to"),
                         include_topics=query.get("topics", "1") == "1",
                         min_messages=int(query.get("min_messages", 1)))


def h_timeline(conn, params, query, body):
    case_id = params["case_id"]
    limit = min(int(query.get("limit", 400)), 2000)
    date_from = query.get("from")
    date_to = query.get("to")
    conversation_id = query.get("conversation_id") or None
    kinds = set((query.get("kinds") or "").split(",")) - {""}
    events: list[dict[str, Any]] = []

    if not kinds or "message" in kinds:
        clauses = ["m.case_id=?"]
        params_sql: list[Any] = [case_id]
        if date_from:
            clauses.append("m.sent_at_utc>=?")
            params_sql.append(date_from)
        if date_to:
            clauses.append("m.sent_at_utc<=?")
            params_sql.append(date_to + "T23:59:59Z" if len(date_to) == 10 else date_to)
        if conversation_id:
            clauses.append("m.conversation_id=?")
            params_sql.append(conversation_id)
        for row in conn.execute(
                f"SELECT m.id, m.sent_at_utc, m.sender_raw, m.body, m.message_type,"
                f" c.title, m.has_media FROM messages m JOIN conversations c"
                f" ON c.id=m.conversation_id WHERE {' AND '.join(clauses)}"
                f" ORDER BY m.sent_at_utc LIMIT ?", (*params_sql, limit)):
            events.append({"id": row["id"], "at": row["sent_at_utc"], "kind": "message",
                           "title": f"{row['sender_raw']} · {row['title']}",
                           "detail": (row["body"] or "")[:300],
                           "message_id": row["id"],
                           "type": row["message_type"],
                           "media": bool(row["has_media"])})

    if not kinds or "group" in kinds:
        for row in conn.execute(
                "SELECT g.id, g.occurred_at, g.event_type, g.raw_text, c.title"
                " FROM group_events g JOIN conversations c ON c.id=g.conversation_id"
                " WHERE g.case_id=? ORDER BY g.occurred_at LIMIT ?", (case_id, limit)):
            events.append({"id": row["id"], "at": row["occurred_at"], "kind": "group_event",
                           "title": f"{row['event_type']} · {row['title']}",
                           "detail": row["raw_text"], "message_id": None})

    if not kinds or "import" in kinds:
        for row in conn.execute(
                "SELECT id, imported_at, original_name, sha256 FROM evidence_sources"
                " WHERE case_id=? ORDER BY imported_at", (case_id,)):
            events.append({"id": row["id"], "at": row["imported_at"], "kind": "import",
                           "title": f"Evidence imported: {row['original_name']}",
                           "detail": row["sha256"], "message_id": None})

    if not kinds or "annotation" in kinds:
        for row in conn.execute(
                "SELECT b.id, m.sent_at_utc, b.label, m.body FROM bookmarks b"
                " JOIN messages m ON m.id=b.message_id WHERE b.case_id=?",
                (case_id,)):
            events.append({"id": row["id"], "at": row["sent_at_utc"], "kind": "bookmark",
                           "title": f"Bookmark: {row['label'] or 'marked message'}",
                           "detail": (row["body"] or "")[:200], "message_id": None})
        for row in conn.execute(
                "SELECT id, created_at, body FROM investigation_notes WHERE case_id=?",
                (case_id,)):
            events.append({"id": row["id"], "at": row["created_at"], "kind": "note",
                           "title": "Investigation note",
                           "detail": (row["body"] or "")[:200], "message_id": None})

    events.sort(key=lambda e: e["at"])
    return {"events": events[:limit], "total": len(events)}


def h_recovery(conn, params, query, body):
    case_id = params["case_id"]
    rows = db.rows_to_list(conn.execute(
        "SELECT * FROM recovery_findings WHERE case_id=? ORDER BY created_at DESC LIMIT 500",
        (case_id,)))
    for row in rows:
        row["detail"] = db.json_load(row.pop("detail_json"), {})
    return {"findings": rows,
            "classifications": recovery.CLASSIFICATIONS,
            "counts": {r["status"]: 0 for r in rows},
            "comparisons": recovery.compare_snapshots(conn, case_id)}


def h_recovery_analyze(conn, params, query, body):
    result = recovery.analyze(conn, params["case_id"])
    db.audit(conn, "recovery.analyze", params["case_id"], "user",
             {"findings": len(result["findings"])})
    return result


def h_media(conn, params, query, body):
    return media.list_media(conn, params["case_id"],
                            media_type=query.get("type"),
                            conversation_id=query.get("conversation_id") or None,
                            search=query.get("q"), limit=int(query.get("limit", 60)),
                            offset=int(query.get("offset", 0)))


def h_media_duplicates(conn, params, query, body):
    return media.duplicates(conn, params["case_id"])


def h_media_missing(conn, params, query, body):
    return media.missing_media(conn, params["case_id"])


def h_media_timeline(conn, params, query, body):
    return media.media_timeline(conn, params["case_id"])


def h_media_inspect(conn, params, query, body):
    return media.inspect(conn, params["attachment_id"],
                         force=(body or {}).get("force", False))


def h_media_file(conn, params, query, body):
    path = media.serve_path(conn, params["attachment_id"])
    if path is None:
        raise ApiError("file not available", 404)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, mime)


def h_media_thumb(conn, params, query, body):
    row = conn.execute("SELECT meta_json FROM attachments WHERE id=?",
                       (params["attachment_id"],)).fetchone()
    meta = db.json_load(row["meta_json"], {}) if row else {}
    thumb = meta.get("thumbnail")
    if not thumb or not Path(thumb).is_file():
        media.inspect(conn, params["attachment_id"])
        row = conn.execute("SELECT meta_json FROM attachments WHERE id=?",
                           (params["attachment_id"],)).fetchone()
        meta = db.json_load(row["meta_json"], {}) if row else {}
        thumb = meta.get("thumbnail")
    if not thumb or not Path(thumb).is_file():
        raise ApiError("no thumbnail available", 404)
    return FileResponse(Path(thumb), "image/jpeg")


def h_transcribe(conn, params, query, body):
    try:
        return audio.transcribe(conn, params["attachment_id"],
                                model=(body or {}).get("model"),
                                language=(body or {}).get("language"),
                                force=(body or {}).get("force", False))
    except audio.TranscriptionUnavailable as exc:
        raise ApiError(str(exc), 503) from exc


def h_transcripts(conn, params, query, body):
    return {"transcripts": audio.list_transcripts(conn, params["case_id"]),
            "engine": audio.engine_status()}


def h_transcript_update(conn, params, query, body):
    if not (body or {}).get("text"):
        raise ApiError("text is required")
    return audio.update_transcript(conn, params["transcript_id"], body["text"],
                                   body.get("language"))


def h_transcript_search(conn, params, query, body):
    return audio.search_transcripts(conn, params["case_id"], query.get("q", ""))


def h_search(conn, params, query, body):
    case_id = params["case_id"]
    if body:
        q = search_mod.SearchQuery.from_dict(body)
    else:
        q = search_mod.SearchQuery(
            q=query.get("q", ""), mode=query.get("mode", "fts"),
            limit=int(query.get("limit", 50)), offset=int(query.get("offset", 0)),
            date_from=query.get("from") or None, date_to=query.get("to") or None,
            conversation_ids=[query["conversation_id"]] if query.get("conversation_id") else [],
            sender_ids=[query["sender_id"]] if query.get("sender_id") else [],
            media_type=query.get("media_type") or None,
            tag=query.get("tag") or None,
            bookmarked=query.get("bookmarked") == "1")
    return search_mod.search(conn, case_id, q)


def h_saved_searches(conn, params, query, body):
    return search_mod.list_saved(conn, params["case_id"])


def h_saved_search_create(conn, params, query, body):
    body = body or {}
    if not body.get("name"):
        raise ApiError("name is required")
    return search_mod.save_search(conn, params["case_id"], body["name"],
                                  body.get("query") or {})


def h_saved_search_delete(conn, params, query, body):
    search_mod.delete_saved(conn, params["case_id"], params["search_id"])
    return {"deleted": True}


def h_search_suggest(conn, params, query, body):
    return search_mod.suggestions(conn, params["case_id"], query.get("q", ""))


def h_ai_status(conn, params, query, body):
    settings = db.get_settings(conn)
    return ai_providers.status(settings)


def h_ai_ask(conn, params, query, body):
    body = body or {}
    if not body.get("question"):
        raise ApiError("question is required")
    try:
        return ai_assistant.ask(
            conn, params["case_id"], body["question"],
            conversation_id=body.get("conversation_id"),
            provider_name=body.get("provider"), model=body.get("model"),
            limit=int(body.get("limit", 24)))
    except Exception as exc:  # noqa: BLE001
        raise ApiError(f"assistant failed: {exc}", 502) from exc


def h_ai_history(conn, params, query, body):
    return ai_assistant.history(conn, params["case_id"])


def h_reports(conn, params, query, body):
    return reporting.list_reports(conn, params["case_id"])


def h_report_preview(conn, params, query, body):
    html = reporting.preview(conn, params["case_id"],
                             (body or {}).get("type", "case"), body or {})
    return {"html": html}


def h_report_generate(conn, params, query, body):
    body = body or {}
    return reporting.generate(conn, params["case_id"], body.get("type", "case"),
                              body.get("format", "pdf"), body.get("options") or {})


def h_report_download(conn, params, query, body):
    path = reporting.report_path(conn, params["report_id"])
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, mime)


def h_export_messages(conn, params, query, body):
    body = body or {}
    return reporting.export_messages(conn, params["case_id"], fmt=body.get("format", "csv"),
                                     conversation_id=body.get("conversation_id"),
                                     contact_id=body.get("contact_id"),
                                     date_from=body.get("date_from"),
                                     date_to=body.get("date_to"))


def h_backup(conn, params, query, body):
    password = (body or {}).get("password")
    if not password or len(password) < 8:
        raise ApiError("a passphrase of at least 8 characters is required")
    return backup.create_backup(conn, params["case_id"], password)


def h_restore(conn, params, query, body):
    body = body or {}
    if not body.get("path"):
        raise ApiError("backup path is required")
    try:
        return backup.restore_backup(conn, Path(body["path"]), body.get("password", ""),
                                     body.get("name"))
    except (ValueError, RuntimeError, OSError) as exc:
        raise ApiError(str(exc), 400) from exc


def h_stats(conn, params, query, body):
    return cases_mod.case_counts(conn, params["case_id"])


ROUTES: list[tuple[str, str, Callable]] = [
    ("GET", "/api/health", h_health),
    ("GET", "/api/version", h_version),
    ("GET", "/api/diagnostics", h_diagnostics),
    ("GET", "/api/settings", h_settings),
    ("PATCH", "/api/settings", h_settings_patch),
    ("GET", "/api/cases", h_cases),
    ("POST", "/api/cases", h_case_create),
    ("POST", "/api/cases/restore", h_restore),
    ("GET", "/api/cases/<case_id>", h_case_get),
    ("PATCH", "/api/cases/<case_id>", h_case_patch),
    ("DELETE", "/api/cases/<case_id>", h_case_delete),
    ("POST", "/api/cases/<case_id>/archive", h_case_archive),
    ("POST", "/api/cases/<case_id>/activate", h_case_restore_status),
    ("POST", "/api/cases/<case_id>/duplicate", h_case_duplicate),
    ("GET", "/api/cases/<case_id>/manifest", h_case_manifest),
    ("GET", "/api/cases/<case_id>/audit", h_audit),
    ("GET", "/api/cases/<case_id>/custody", h_custody),
    ("GET", "/api/cases/<case_id>/notes", h_notes),
    ("POST", "/api/cases/<case_id>/notes", h_note_create),
    ("DELETE", "/api/cases/<case_id>/notes/<note_id>", h_note_delete),
    ("GET", "/api/cases/<case_id>/bookmarks", h_bookmarks),
    ("POST", "/api/cases/<case_id>/bookmarks", h_bookmark_create),
    ("DELETE", "/api/cases/<case_id>/bookmarks/<message_id>", h_bookmark_delete),
    ("GET", "/api/cases/<case_id>/tags", h_tags),
    ("POST", "/api/cases/<case_id>/tags", h_tag_create),
    ("DELETE", "/api/cases/<case_id>/tags/<message_id>", h_tag_delete),
    ("GET", "/api/cases/<case_id>/evidence", h_evidence),
    ("POST", "/api/cases/<case_id>/evidence/verify", h_evidence_verify),
    ("GET", "/api/cases/<case_id>/evidence/<evidence_id>/quality", h_evidence_quality),
    ("POST", "/api/cases/<case_id>/import", h_import),
    ("POST", "/api/cases/<case_id>/import-sample", h_import_sample),
    ("GET", "/api/cases/<case_id>/jobs", h_jobs),
    ("GET", "/api/jobs/<job_id>", h_job),
    ("POST", "/api/jobs/<job_id>/cancel", h_job_cancel),
    ("GET", "/api/cases/<case_id>/dashboard", h_dashboard),
    ("GET", "/api/cases/<case_id>/analytics", h_analytics),
    ("GET", "/api/cases/<case_id>/sentiment", h_sentiment),
    ("GET", "/api/cases/<case_id>/anomalies", h_anomalies),
    ("GET", "/api/cases/<case_id>/conversations", h_conversations),
    ("GET", "/api/cases/<case_id>/conversations/<conversation_id>", h_conversation),
    ("GET", "/api/cases/<case_id>/conversations/<conversation_id>/messages", h_messages),
    ("GET", "/api/cases/<case_id>/messages/<message_id>", h_message_detail),
    ("GET", "/api/cases/<case_id>/contacts", h_contacts),
    ("GET", "/api/cases/<case_id>/contacts/<contact_id>", h_contact),
    ("POST", "/api/cases/<case_id>/contacts/compare", h_contact_compare),
    ("GET", "/api/cases/<case_id>/groups", h_groups),
    ("GET", "/api/cases/<case_id>/groups/<conversation_id>", h_group),
    ("GET", "/api/cases/<case_id>/network", h_network),
    ("GET", "/api/cases/<case_id>/timeline", h_timeline),
    ("GET", "/api/cases/<case_id>/recovery", h_recovery),
    ("POST", "/api/cases/<case_id>/recovery/analyze", h_recovery_analyze),
    ("GET", "/api/cases/<case_id>/media", h_media),
    ("GET", "/api/cases/<case_id>/media/duplicates", h_media_duplicates),
    ("GET", "/api/cases/<case_id>/media/missing", h_media_missing),
    ("GET", "/api/cases/<case_id>/media/timeline", h_media_timeline),
    ("POST", "/api/cases/<case_id>/media/<attachment_id>/inspect", h_media_inspect),
    ("GET", "/api/cases/<case_id>/media/<attachment_id>/file", h_media_file),
    ("GET", "/api/cases/<case_id>/media/<attachment_id>/thumb", h_media_thumb),
    ("POST", "/api/cases/<case_id>/audio/<attachment_id>/transcribe", h_transcribe),
    ("GET", "/api/cases/<case_id>/transcripts", h_transcripts),
    ("PATCH", "/api/transcripts/<transcript_id>", h_transcript_update),
    ("GET", "/api/cases/<case_id>/transcripts/search", h_transcript_search),
    ("GET", "/api/cases/<case_id>/search", h_search),
    ("POST", "/api/cases/<case_id>/search", h_search),
    ("GET", "/api/cases/<case_id>/search/suggest", h_search_suggest),
    ("GET", "/api/cases/<case_id>/searches", h_saved_searches),
    ("POST", "/api/cases/<case_id>/searches", h_saved_search_create),
    ("DELETE", "/api/cases/<case_id>/searches/<search_id>", h_saved_search_delete),
    ("GET", "/api/ai/status", h_ai_status),
    ("POST", "/api/cases/<case_id>/ai/ask", h_ai_ask),
    ("GET", "/api/cases/<case_id>/ai/history", h_ai_history),
    ("GET", "/api/cases/<case_id>/reports", h_reports),
    ("POST", "/api/cases/<case_id>/reports/preview", h_report_preview),
    ("POST", "/api/cases/<case_id>/reports", h_report_generate),
    ("GET", "/api/reports/<report_id>/download", h_report_download),
    ("POST", "/api/cases/<case_id>/export/messages", h_export_messages),
    ("POST", "/api/cases/<case_id>/backup", h_backup),
    ("GET", "/api/cases/<case_id>/stats", h_stats),
]


def _compile(pattern: str) -> re.Pattern[str]:
    regex = "^" + re.sub(r"<(\w+)>", lambda m: f"(?P<{m.group(1)}>[^/]+)", pattern) + "$"
    return re.compile(regex)


COMPILED = [(_compile(p), method, fn) for method, p, fn in ROUTES]


def dispatch(conn, method: str, path: str, query: dict[str, str],
             body: Any) -> Any:
    for regex, route_method, fn in COMPILED:
        if route_method != method:
            continue
        match = regex.match(path)
        if not match:
            continue
        params = {k: urllib.parse.unquote(v) for k, v in match.groupdict().items()}
        return fn(conn, params, query, body)
    raise ApiError(f"no route for {method} {path}", 404)


class Handler(BaseHTTPRequestHandler):
    server_version = f"WFSEngine/{ENGINE_VERSION}"
    protocol_version = "HTTP/1.1"
    token: str | None = None
    quiet = True

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if not self.quiet:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ------------------------------------------------------------------ helpers
    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin and self._origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("X-Content-Type-Options", "nosniff")

    def _json(self, status: int, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    # Exact origins only: a prefix test would accept "http://localhost.evil.com"
    # and reflect it back to the caller.
    ALLOWED_ORIGIN_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
    ALLOWED_ORIGINS = frozenset({"tauri://localhost", "https://tauri.localhost"})

    @classmethod
    def _origin_allowed(cls, origin: str) -> bool:
        """Allow the desktop shell and loopback development origins."""
        if origin in cls.ALLOWED_ORIGINS:
            return True
        try:
            parsed = urllib.parse.urlsplit(origin)
        except ValueError:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        try:
            parsed.port  # noqa: B018 - raises ValueError on a malformed port
        except ValueError:
            return False
        # urlsplit lowercases the hostname and strips the userinfo section, so
        # "http://localhost@evil.com" resolves to host "evil.com" here.
        return (parsed.hostname or "") in cls.ALLOWED_ORIGIN_HOSTS

    def _authorised(self) -> bool:
        if not self.token:
            return True
        header = self.headers.get("Authorization", "")
        if header == f"Bearer {self.token}":
            return True
        # Media/thumbnail URLs loaded by <img>/<audio> tags cannot send headers.
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        return query.get("token", [""])[0] == self.token

    def _file(self, path: Path, mime: str) -> None:
        try:
            size = path.stat().st_size
        except OSError:
            self._json(404, {"error": "file missing"})
            return
        start, end = 0, size - 1
        status = 200
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            try:
                spec = range_header[6:].split(",")[0]
                first, _, last = spec.partition("-")
                if first:
                    start = int(first)
                if last:
                    end = min(int(last), size - 1)
                if start > end:
                    start, end = 0, size - 1
                status = 206
            except ValueError:
                start, end = 0, size - 1
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self._cors()
        self.end_headers()
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(262144, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    # ------------------------------------------------------------------ verbs
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    def _handle(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if not self._authorised():
            self._json(401, {"error": "unauthorised"})
            return
        body: Any = None
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            if length > MAX_BODY:
                self._json(413, {"error": "request body too large"})
                return
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except (ValueError, UnicodeDecodeError):
                self._json(400, {"error": "invalid JSON body"})
                return
        try:
            with db.session() as conn:
                result = dispatch(conn, method, path, query, body)
        except ApiError as exc:
            self._json(exc.status, {"error": str(exc)})
            return
        except KeyError as exc:
            self._json(404, {"error": f"not found: {exc}"})
            return
        except FileNotFoundError as exc:
            self._json(404, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if isinstance(result, FileResponse):
            self._file(result.path, result.mime)
        else:
            self._json(200, result)


class EngineServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765,
                 token: str | None = None):
        db.migrate()
        config.ensure_dirs()
        handler = type("BoundHandler", (Handler,), {"token": token})
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.host, self.port = self.httpd.server_address[:2]

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()


def serve(host: str = "127.0.0.1", port: int = 8765, token: str | None = None) -> None:
    server = EngineServer(host, port, token)
    print(json.dumps({"listening": f"http://{server.host}:{server.port}",
                      "token_required": bool(token), "engine": ENGINE_VERSION}),
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


def run_in_thread(port: int = 0, token: str | None = None) -> EngineServer:
    server = EngineServer("127.0.0.1", port, token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
