"""Report orchestration: build, render, record hash, expose downloads."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from .. import cases as cases_mod
from .. import db
from ..hashing import sha256_file
from ..safety import spreadsheet_safe, unique_path
from . import builder, render_html, render_pdf, render_xlsx

FORMATS = ("html", "pdf", "xlsx", "csv", "json")


def generate(conn, case_id: str, report_type: str = "case", fmt: str = "pdf",
             options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format '{fmt}'")
    case = cases_mod.get_case(conn, case_id)
    report = builder.build(conn, case_id, report_type, options)
    out_dir = Path(case["dir_path"]) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Never overwrite a previously generated report: two exports in the same
    # minute are both evidence products and must both survive.
    path = unique_path(out_dir, f"{report_type}-report", fmt)

    if fmt == "html":
        theme = options.get("theme", "graphite")
        path.write_text(render_html.render(report, theme=theme), encoding="utf-8")
    elif fmt == "pdf":
        render_pdf.render(report, path)
    elif fmt == "xlsx":
        render_xlsx.render(report, path)
    elif fmt == "json":
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    else:  # csv: flatten the tabular blocks
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["section", "column", "value"])
        for block in report["blocks"]:
            if block["type"] == "table":
                for row in block["rows"]:
                    writer.writerow([spreadsheet_safe(cell)
                                     for cell in [block["title"], *row]])
            elif block["type"] == "kpi":
                writer.writerow([spreadsheet_safe(cell) for cell in
                                 ["summary", block["label"], block["value"]]])
        path.write_text(buffer.getvalue(), encoding="utf-8-sig")

    digest = sha256_file(path)
    report_id = db.new_id()
    conn.execute(
        "INSERT INTO reports(id, case_id, type, format, path, size_bytes, sha256,"
        " params_json, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (report_id, case_id, report_type, fmt, str(path), path.stat().st_size, digest,
         db.json_dump(options), db.now_utc()))
    db.audit(conn, "report.generate", case_id, "user", {
        "report_id": report_id, "type": report_type, "format": fmt, "sha256": digest})
    return {
        "id": report_id, "type": report_type, "format": fmt, "path": str(path),
        "size_bytes": path.stat().st_size, "sha256": digest,
        "created_at": db.now_utc(), "title": report["title"],
        "case_id": case_id,
    }


def list_reports(conn, case_id: str) -> list[dict[str, Any]]:
    return db.rows_to_list(conn.execute(
        "SELECT id, type, format, path, size_bytes, sha256, created_at FROM reports"
        " WHERE case_id=? ORDER BY created_at DESC", (case_id,)))


def report_path(conn, report_id: str) -> Path:
    row = conn.execute("SELECT path FROM reports WHERE id=?", (report_id,)).fetchone()
    if not row:
        raise KeyError("report not found")
    path = Path(row["path"])
    if not path.is_file():
        raise FileNotFoundError("report file is missing from disk")
    return path


def preview(conn, case_id: str, report_type: str = "case",
            options: dict[str, Any] | None = None) -> str:
    report = builder.build(conn, case_id, report_type, options or {})
    return render_html.render(report, theme=(options or {}).get("theme", "graphite"))


def export_messages(conn, case_id: str, *, fmt: str = "csv",
                    conversation_id: str | None = None,
                    contact_id: str | None = None,
                    date_from: str | None = None, date_to: str | None = None,
                    limit: int = 100_000) -> dict[str, Any]:
    case = cases_mod.get_case(conn, case_id)
    clauses = ["m.case_id=?"]
    params: list[Any] = [case_id]
    if conversation_id:
        clauses.append("m.conversation_id=?")
        params.append(conversation_id)
    if contact_id:
        clauses.append("m.sender_id=?")
        params.append(contact_id)
    if date_from:
        clauses.append("m.sent_at_utc>=?")
        params.append(date_from)
    if date_to:
        clauses.append("m.sent_at_utc<=?")
        params.append(date_to if len(date_to) > 10 else date_to + "T23:59:59Z")
    sql = ("SELECT m.sent_at_utc, m.sent_at_local, m.original_timestamp, m.sender_raw,"
           " c.title AS conversation, m.message_type, m.body, m.source_ref, m.evidence_id,"
           " m.parse_confidence, m.is_deleted, m.is_edited, m.has_media"
           " FROM messages m JOIN conversations c ON c.id=m.conversation_id"
           f" WHERE {' AND '.join(clauses)} ORDER BY m.sent_at_utc LIMIT ?")
    rows = db.rows_to_list(conn.execute(sql, (*params, limit)))
    out_dir = Path(case["dir_path"]) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = unique_path(out_dir, "messages", fmt)
    if fmt == "json":
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    else:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                                    ["sent_at_utc"])
            writer.writeheader()
            writer.writerows([{key: spreadsheet_safe(value) for key, value in row.items()}
                              for row in rows])
    digest = sha256_file(path)
    conn.execute(
        "INSERT INTO export_jobs(id, case_id, kind, status, path, created_at, finished_at)"
        " VALUES(?,?,?,'done',?,?,?)",
        (db.new_id(), case_id, f"messages.{fmt}", str(path), db.now_utc(), db.now_utc()))
    db.audit(conn, "export.messages", case_id, "user",
             {"path": str(path), "rows": len(rows), "sha256": digest})
    return {"path": str(path), "rows": len(rows), "sha256": digest, "format": fmt}
