"""Communication analytics computed from imported records.

Every function documents its own formula. Nothing here infers intent, affection
or personality: the outputs are counts, durations and distributions of observed
messages only.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .. import db, textutil
from ..config import SESSION_GAP_MINUTES
from ..parsers.dates import parse_utc_iso

WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def self_contact(conn, case_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM contacts WHERE case_id=? AND is_self=1 LIMIT 1", (case_id,)).fetchone()
    return dict(row) if row else None


def _where(case_id: str, *, conversation_id: str | None = None,
           contact_id: str | None = None, date_from: str | None = None,
           date_to: str | None = None, include_system: bool = True) -> tuple[str, list]:
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
    if not include_system:
        clauses.append("m.is_system=0")
    return " AND ".join(clauses), params


def overview(conn, case_id: str, *, conversation_id: str | None = None,
             date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    where, params = _where(case_id, conversation_id=conversation_id,
                           date_from=date_from, date_to=date_to)
    self_row = self_contact(conn, case_id)
    self_id = self_row["id"] if self_row else None

    totals = conn.execute(
        f"SELECT COUNT(*) AS messages,"
        f" COUNT(DISTINCT m.conversation_id) AS conversations,"
        f" COUNT(DISTINCT m.sender_id) AS senders,"
        f" SUM(CASE WHEN m.is_system=0 THEN 1 ELSE 0 END) AS real_messages,"
        f" SUM(CASE WHEN m.has_media=1 THEN 1 ELSE 0 END) AS media,"
        f" SUM(CASE WHEN m.message_type='audio' THEN 1 ELSE 0 END) AS voice_notes,"
        f" SUM(CASE WHEN m.is_deleted=1 THEN 1 ELSE 0 END) AS deleted,"
        f" SUM(CASE WHEN m.is_edited=1 THEN 1 ELSE 0 END) AS edited,"
        f" SUM(m.char_count) AS chars,"
        f" MIN(m.sent_at_utc) AS first_at, MAX(m.sent_at_utc) AS last_at,"
        f" COUNT(DISTINCT substr(m.sent_at_utc,1,10)) AS active_days"
        f" FROM messages m WHERE {where}", params).fetchone()

    outgoing = 0
    if self_id:
        outgoing = conn.execute(
            f"SELECT COUNT(*) FROM messages m WHERE {where} AND m.sender_id=?",
            (*params, self_id)).fetchone()[0]
    total = totals["messages"] or 0
    links = conn.execute(
        "SELECT COUNT(*) FROM message_references r JOIN messages m ON m.id=r.message_id"
        f" WHERE {where} AND r.ref_type='url'", params).fetchone()[0]
    groups = conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE case_id=? AND kind='group'",
        (case_id,)).fetchone()[0]
    contacts = conn.execute("SELECT COUNT(*) FROM contacts WHERE case_id=?", (case_id,)).fetchone()[0]
    active_days = totals["active_days"] or 0
    real = totals["real_messages"] or 0

    return {
        "messages": total,
        "real_messages": real,
        "system_messages": total - real,
        "conversations": totals["conversations"] or 0,
        "contacts": contacts,
        "groups": groups,
        "incoming": max(0, real - outgoing),
        "outgoing": outgoing,
        "media_messages": totals["media"] or 0,
        "voice_notes": totals["voice_notes"] or 0,
        "links": links,
        "deleted_markers": totals["deleted"] or 0,
        "edited_markers": totals["edited"] or 0,
        "active_days": active_days,
        "avg_messages_per_active_day": round(real / active_days, 2) if active_days else 0,
        "avg_message_length": round((totals["chars"] or 0) / total, 1) if total else 0,
        "first_at": totals["first_at"],
        "last_at": totals["last_at"],
        "has_self_contact": self_id is not None,
        "formula": (
            "Counts of stored message records after the active filter. Incoming/outgoing "
            "uses the contact marked as the device owner ('You'); if no exported message "
            "came from the owner, outgoing is 0 rather than estimated."),
    }


def activity_series(conn, case_id: str, granularity: str = "day", *,
                    conversation_id: str | None = None, contact_id: str | None = None,
                    date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    where, params = _where(case_id, conversation_id=conversation_id,
                           contact_id=contact_id, date_from=date_from, date_to=date_to)
    buckets = {
        "hour": "substr(m.sent_at_utc,12,2)",
        "day": "substr(m.sent_at_utc,1,10)",
        "week": "strftime('%Y-W%W', m.sent_at_utc)",
        "month": "substr(m.sent_at_utc,1,7)",
        "year": "substr(m.sent_at_utc,1,4)",
        "weekday": "CAST(strftime('%w', m.sent_at_utc) AS INTEGER)",
    }
    if granularity not in buckets:
        granularity = "day"
    expr = buckets[granularity]
    rows = conn.execute(
        f"SELECT {expr} AS bucket, COUNT(*) AS count, SUM(m.has_media) AS media"
        f" FROM messages m WHERE {where} AND m.is_system=0 GROUP BY bucket ORDER BY bucket",
        params).fetchall()
    series = []
    for row in rows:
        bucket = row["bucket"]
        if granularity == "weekday":
            bucket = WEEKDAYS[int(bucket)]
        elif granularity == "hour":
            bucket = f"{int(bucket):02d}:00"
        series.append({"bucket": bucket, "count": row["count"], "media": row["media"] or 0})

    # Inactivity gaps and bursts on the daily series.
    daily = _daily_counts(conn, case_id, conversation_id, date_from, date_to)
    return {
        "granularity": granularity,
        "series": series,
        "inactivity": _inactivity_report(daily),
        "bursts": _burst_report(daily),
        "formula": "Message counts grouped by UTC bucket of the normalised timestamp; "
                   "system notices excluded.",
    }


def _daily_counts(conn, case_id: str, conversation_id: str | None,
                  date_from: str | None, date_to: str | None) -> list[tuple[str, int]]:
    where, params = _where(case_id, conversation_id=conversation_id,
                           date_from=date_from, date_to=date_to)
    rows = conn.execute(
        f"SELECT substr(m.sent_at_utc,1,10) AS d, COUNT(*) AS c FROM messages m"
        f" WHERE {where} AND m.is_system=0 GROUP BY d ORDER BY d", params).fetchall()
    return [(r["d"], r["c"]) for r in rows]


def _inactivity_report(daily: list[tuple[str, int]], min_days: int = 7) -> dict[str, Any]:
    if len(daily) < 2:
        return {"longest_gaps": [], "method": "needs at least two active days"}
    gaps = []
    for (d1, _), (d2, _) in zip(daily, daily[1:]):
        delta = (datetime.fromisoformat(d2) - datetime.fromisoformat(d1)).days
        if delta >= min_days:
            gaps.append({"from": d1, "to": d2, "days": delta})
    gaps.sort(key=lambda g: g["days"], reverse=True)
    return {"longest_gaps": gaps[:10],
            "method": f"consecutive active-day boundaries with a gap of >= {min_days} days"}


def _burst_report(daily: list[tuple[str, int]], top: int = 5) -> list[dict[str, Any]]:
    if not daily:
        return []
    counts = [c for _, c in daily]
    mean = statistics.fmean(counts)
    stdev = statistics.pstdev(counts) or 1.0
    scored = [{"date": d, "count": c, "z": round((c - mean) / stdev, 2)}
              for d, c in daily if (c - mean) / stdev >= 2.0]
    scored.sort(key=lambda r: r["z"], reverse=True)
    return scored[:top]


def heatmap(conn, case_id: str, *, conversation_id: str | None = None,
            date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    where, params = _where(case_id, conversation_id=conversation_id,
                           date_from=date_from, date_to=date_to)
    rows = conn.execute(
        f"SELECT CAST(strftime('%w', m.sent_at_utc) AS INTEGER) AS wd,"
        f" CAST(substr(m.sent_at_utc,12,2) AS INTEGER) AS hr, COUNT(*) AS c"
        f" FROM messages m WHERE {where} GROUP BY wd, hr", params).fetchall()
    grid = [[0] * 24 for _ in range(7)]
    for row in rows:
        grid[row["wd"]][row["hr"]] = row["c"]
    return {
        "grid": grid,
        "weekdays": WEEKDAYS,
        "hours": [f"{h:02d}" for h in range(24)],
        "max": max((max(r) for r in grid), default=0),
        "formula": "Count of messages per (UTC weekday, UTC hour) cell.",
    }


def response_times(conn, case_id: str, *, conversation_id: str | None = None,
                   exclude_groups: bool = True, max_gap_minutes: int = SESSION_GAP_MINUTES,
                   date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    """Response latency between a message and the next message by a different sender.

    Methodology: within one conversation, ordered by timestamp, a response pair is
    (msg A by sender X, next msg B by sender Y != X). Pairs separated by more than
    ``max_gap_minutes`` are dropped as session breaks; system notices never count.
    Group chats are excluded by default because a single "response" is ambiguous.
    """
    where, params = _where(case_id, conversation_id=conversation_id,
                           date_from=date_from, date_to=date_to, include_system=False)
    if exclude_groups:
        where += " AND m.conversation_id IN (SELECT id FROM conversations WHERE kind='chat')"
    rows = conn.execute(
        f"SELECT m.conversation_id, m.sender_id, m.sent_at_utc FROM messages m"
        f" WHERE {where} ORDER BY m.conversation_id, m.sent_at_utc", params).fetchall()
    self_row = self_contact(conn, case_id)
    self_id = self_row["id"] if self_row else None

    deltas: list[float] = []
    by_direction: dict[str, list[float]] = defaultdict(list)
    per_contact: dict[str, list[float]] = defaultdict(list)
    prev = None
    excluded = 0
    for row in rows:
        if prev is not None and prev["conversation_id"] == row["conversation_id"]:
            if prev["sender_id"] != row["sender_id"]:
                gap = (parse_utc_iso(row["sent_at_utc"])
                       - parse_utc_iso(prev["sent_at_utc"])).total_seconds() / 60.0
                if gap <= max_gap_minutes:
                    deltas.append(gap)
                    direction = "self_replied" if row["sender_id"] == self_id else "peer_replied"
                    by_direction[direction].append(gap)
                    if row["sender_id"] and row["sender_id"] != self_id:
                        per_contact[row["sender_id"]].append(gap)
                else:
                    excluded += 1
        prev = row

    buckets = [(0, 1), (1, 5), (5, 15), (15, 60), (60, 240), (240, 1440), (1440, None)]
    hist = []
    for low, high in buckets:
        count = sum(1 for d in deltas if d >= low and (high is None or d < high))
        label = f"{low}-{high} min" if high else f">{low} min"
        hist.append({"label": label, "count": count})

    top_contacts = []
    for cid, values in sorted(per_contact.items(), key=lambda kv: len(kv[1]), reverse=True)[:10]:
        contact = conn.execute("SELECT display_name FROM contacts WHERE id=?", (cid,)).fetchone()
        top_contacts.append({
            "contact_id": cid,
            "contact": contact["display_name"] if contact else "unknown",
            "median_minutes": round(statistics.median(values), 1),
            "samples": len(values),
        })

    return {
        "samples": len(deltas),
        "excluded_session_breaks": excluded,
        "median_minutes": round(statistics.median(deltas), 1) if deltas else None,
        "average_minutes": round(statistics.fmean(deltas), 1) if deltas else None,
        "p90_minutes": round(sorted(deltas)[int(len(deltas) * 0.9)], 1) if deltas else None,
        "histogram": hist,
        "by_direction": {k: {"samples": len(v), "median": round(statistics.median(v), 1)}
                         for k, v in by_direction.items()},
        "per_contact": top_contacts,
        "methodology": {
            "pair_rule": "next message by a different sender in the same conversation",
            "session_gap_minutes": max_gap_minutes,
            "group_chats": "excluded" if exclude_groups else "included (ambiguous)",
            "system_messages": "excluded",
        },
    }


def word_frequency(conn, case_id: str, *, conversation_id: str | None = None,
                   contact_id: str | None = None, limit: int = 40,
                   date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    where, params = _where(case_id, conversation_id=conversation_id, contact_id=contact_id,
                           date_from=date_from, date_to=date_to, include_system=False)
    counter: Counter[str] = Counter()
    scanned = 0
    for row in conn.execute(
            f"SELECT m.body FROM messages m WHERE {where} AND m.body<>''", params):
        body = row["body"] or ""
        if textutil.media_placeholder_kind(body):
            continue  # '<Media omitted>' is metadata, not conversation content
        counter.update(textutil.tokenize(body))
        scanned += 1
    return {
        "scanned_messages": scanned,
        "words": [{"word": w, "count": c} for w, c in counter.most_common(limit)],
        "formula": "Whitespace/punctuation tokenisation, lowercased, stopwords removed; "
                   "counts per token occurrence (message bodies only, no attachments).",
    }


def emoji_frequency(conn, case_id: str, *, conversation_id: str | None = None,
                    limit: int = 30) -> dict[str, Any]:
    where, params = _where(case_id, conversation_id=conversation_id, include_system=False)
    counter: Counter[str] = Counter()
    for row in conn.execute(f"SELECT m.body FROM messages m WHERE {where}", params):
        counter.update(textutil.extract_emojis(row["body"] or ""))
    return {"emojis": [{"emoji": e, "count": c} for e, c in counter.most_common(limit)],
            "total": sum(counter.values())}


def language_mix(conn, case_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT body FROM messages WHERE case_id=? AND is_system=0 AND body<>''", (case_id,))
    counter: Counter[str] = Counter()
    for row in rows:
        counter[textutil.detect_language_guess(row["body"])] += 1
    return {"languages": [{"language": k, "count": v} for k, v in counter.most_common()],
            "method": "Unicode script detection per message (not a statistical language ID)"}


def conversation_summaries(conn, case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT c.*,"
        " (SELECT COUNT(*) FROM attachments a WHERE a.conversation_id=c.id) AS attachments,"
        " (SELECT COUNT(*) FROM bookmarks b JOIN messages m2 ON m2.id=b.message_id"
        "   WHERE m2.conversation_id=c.id) AS bookmarks,"
        " (SELECT COUNT(DISTINCT sender_id) FROM messages m3 WHERE m3.conversation_id=c.id"
        "   AND m3.sender_id IS NOT NULL) AS participants"
        " FROM conversations c WHERE c.case_id=? ORDER BY c.last_at DESC", (case_id,)).fetchall()
    self_row = self_contact(conn, case_id)
    self_id = self_row["id"] if self_row else None
    out = []
    for row in rows:
        item = dict(row)
        last = conn.execute(
            "SELECT body, sender_raw, message_type FROM messages WHERE conversation_id=?"
            " ORDER BY sent_at_utc DESC LIMIT 1", (row["id"],)).fetchone()
        item["last_message"] = last["body"][:160] if last else ""
        item["last_sender"] = last["sender_raw"] if last else ""
        item["last_message_type"] = last["message_type"] if last else ""
        if self_id:
            mine = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id=? AND sender_id=?",
                (row["id"], self_id)).fetchone()[0]
            item["outgoing"] = mine
            item["incoming"] = (row["message_count"] or 0) - mine
        else:
            item["outgoing"] = 0
            item["incoming"] = row["message_count"] or 0
        out.append(item)
    return out


def contacts(conn, case_id: str) -> list[dict[str, Any]]:
    self_row = self_contact(conn, case_id)
    self_id = self_row["id"] if self_row else None
    rows = conn.execute(
        "SELECT ct.*,"
        " (SELECT COUNT(*) FROM messages m WHERE m.sender_id=ct.id) AS messages,"
        " (SELECT COUNT(DISTINCT conversation_id) FROM messages m WHERE m.sender_id=ct.id)"
        "   AS conversations,"
        " (SELECT COUNT(*) FROM attachments a JOIN messages m ON m.id=a.message_id"
        "   WHERE m.sender_id=ct.id) AS attachments,"
        " (SELECT COUNT(*) FROM messages m WHERE m.sender_id=ct.id AND m.has_media=1)"
        "   AS media_messages"
        " FROM contacts ct WHERE ct.case_id=? ORDER BY messages DESC", (case_id,)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["is_self"] = bool(item["is_self"])
        peer = 0 if item["id"] == self_id else item["messages"]
        mine = 0
        if self_id and item["id"] != self_id:
            mine = conn.execute(
                "SELECT COUNT(*) FROM messages a JOIN messages b"
                " ON a.conversation_id=b.conversation_id AND b.sender_id=?"
                " WHERE a.sender_id=? AND a.case_id=?", (self_id, item["id"], case_id)
            ).fetchone()[0]
        item["incoming"] = peer
        item["outgoing"] = mine
        item["active_hours"] = _active_hours(conn, item["id"])
        out.append(item)
    return out


def _active_hours(conn, contact_id: str, top: int = 4) -> list[int]:
    rows = conn.execute(
        "SELECT CAST(substr(sent_at_utc,12,2) AS INTEGER) AS h, COUNT(*) AS c"
        " FROM messages WHERE sender_id=? GROUP BY h ORDER BY c DESC LIMIT ?",
        (contact_id, top)).fetchall()
    return [r["h"] for r in rows]


def contact_profile(conn, case_id: str, contact_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM contacts WHERE id=? AND case_id=?",
                       (contact_id, case_id)).fetchone()
    if not row:
        raise KeyError("contact not found")
    contact = dict(row)
    where, params = _where(case_id, contact_id=contact_id)
    stats = conn.execute(
        f"SELECT COUNT(*) AS messages, MIN(m.sent_at_utc) AS first_at,"
        f" MAX(m.sent_at_utc) AS last_at, SUM(m.has_media) AS media,"
        f" SUM(m.char_count) AS chars, COUNT(DISTINCT m.conversation_id) AS conversations"
        f" FROM messages m WHERE {where}", params).fetchone()
    hourly = {r["h"]: r["c"] for r in conn.execute(
        f"SELECT CAST(substr(m.sent_at_utc,12,2) AS INTEGER) AS h, COUNT(*) AS c"
        f" FROM messages m WHERE {where} GROUP BY h", params)}
    weekday = {r["d"]: r["c"] for r in conn.execute(
        f"SELECT CAST(strftime('%w', m.sent_at_utc) AS INTEGER) AS d, COUNT(*) AS c"
        f" FROM messages m WHERE {where} GROUP BY d", params)}
    monthly = [{"bucket": r["b"], "count": r["c"]} for r in conn.execute(
        f"SELECT substr(m.sent_at_utc,1,7) AS b, COUNT(*) AS c FROM messages m"
        f" WHERE {where} GROUP BY b ORDER BY b", params)]
    topics = [{"word": w, "count": c} for w, c in
              Counter(textutil.tokenize(" ".join(
                  r["body"] for r in conn.execute(
                      f"SELECT m.body FROM messages m WHERE {where} LIMIT 4000", params)
              ))).most_common(20)]
    groups = db.rows_to_list(conn.execute(
        "SELECT DISTINCT c.id, c.title FROM conversations c"
        " JOIN messages m ON m.conversation_id=c.id WHERE m.sender_id=? AND c.kind='group'",
        (contact_id,)))
    notes = db.rows_to_list(conn.execute(
        "SELECT * FROM investigation_notes WHERE case_id=? AND message_id IN"
        " (SELECT id FROM messages WHERE sender_id=?)", (case_id, contact_id)))
    tags = db.rows_to_list(conn.execute(
        "SELECT t.tag, COUNT(*) AS count FROM message_tags t JOIN messages m"
        " ON m.id=t.message_id WHERE m.sender_id=? GROUP BY t.tag", (contact_id,)))

    response = response_times(conn, case_id)
    per_contact = {c["contact_id"]: c for c in response["per_contact"]}
    first_moves = conn.execute(
        f"SELECT COUNT(*) FROM messages m WHERE {where} AND NOT EXISTS"
        f" (SELECT 1 FROM messages p WHERE p.conversation_id=m.conversation_id"
        f"  AND p.sent_at_utc < m.sent_at_utc)", params).fetchone()[0]

    return {
        "contact": contact,
        "messages": stats["messages"] or 0,
        "first_at": stats["first_at"],
        "last_at": stats["last_at"],
        "media_messages": stats["media"] or 0,
        "avg_length": round((stats["chars"] or 0) / stats["messages"], 1) if stats["messages"] else 0,
        "conversations": stats["conversations"] or 0,
        "hourly": [{"hour": f"{h:02d}:00", "count": hourly.get(h, 0)} for h in range(24)],
        "weekday": [{"day": WEEKDAYS[i], "count": weekday.get(i, 0)} for i in range(7)],
        "monthly": monthly,
        "topics": topics,
        "groups": groups,
        "notes": notes,
        "tags": tags,
        "conversation_initiations": first_moves,
        "response": per_contact.get(contact_id),
        "words": word_frequency(conn, case_id, contact_id=contact_id, limit=20)["words"],
        "emojis": emoji_frequency(conn, case_id, limit=10)["emojis"],
        "interpretation_note": (
            "Observed message behaviour only. No personality, intent or sentiment "
            "inference is made from these counts."),
    }


def compare_contacts(conn, case_id: str, contact_ids: list[str]) -> dict[str, Any]:
    profiles = []
    for cid in contact_ids[:6]:
        try:
            p = contact_profile(conn, case_id, cid)
        except KeyError:
            continue
        profiles.append({
            "contact_id": cid,
            "name": p["contact"]["display_name"],
            "messages": p["messages"],
            "media_messages": p["media_messages"],
            "avg_length": p["avg_length"],
            "active_hours": [h["hour"] for h in sorted(
                p["hourly"], key=lambda x: x["count"], reverse=True)[:3] if h["count"]],
            "median_response_minutes": (p["response"] or {}).get("median_minutes"),
            "top_topics": [t["word"] for t in p["topics"][:8]],
            "first_at": p["first_at"],
            "last_at": p["last_at"],
        })

    day_counts = [
        [0] * 24 for _ in profiles
    ]
    for idx, profile in enumerate(profiles):
        hours = {h["hour"]: h["count"] for h in
                 contact_profile(conn, case_id, profile["contact_id"])["hourly"]}
        for hour, count in hours.items():
            day_counts[idx][int(hour[:2])] = count
    return {
        "profiles": profiles,
        "hourly_matrix": day_counts,
        "note": "Comparison of observed message behaviour; not a psychological comparison.",
    }


def group_analysis(conn, case_id: str, conversation_id: str) -> dict[str, Any]:
    conv = conn.execute("SELECT * FROM conversations WHERE id=? AND case_id=?",
                        (conversation_id, case_id)).fetchone()
    if not conv:
        raise KeyError("conversation not found")
    where, params = _where(case_id, conversation_id=conversation_id)
    participants = db.rows_to_list(conn.execute(
        f"SELECT ct.id AS contact_id, ct.display_name AS name, COUNT(*) AS messages,"
        f" SUM(m.has_media) AS media, SUM(m.char_count) AS chars,"
        f" MIN(m.sent_at_utc) AS first_at, MAX(m.sent_at_utc) AS last_at"
        f" FROM messages m JOIN contacts ct ON ct.id=m.sender_id WHERE {where}"
        f" GROUP BY ct.id ORDER BY messages DESC", params))
    total = sum(p["messages"] for p in participants) or 1
    for p in participants:
        p["share"] = round(p["messages"] / total * 100, 2)
        p["avg_length"] = round((p["chars"] or 0) / p["messages"], 1) if p["messages"] else 0
    events = db.rows_to_list(conn.execute(
        "SELECT * FROM group_events WHERE conversation_id=? ORDER BY occurred_at",
        (conversation_id,)))
    monthly = [{"bucket": r["b"], "count": r["c"]} for r in conn.execute(
        f"SELECT substr(m.sent_at_utc,1,7) AS b, COUNT(*) AS c FROM messages m"
        f" WHERE {where} GROUP BY b ORDER BY b", params)]
    media = conn.execute(
        f"SELECT COUNT(*) FROM attachments a WHERE a.conversation_id=?",
        (conversation_id,)).fetchone()[0]
    return {
        "conversation": dict(conv),
        "participants": participants,
        "participation_balance": _balance([p["messages"] for p in participants]),
        "events": events,
        "monthly": monthly,
        "media_files": media,
        "words": word_frequency(conn, case_id, conversation_id=conversation_id, limit=25)["words"],
        "response": response_times(conn, case_id, conversation_id=conversation_id,
                                   exclude_groups=False),
        "note": ("Membership events are shown only where the export contains them. "
                 "Absence of an event is not evidence of absence of the event."),
    }


def _balance(counts: list[int]) -> dict[str, Any]:
    if not counts:
        return {"gini": 0, "top_share": 0}
    total = sum(counts) or 1
    ordered = sorted(counts)
    n = len(ordered)
    gini = (sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(ordered))) / (n * total)
    return {"gini": round(gini, 3), "top_share": round(max(counts) / total * 100, 1),
            "formula": "Gini coefficient of per-participant message counts; "
                       "0 = perfectly even."}


def sessions(conn, case_id: str, conversation_id: str | None = None,
             gap_minutes: int = SESSION_GAP_MINUTES, limit: int = 10) -> dict[str, Any]:
    where, params = _where(case_id, conversation_id=conversation_id, include_system=False)
    rows = conn.execute(
        f"SELECT m.conversation_id, m.sent_at_utc, m.sender_id FROM messages m"
        f" WHERE {where} ORDER BY m.conversation_id, m.sent_at_utc", params).fetchall()
    sessions_found: list[dict[str, Any]] = []
    current_start = None
    current_count = 0
    current_conv = None
    prev_ts = None
    senders: set[str] = set()
    for row in rows:
        ts = parse_utc_iso(row["sent_at_utc"])
        new_session = (
            prev_ts is None or row["conversation_id"] != current_conv
            or (ts - prev_ts).total_seconds() > gap_minutes * 60)
        if new_session and current_start is not None:
            sessions_found.append({
                "conversation_id": current_conv, "start": current_start.isoformat(),
                "end": prev_ts.isoformat(), "messages": current_count,
                "minutes": round((prev_ts - current_start).total_seconds() / 60, 1),
                "participants": len(senders)})
            current_count = 0
            senders = set()
        if new_session:
            current_start = ts
            current_conv = row["conversation_id"]
        current_count += 1
        if row["sender_id"]:
            senders.add(row["sender_id"])
        prev_ts = ts
    if current_start is not None and prev_ts is not None:
        sessions_found.append({
            "conversation_id": current_conv, "start": current_start.isoformat(),
            "end": prev_ts.isoformat(), "messages": current_count,
            "minutes": round((prev_ts - current_start).total_seconds() / 60, 1),
            "participants": len(senders)})
    sessions_found.sort(key=lambda s: (s["messages"], s["minutes"]), reverse=True)
    return {"sessions": sessions_found[:limit], "total_sessions": len(sessions_found),
            "gap_minutes": gap_minutes}


def participation_timeline(conn, case_id: str, conversation_id: str,
                           granularity: str = "month") -> dict[str, Any]:
    expr = {"month": "substr(sent_at_utc,1,7)", "day": "substr(sent_at_utc,1,10)",
            "week": "strftime('%Y-W%W', sent_at_utc)"}.get(
                granularity, "substr(sent_at_utc,1,7)")
    rows = conn.execute(
        f"SELECT {expr} AS b, COALESCE(ct.display_name,'(system)') AS name, COUNT(*) AS c"
        f" FROM messages m LEFT JOIN contacts ct ON ct.id=m.sender_id"
        f" WHERE m.case_id=? AND m.conversation_id=? GROUP BY b, name ORDER BY b",
        (case_id, conversation_id)).fetchall()
    buckets: dict[str, dict[str, int]] = defaultdict(dict)
    names: set[str] = set()
    for row in rows:
        buckets[row["b"]][row["name"]] = row["c"]
        names.add(row["name"])
    return {"buckets": [{"bucket": b, **counts} for b, counts in sorted(buckets.items())],
            "participants": sorted(names)}


def analytics_bundle(conn, case_id: str, *, conversation_id: str | None = None,
                     date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    """Everything the analytics dashboard needs, in one round trip."""
    return {
        "overview": overview(conn, case_id, conversation_id=conversation_id,
                             date_from=date_from, date_to=date_to),
        "hourly": activity_series(conn, case_id, "hour", conversation_id=conversation_id,
                                  date_from=date_from, date_to=date_to),
        "daily": activity_series(conn, case_id, "day", conversation_id=conversation_id,
                                 date_from=date_from, date_to=date_to),
        "weekly": activity_series(conn, case_id, "week", conversation_id=conversation_id,
                                  date_from=date_from, date_to=date_to),
        "monthly": activity_series(conn, case_id, "month", conversation_id=conversation_id,
                                   date_from=date_from, date_to=date_to),
        "weekday": activity_series(conn, case_id, "weekday", conversation_id=conversation_id,
                                   date_from=date_from, date_to=date_to),
        "heatmap": heatmap(conn, case_id, conversation_id=conversation_id,
                           date_from=date_from, date_to=date_to),
        "response": response_times(conn, case_id, conversation_id=conversation_id,
                                   date_from=date_from, date_to=date_to),
        "words": word_frequency(conn, case_id, conversation_id=conversation_id,
                                date_from=date_from, date_to=date_to),
        "emojis": emoji_frequency(conn, case_id, conversation_id=conversation_id),
        "languages": language_mix(conn, case_id),
        "sessions": sessions(conn, case_id, conversation_id=conversation_id),
        "top_contacts": contacts(conn, case_id)[:10],
        "conversations": conversation_summaries(conn, case_id)[:20],
    }
