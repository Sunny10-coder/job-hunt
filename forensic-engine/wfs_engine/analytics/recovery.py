"""Message recovery / snapshot comparison analysis.

Only supportable statements are produced. Deleted message text is never
reconstructed: a deletion marker is reported as an *indicator*, and any
interpretation is kept in the AI layer, labelled as a hypothesis.
"""
from __future__ import annotations

from typing import Any

from .. import db

CLASSIFICATIONS = {
    "recovered_from_evidence": "Recovered from surviving evidence",
    "present_in_earlier_snapshot": "Present in earlier snapshot",
    "deletion_indicator": "Deletion indicator detected",
    "missing_attachment": "Missing attachment",
    "unverified_discrepancy": "Unverified discrepancy",
    "not_recoverable": "Not recoverable from available evidence",
}


def _clear(conn, case_id: str) -> None:
    conn.execute("DELETE FROM recovery_findings WHERE case_id=?", (case_id,))


def analyze(conn, case_id: str, *, reparse: bool = False) -> dict[str, Any]:
    _clear(conn, case_id)
    rows: list[dict[str, Any]] = []

    def add(kind: str, status: str, summary: str, detail: dict[str, Any],
            message_id: str | None = None, evidence_id: str | None = None) -> None:
        findings_id = db.new_id()
        conn.execute(
            "INSERT INTO recovery_findings(id, case_id, kind, status, summary, detail_json,"
            " message_id, evidence_id, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (findings_id, case_id, kind, status, summary, db.json_dump(detail),
             message_id, evidence_id, db.now_utc()))
        rows.append({"id": findings_id, "kind": kind, "status": status,
                     "summary": summary, "detail": detail, "message_id": message_id,
                     "evidence_id": evidence_id})

    # 1. Deletion placeholders present in the export.
    for msg in conn.execute(
        "SELECT m.id, m.sent_at_utc, m.sender_raw, m.raw_text, m.conversation_id,"
        " c.title FROM messages m JOIN conversations c ON c.id=m.conversation_id"
        " WHERE m.case_id=? AND m.is_deleted=1 ORDER BY m.sent_at_utc", (case_id,)):
        add("deleted_message", "deletion_indicator",
            f"Deletion placeholder from {msg['sender_raw']} in '{msg['title']}'",
            {"raw_text": msg["raw_text"], "conversation": msg["title"],
             "note": "The export contains a deletion marker; the original text is not "
                     "present in any imported artifact."},
            msg["id"], None)

    # 2. Edited-message markers.
    for msg in conn.execute(
        "SELECT m.id, m.sent_at_utc, m.sender_raw, m.body, c.title FROM messages m"
        " JOIN conversations c ON c.id=m.conversation_id"
        " WHERE m.case_id=? AND m.is_edited=1 ORDER BY m.sent_at_utc", (case_id,)):
        add("edited_message", "unverified_discrepancy",
            f"Message marked as edited by {msg['sender_raw']} in '{msg['title']}'",
            {"body": msg["body"], "conversation": msg["title"],
             "note": "An edited-message marker was present; earlier wording is only "
                     "available if another imported snapshot preserves it."},
            msg["id"], None)

    # 3. Media placeholders without a resolved attachment.
    for row in conn.execute(
        "SELECT m.id, m.media_ref, m.message_type, m.sent_at_utc, c.title FROM messages m"
        " JOIN conversations c ON c.id=m.conversation_id"
        " WHERE m.case_id=? AND m.has_media=1 AND m.id NOT IN"
        " (SELECT COALESCE(message_id,'') FROM attachments)", (case_id,)):
        add("missing_attachment", "missing_attachment",
            f"{row['message_type']} placeholder without a media file in '{row['title']}'",
            {"placeholder": row["media_ref"], "conversation": row["title"],
             "note": "The export references media that is not present in the imported "
                     "artifacts."},
            row["id"], None)

    # 4. Media artifacts that no message could be linked to.
    for row in conn.execute(
        "SELECT id, file_name, sha256, size_bytes FROM attachments"
        " WHERE case_id=? AND linked=0", (case_id,)):
        add("unlinked_media", "unverified_discrepancy",
            f"Media artifact '{row['file_name']}' is not referenced by any message",
            {"file_name": row["file_name"], "sha256": row["sha256"],
             "note": "The file exists in the evidence but the export text does not name "
                     "it; association would be a guess and is not made."},
            None, None)

    # 5. Snapshot comparison across evidence items.
    comparisons = compare_snapshots(conn, case_id)
    for comp in comparisons:
        for missing in comp["only_in_a"][:200]:
            add("snapshot_difference", "present_in_earlier_snapshot",
                f"Message in '{comp['evidence_a']['original_name']}' is absent from "
                f"'{comp['evidence_b']['original_name']}' (conversation "
                f"'{missing['conversation']}')",
                {"message": missing, "snapshot_a": comp["evidence_a"]["id"],
                 "snapshot_b": comp["evidence_b"]["id"],
                 "note": "Absence in a later export does not prove deletion; it may "
                         "simply be outside that export's range."},
                missing["message_id"], comp["evidence_a"]["id"])
        for missing in comp["only_in_b"][:200]:
            add("snapshot_difference", "unverified_discrepancy",
                f"Message in '{comp['evidence_b']['original_name']}' is absent from "
                f"'{comp['evidence_a']['original_name']}'",
                {"message": missing, "snapshot_a": comp["evidence_a"]["id"],
                 "snapshot_b": comp["evidence_b"]["id"]},
                missing["message_id"], comp["evidence_b"]["id"])

    # 6. Low-confidence parse results.
    for row in conn.execute(
        "SELECT id, source_ref, parse_confidence FROM messages"
        " WHERE case_id=? AND parse_confidence < 0.7 LIMIT 500", (case_id,)):
        add("low_confidence_record", "unverified_discrepancy",
            f"Record parsed with confidence {row['parse_confidence']:.2f}",
            {"source_ref": row["source_ref"]}, row["id"], None)

    summary = conn.execute(
        "SELECT status, COUNT(*) AS c FROM recovery_findings WHERE case_id=?"
        " GROUP BY status", (case_id,)).fetchall()
    return {
        "findings": rows,
        "counts": {r["status"]: r["c"] for r in summary},
        "classifications": CLASSIFICATIONS,
        "comparisons": [{k: v for k, v in c.items() if k != "only_in_a" and k != "only_in_b"}
                        for c in comparisons],
        "limitations": [
            "Nothing is decrypted: Crypt12/14/15 databases and iPhone backups are out of scope.",
            "Deleted text is never reconstructed; only indicators and cross-snapshot "
            "differences are reported.",
            "A message missing from a later export may simply be outside that export's "
            "date range or excluded by the export settings.",
        ],
    }


def compare_snapshots(conn, case_id: str, evidence_a: str | None = None,
                      evidence_b: str | None = None) -> list[dict[str, Any]]:
    evidence = db.rows_to_list(conn.execute(
        "SELECT id, original_name, imported_at, message_count FROM evidence_sources"
        " WHERE case_id=? ORDER BY imported_at", (case_id,)))
    if evidence_a:
        evidence = [e for e in evidence if e["id"] == evidence_a]
    if evidence_b:
        evidence = [e for e in evidence if e["id"] == evidence_b]
    if len(evidence) < 2:
        return []

    # Compare per conversation: two exports of different chats are not comparable.
    per_evidence: dict[str, dict[str, set[str]]] = {e["id"]: {} for e in evidence}
    seen: dict[str, set[str]] = {e["id"]: set() for e in evidence}
    rows = conn.execute(
        "SELECT o.message_id, o.evidence_id, m.conversation_id FROM message_observations o"
        " JOIN messages m ON m.id=o.message_id WHERE o.evidence_id IN"
        f" ({','.join('?' * len(evidence))})", tuple(e["id"] for e in evidence))
    for row in rows:
        per_evidence[row["evidence_id"]].setdefault(row["conversation_id"], set()).add(
            row["message_id"])
        seen[row["evidence_id"]].add(row["message_id"])

    def details(message_ids: set[str]) -> list[dict[str, Any]]:
        if not message_ids:
            return []
        placeholders = ",".join("?" * len(message_ids))
        out = []
        for row in conn.execute(
                f"SELECT m.id, m.sent_at_utc, m.sender_raw, substr(m.body,1,200) AS body,"
                f" c.title FROM messages m JOIN conversations c ON c.id=m.conversation_id"
                f" WHERE m.id IN ({placeholders}) ORDER BY m.sent_at_utc", tuple(message_ids)):
            out.append({"message_id": row["id"], "sent_at_utc": row["sent_at_utc"],
                        "sender": row["sender_raw"], "body": row["body"],
                        "conversation": row["title"]})
        return out

    comparisons = []
    for i in range(len(evidence)):
        for j in range(len(evidence)):
            if i == j:
                continue
            a, b = evidence[i], evidence[j]
            convs_a = per_evidence[a["id"]]
            convs_b = per_evidence[b["id"]]
            shared_convs = set(convs_a) & set(convs_b)
            only_a: set[str] = set()
            only_b: set[str] = set()
            shared = 0
            for conv in shared_convs:
                only_a |= convs_a[conv] - convs_b[conv]
                only_b |= convs_b[conv] - convs_a[conv]
                shared += len(convs_a[conv] & convs_b[conv])
            if not shared_convs:
                continue
            comparisons.append({
                "evidence_a": a, "evidence_b": b,
                "only_in_a": details(only_a),
                "only_in_b": details(only_b),
                "shared": shared,
                "shared_conversations": len(shared_convs),
                "excluded_conversations": {
                    "only_in_a": len(set(convs_a) - shared_convs),
                    "only_in_b": len(set(convs_b) - shared_convs),
                },
                "method": ("Compares the set of normalised messages observed in each "
                           "evidence item, restricted to conversations present in both "
                           "snapshots (message_observations). Unrelated conversations "
                           "are never compared."),
            })
    return comparisons
