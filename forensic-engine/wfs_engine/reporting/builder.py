"""Report data assembly.

Reports are built from the same database rows the UI shows, so a report can
never contain numbers that the application itself would not display.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .. import cases as cases_mod
from .. import db
from ..analytics import anomalies, metrics, network, recovery
from ..config import ENGINE_VERSION

REPORT_TYPES = {
    "case": "Complete Case Report",
    "conversation": "Conversation Analysis Report",
    "contact": "Contact Intelligence Report",
    "group": "Group Activity Report",
    "timeline": "Communication Timeline Report",
    "media": "Media Evidence Report",
    "recovery": "Recovery Analysis Report",
    "ai": "AI-Assisted Analytical Report",
    "search": "Search Results Report",
    "custom": "Custom Investigation Report",
}

DEFAULT_SECTIONS = {
    "case": ["summary", "metrics", "activity", "contacts", "conversations",
             "evidence", "findings", "methodology"],
    "conversation": ["summary", "metrics", "activity", "response", "topics",
                     "messages", "methodology"],
    "contact": ["summary", "metrics", "activity", "topics", "timeline", "methodology"],
    "group": ["summary", "metrics", "participants", "activity", "events", "methodology"],
    "timeline": ["summary", "timeline", "methodology"],
    "media": ["summary", "media", "missing", "methodology"],
    "recovery": ["summary", "findings", "methodology"],
    "ai": ["summary", "ai", "methodology"],
    "search": ["summary", "messages", "methodology"],
    "custom": ["summary", "metrics", "methodology"],
}


def _kpi(label: str, value: Any, hint: str = "") -> dict[str, Any]:
    return {"type": "kpi", "label": label, "value": value, "hint": hint}


def _table(title: str, columns: list[str], rows: list[list[Any]],
           note: str = "") -> dict[str, Any]:
    return {"type": "table", "title": title, "columns": columns, "rows": rows,
            "note": note}


def _text(title: str, body: str) -> dict[str, Any]:
    return {"type": "text", "title": title, "body": body}


def _bar(title: str, labels: list[str], values: list[float], note: str = "") -> dict:
    return {"type": "chart", "chart": "bar", "title": title, "labels": labels,
            "series": [{"name": "count", "values": values}], "note": note}


def _line(title: str, labels: list[str], values: list[float], note: str = "") -> dict:
    return {"type": "chart", "chart": "line", "title": title, "labels": labels,
            "series": [{"name": "count", "values": values}], "note": note}


def _heatmap(title: str, grid: list[list[int]], weekdays: list[str]) -> dict:
    return {"type": "chart", "chart": "heatmap", "title": title, "grid": grid,
            "labels": weekdays, "note": "UTC weekday x hour message counts"}


def build(conn, case_id: str, report_type: str = "case",
          options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    case = cases_mod.get_case(conn, case_id)
    sections_requested = options.get("sections") or DEFAULT_SECTIONS.get(
        report_type, DEFAULT_SECTIONS["case"])
    conversation_id = options.get("conversation_id")
    contact_id = options.get("contact_id")
    date_from = options.get("date_from")
    date_to = options.get("date_to")
    include_messages = bool(options.get("include_messages", True))
    message_limit = int(options.get("message_limit", 500))

    blocks: list[dict[str, Any]] = []
    overview = metrics.overview(conn, case_id, conversation_id=conversation_id,
                                date_from=date_from, date_to=date_to)
    evidence = db.rows_to_list(conn.execute(
        "SELECT original_name, source_type, size_bytes, sha256, imported_at,"
        " message_count, date_order, parse_confidence FROM evidence_sources"
        " WHERE case_id=? ORDER BY imported_at", (case_id,)))

    title = REPORT_TYPES.get(report_type, "Report")
    scope_bits = []
    if conversation_id:
        conv = conn.execute("SELECT title FROM conversations WHERE id=?",
                            (conversation_id,)).fetchone()
        if conv:
            scope_bits.append(f"conversation '{conv['title']}'")
    if contact_id:
        c = conn.execute("SELECT display_name FROM contacts WHERE id=?",
                         (contact_id,)).fetchone()
        if c:
            scope_bits.append(f"contact '{c['display_name']}'")
    if date_from or date_to:
        scope_bits.append(f"date range {date_from or 'start'} to {date_to or 'end'}")

    if "summary" in sections_requested:
        blocks.append(_kpi("Messages", overview["real_messages"]))
        blocks.append(_kpi("Conversations", overview["conversations"]))
        blocks.append(_kpi("Contacts", overview["contacts"]))
        blocks.append(_kpi("Groups", overview["groups"]))
        blocks.append(_kpi("Media messages", overview["media_messages"]))
        blocks.append(_kpi("Active days", overview["active_days"]))
        blocks.append(_text(
            "Scope",
            (f"This report covers {overview['real_messages']} message records from "
             f"{len(evidence)} evidence source(s)"
             + (f", restricted to {', '.join(scope_bits)}" if scope_bits else "")
             + f". Activity window {overview['first_at'] or 'n/a'} to "
               f"{overview['last_at'] or 'n/a'} (UTC).")))

    if "metrics" in sections_requested:
        blocks.append(_table(
            "Communication metrics",
            ["Metric", "Value"],
            [["Total messages", overview["messages"]],
             ["Incoming", overview["incoming"]],
             ["Outgoing", overview["outgoing"]],
             ["System messages", overview["system_messages"]],
             ["Media messages", overview["media_messages"]],
             ["Voice notes", overview["voice_notes"]],
             ["Links shared", overview["links"]],
             ["Deleted markers", overview["deleted_markers"]],
             ["Edited markers", overview["edited_markers"]],
             ["Average message length (chars)", overview["avg_message_length"]],
             ["Average messages / active day", overview["avg_messages_per_active_day"]]],
            note="Incoming/outgoing is derived from the contact flagged as the device owner."))

    if "activity" in sections_requested:
        daily = metrics.activity_series(conn, case_id, "day", conversation_id=conversation_id,
                                        date_from=date_from, date_to=date_to)
        series = daily["series"]
        if report_type in ("case", "custom"):
            monthly = metrics.activity_series(conn, case_id, "month",
                                              conversation_id=conversation_id)
            blocks.append(_line("Messages per month",
                                [s["bucket"] for s in monthly["series"]],
                                [s["count"] for s in monthly["series"]]))
        blocks.append(_line("Messages per day (last 60 active days)",
                            [s["bucket"] for s in series[-60:]],
                            [s["count"] for s in series[-60:]]))
        grid = metrics.heatmap(conn, case_id, conversation_id=conversation_id)["grid"]
        blocks.append(_heatmap("Activity heatmap", grid, metrics.WEEKDAYS))
        if daily["inactivity"]["longest_gaps"]:
            blocks.append(_table(
                "Longest inactivity periods",
                ["From", "To", "Days"],
                [[g["from"], g["to"], g["days"]]
                 for g in daily["inactivity"]["longest_gaps"][:5]]))

    if "response" in sections_requested:
        response = metrics.response_times(conn, case_id, conversation_id=conversation_id,
                                          date_from=date_from, date_to=date_to)
        blocks.append(_kpi("Median response (min)",
                           response["median_minutes"] if response["median_minutes"] else "n/a"))
        blocks.append(_table(
            "Response-time distribution",
            ["Bucket", "Pairs"],
            [[b["label"], b["count"]] for b in response["histogram"]],
            note=(f"Pairs: {response['samples']}; session breaks excluded: "
                  f"{response['excluded_session_breaks']}; group chats: "
                  f"{response['methodology']['group_chats']}.")))

    if "topics" in sections_requested:
        words = metrics.word_frequency(conn, case_id, conversation_id=conversation_id,
                                       contact_id=contact_id, limit=25)
        blocks.append(_bar("Most frequent terms", [w["word"] for w in words["words"]],
                           [w["count"] for w in words["words"]]))
        emojis = metrics.emoji_frequency(conn, case_id, conversation_id=conversation_id)
        if emojis["emojis"]:
            blocks.append(_table("Most used emoji", ["Emoji", "Count"],
                                 [[e["emoji"], e["count"]] for e in emojis["emojis"][:15]]))

    if "contacts" in sections_requested:
        rows = []
        for c in metrics.contacts(conn, case_id)[:25]:
            rows.append([c["display_name"], c["messages"], c["incoming"], c["outgoing"],
                         c["media_messages"], c["first_seen"] or "", c["last_seen"] or ""])
        blocks.append(_table(
            "Contact ranking", ["Contact", "Messages", "Incoming", "Outgoing", "Media",
                                "First seen", "Last seen"], rows,
            note="Observed message counts only."))

    if "conversations" in sections_requested:
        rows = [[c["title"], c["kind"], c["message_count"], c["media_count"],
                 c["first_at"] or "", c["last_at"] or ""]
                for c in metrics.conversation_summaries(conn, case_id)[:30]]
        blocks.append(_table(
            "Conversations", ["Title", "Type", "Messages", "Media", "First", "Last"], rows))

    if "participants" in sections_requested and conversation_id:
        group = metrics.group_analysis(conn, case_id, conversation_id)
        blocks.append(_table(
            "Participant contribution",
            ["Participant", "Messages", "Share %", "Media", "Avg length", "First", "Last"],
            [[p["name"], p["messages"], p["share"], p["media"], p["avg_length"],
              p["first_at"], p["last_at"]] for p in group["participants"]],
            note=f"Gini coefficient: {group['participation_balance']['gini']}"))

    if "events" in sections_requested and conversation_id:
        events = db.rows_to_list(conn.execute(
            "SELECT occurred_at, event_type, actor, target, raw_text FROM group_events"
            " WHERE conversation_id=? ORDER BY occurred_at LIMIT 200", (conversation_id,)))
        blocks.append(_table("Group events", ["When", "Type", "Actor", "Raw"],
                             [[e["occurred_at"], e["event_type"], e["actor"] or "",
                               (e["raw_text"] or "")[:120]] for e in events],
                             note="Only events recorded in the export are listed."))

    if "timeline" in sections_requested:
        rows = db.rows_to_list(conn.execute(
            "SELECT occurred_at, kind, title FROM timeline_events WHERE case_id=?"
            " ORDER BY occurred_at LIMIT 200", (case_id,)))
        msg_rows = db.rows_to_list(conn.execute(
            "SELECT m.sent_at_utc, m.sender_raw, substr(m.body,1,120) AS body, c.title"
            " FROM messages m JOIN conversations c ON c.id=m.conversation_id"
            " WHERE m.case_id=? ORDER BY m.sent_at_utc LIMIT 200", (case_id,)))
        combined = ([{"when": r["occurred_at"], "kind": r["kind"], "detail": r["title"]}
                     for r in rows]
                    + [{"when": r["sent_at_utc"], "kind": "message",
                        "detail": f"{r['sender_raw']} in {r['title']}: {r['body']}"}
                       for r in msg_rows])
        combined.sort(key=lambda r: r["when"])
        blocks.append(_table("Unified timeline", ["When (UTC)", "Type", "Detail"],
                             [[c["when"], c["kind"], c["detail"][:200]]
                              for c in combined[:200]]))

    if "media" in sections_requested:
        media = db.rows_to_list(conn.execute(
            "SELECT file_name, media_type, size_bytes, sha256, missing, duration_ms"
            " FROM attachments WHERE case_id=? ORDER BY created_at DESC LIMIT 300",
            (case_id,)))
        blocks.append(_table(
            "Media inventory",
            ["File", "Type", "Bytes", "SHA-256", "Present", "Duration ms"],
            [[m["file_name"], m["media_type"], m["size_bytes"],
              (m["sha256"] or "")[:32], "no" if m["missing"] else "yes",
              m["duration_ms"] or ""] for m in media]))
        dupes = __import__("wfs_engine.media", fromlist=["duplicates"]).duplicates(conn, case_id)
        if dupes["exact_duplicates"]:
            blocks.append(_table("Duplicate media (identical SHA-256)", ["SHA-256", "Count"],
                                 [[d["sha256"][:32], d["count"]]
                                  for d in dupes["exact_duplicates"]]))

    if "missing" in sections_requested:
        missing = __import__("wfs_engine.media", fromlist=["missing_media"]).missing_media(
            conn, case_id)
        blocks.append(_table(
            "Media placeholders without files",
            ["When (UTC)", "Sender", "Type", "Conversation"],
            [[p["sent_at_utc"], p["sender_raw"], p["message_type"], p["conversation"]]
             for p in missing["placeholders"][:100]],
            note=missing["note"]))

    if "findings" in sections_requested:
        findings = recovery.analyze(conn, case_id)
        blocks.append(_table(
            "Recovery and discrepancy findings",
            ["Classification", "Summary"],
            [[recovery.CLASSIFICATIONS.get(f["status"], f["status"]), f["summary"]]
             for f in findings["findings"][:150]],
            note="; ".join(findings["limitations"])))
        flags = anomalies.detect(conn, case_id,
                                sensitivity=float(options.get("sensitivity", 3.0)))
        if flags["findings"]:
            blocks.append(_table(
                "Statistical anomalies",
                ["Kind", "Date", "Observed", "Baseline", "Deviation"],
                [[f["kind"], f.get("date") or "-", f["observed"], f["baseline_median"],
                  f["deviation"]] for f in flags["findings"][:40]],
                note=flags["disclaimer"]))

    if "ai" in sections_requested:
        queries = db.rows_to_list(conn.execute(
            "SELECT question, answer, provider, model, status, created_at FROM ai_queries"
            " WHERE case_id=? ORDER BY created_at DESC LIMIT 10", (case_id,)))
        for q in queries:
            blocks.append(_text(
                f"AI question ({q['created_at']}, {q['provider']}/{q['model']}, "
                f"status {q['status']})",
                f"Q: {q['question']}\n\nA: {q['answer']}"))
        blocks.append(_text(
            "AI interpretation labelling",
            "Everything in this section is a generated interpretation over retrieved "
            "evidence. It is not a forensic finding and must not be presented as one."))

    if "messages" in sections_requested and include_messages:
        clauses = ["m.case_id=?"]
        params: list[Any] = [case_id]
        if conversation_id:
            clauses.append("m.conversation_id=?")
            params.append(conversation_id)
        if contact_id:
            clauses.append("m.sender_id=?")
            params.append(contact_id)
        where = " AND ".join(clauses)
        rows = db.rows_to_list(conn.execute(
            f"SELECT m.sent_at_utc, m.sender_raw, m.body, m.message_type, c.title,"
            f" m.source_ref FROM messages m JOIN conversations c ON c.id=m.conversation_id"
            f" WHERE {where} ORDER BY m.sent_at_utc LIMIT ?", (*params, message_limit)))
        blocks.append(_table(
            "Message records (verbatim)",
            ["When (UTC)", "Sender", "Conversation", "Type", "Text", "Source ref"],
            [[r["sent_at_utc"], r["sender_raw"], r["title"], r["message_type"],
              (r["body"] or "")[:400], r["source_ref"]] for r in rows],
            note=f"Capped at {message_limit} records for this report."))

    if "evidence" in sections_requested:
        blocks.append(_table(
            "Evidence inventory",
            ["File", "Type", "Bytes", "SHA-256", "Imported", "Messages", "Date order"],
            [[e["original_name"], e["source_type"], e["size_bytes"], e["sha256"],
              e["imported_at"], e["message_count"], e["date_order"] or ""]
             for e in evidence],
            note="SHA-256 of each original is recorded at ingestion and re-verifiable."))

    if "methodology" in sections_requested or True:
        blocks.append(_text(
            "Methodology",
            "Messages were parsed from the supplied exports without modifying the "
            "originals; every record keeps its source line/row reference, its original "
            "timestamp string and a normalised UTC value. Statistics are computed with "
            "SQL aggregates over those records. Response times pair a message with the "
            "next message from a different sender inside the same conversation, dropping "
            "pairs separated by more than 60 minutes. Media metadata is reported as "
            "found; it can be absent or manipulated and is not proof of authenticity."))
        blocks.append(_text(
            "Data limitations",
            "Coverage is limited to the imported artifacts. WhatsApp exports truncate "
            "history, omit media that was not included, and contain no delivery or "
            "read receipts. Deleted message text is never reconstructed."))

    return {
        "title": title,
        "case": {"id": case["id"], "case_number": case["case_number"],
                 "name": case["name"], "examiner": case["examiner"],
                 "description": case["description"],
                 "authorization": case["authorization_statement"]},
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "engine_version": ENGINE_VERSION,
        "report_type": report_type,
        "scope": scope_bits,
        "options": options,
        "blocks": blocks,
        "evidence": evidence,
        "disclaimer": ("This report was produced with WhatsApp Forensic Studio AI from "
                       "user-supplied evidence. It is an analytical work product, not an "
                       "independent forensic certification, and it makes no claim of "
                       "legal admissibility."),
        "signature": {
            "report_sha256_note": ("The exported file's SHA-256 is stored in the reports "
                                   "table so a recipient can verify it was not altered "
                                   "after export."),
        },
    }
