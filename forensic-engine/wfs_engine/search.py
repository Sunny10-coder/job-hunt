"""Advanced search: FTS5, exact, and bounded regex over structured filters."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from . import db

MAX_REGEX_LENGTH = 300
REGEX_SCAN_LIMIT = 200_000
SNIPPET_START = "\u0002"
SNIPPET_END = "\u0003"


@dataclass
class SearchQuery:
    q: str = ""
    mode: str = "fts"                  # fts | exact | regex
    conversation_ids: list[str] = field(default_factory=list)
    sender_ids: list[str] = field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None
    media_type: str | None = None
    is_deleted: bool | None = None
    is_edited: bool | None = None
    bookmarked: bool | None = None
    tag: str | None = None
    has_url: bool | None = None
    has_phone: bool | None = None
    has_email: bool | None = None
    attachment_name: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    include_system: bool = False
    limit: int = 50
    offset: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchQuery":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def _filters(query: SearchQuery) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if query.conversation_ids:
        clauses.append(f"m.conversation_id IN ({','.join('?' * len(query.conversation_ids))})")
        params.extend(query.conversation_ids)
    if query.sender_ids:
        clauses.append(f"m.sender_id IN ({','.join('?' * len(query.sender_ids))})")
        params.extend(query.sender_ids)
    if query.date_from:
        clauses.append("m.sent_at_utc >= ?")
        params.append(query.date_from)
    if query.date_to:
        clauses.append("m.sent_at_utc <= ?")
        params.append(query.date_to if len(query.date_to) > 10 else query.date_to + "T23:59:59Z")
    if query.media_type:
        if query.media_type == "any":
            clauses.append("m.has_media = 1")
        else:
            clauses.append("m.message_type = ?")
            params.append(query.media_type)
    if query.is_deleted is not None:
        clauses.append("m.is_deleted = ?")
        params.append(1 if query.is_deleted else 0)
    if query.is_edited is not None:
        clauses.append("m.is_edited = ?")
        params.append(1 if query.is_edited else 0)
    if query.bookmarked:
        clauses.append("m.id IN (SELECT message_id FROM bookmarks WHERE case_id=m.case_id)")
    if query.tag:
        clauses.append("m.id IN (SELECT message_id FROM message_tags WHERE tag=?)")
        params.append(query.tag)
    if query.has_url:
        clauses.append("EXISTS (SELECT 1 FROM message_references r WHERE r.message_id=m.id"
                       " AND r.ref_type='url')")
    if query.has_phone:
        clauses.append("EXISTS (SELECT 1 FROM message_references r WHERE r.message_id=m.id"
                       " AND r.ref_type='phone')")
    if query.has_email:
        clauses.append("EXISTS (SELECT 1 FROM message_references r WHERE r.message_id=m.id"
                       " AND r.ref_type='email')")
    if query.attachment_name:
        clauses.append("EXISTS (SELECT 1 FROM attachments a WHERE a.message_id=m.id"
                       " AND a.file_name LIKE ?)")
        params.append(f"%{query.attachment_name}%")
    if query.min_length is not None:
        clauses.append("m.char_count >= ?")
        params.append(int(query.min_length))
    if query.max_length is not None:
        clauses.append("m.char_count <= ?")
        params.append(int(query.max_length))
    if not query.include_system:
        clauses.append("m.is_system = 0")
    return (" AND ".join(clauses) if clauses else "1=1"), params


def build_fts_expression(text: str) -> str:
    """Translate a friendly query into a safe FTS5 MATCH expression.

    Bare words are quoted so FTS operators in user text cannot raise syntax
    errors or change intent; AND / OR / NOT and quoted phrases are preserved.
    A trailing ``*`` becomes a prefix query.
    """
    tokens = re.findall(r'"[^"]*"|\(|\)|\bAND\b|\bOR\b|\bNOT\b|[^\s()"]+', text)
    out: list[str] = []
    term_count = 0
    for token in tokens:
        upper = token.upper()
        if upper in ("AND", "OR", "NOT"):
            out.append(upper)
        elif token in ("(", ")"):
            out.append(token)
        elif token.startswith('"'):
            phrase = token.strip('"').replace('"', '""')
            if phrase:
                out.append(f'"{phrase}"')
                term_count += 1
        elif token.endswith("*") and len(token) > 1:
            stem = token[:-1].replace('"', '""')
            if stem:
                out.append(f'"{stem}"*')
                term_count += 1
        else:
            cleaned = token.replace('"', '""')
            if cleaned:
                out.append(f'"{cleaned}"')
                term_count += 1
    if term_count == 0:
        return ""
    # A dangling boolean operator or bracket would be an FTS5 syntax error.
    while out and out[0] in ("AND", "OR", ")"):
        out.pop(0)
    while out and out[-1] in ("AND", "OR", "NOT", "("):
        out.pop()
    if not out:
        return ""
    if all(tok in ("AND", "OR", "NOT", "(", ")") for tok in out):
        return ""
    return " ".join(out)


def _snippet_tagged(text: str, query_text: str) -> str:
    """Mark query terms inside a body for highlighting without HTML injection."""
    terms = [t for t in re.findall(r"[^\s\"]+", query_text) if len(t) > 1]
    result = text
    for term in sorted(terms, key=len, reverse=True):
        try:
            pattern = re.compile(re.escape(term.strip("*")), re.IGNORECASE)
        except re.error:
            continue
        result = pattern.sub(lambda m: f"{SNIPPET_START}{m.group(0)}{SNIPPET_END}", result)
    return result[:400]


def search(conn, case_id: str, query: SearchQuery) -> dict[str, Any]:
    started = time.perf_counter()
    where, params = _filters(query)
    base = ("SELECT m.id, m.conversation_id, c.title AS conversation, m.sender_raw,"
            " m.sent_at_utc, m.sent_at_local, m.body, m.message_type, m.has_media,"
            " m.is_deleted, m.is_edited, m.source_ref, m.evidence_id, m.parse_confidence"
            " FROM messages m JOIN conversations c ON c.id=m.conversation_id")
    q = (query.q or "").strip()
    params = [case_id, *params]
    total = 0
    rows: list[Any] = []
    notes = []

    if not q and query.mode != "regex":
        sql = f"{base} WHERE m.case_id=? AND {where} ORDER BY m.sent_at_utc DESC LIMIT ? OFFSET ?"
        count_sql = f"SELECT COUNT(*) FROM messages m WHERE m.case_id=? AND {where}"
        total = conn.execute(count_sql, params).fetchone()[0]
        rows = conn.execute(sql, (*params, query.limit, query.offset)).fetchall()
    elif query.mode == "exact":
        sql = (f"{base} WHERE m.case_id=? AND {where} AND m.body LIKE ? ESCAPE '\\'"
               f" ORDER BY m.sent_at_utc DESC LIMIT ? OFFSET ?")
        count_sql = (f"SELECT COUNT(*) FROM messages m WHERE m.case_id=? AND {where}"
                     f" AND m.body LIKE ? ESCAPE '\\'")
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        total = conn.execute(count_sql, (*params, like)).fetchone()[0]
        rows = conn.execute(sql, (*params, like, query.limit, query.offset)).fetchall()
    elif query.mode == "regex":
        if len(q) > MAX_REGEX_LENGTH:
            raise ValueError(f"regex longer than {MAX_REGEX_LENGTH} characters")
        try:
            rx = re.compile(q, re.IGNORECASE | re.UNICODE)
        except re.error as exc:
            raise ValueError(f"invalid regular expression: {exc}") from exc
        candidates = conn.execute(
            f"{base} WHERE m.case_id=? AND {where} ORDER BY m.sent_at_utc DESC LIMIT ?",
            (*params, REGEX_SCAN_LIMIT)).fetchall()
        matched = [r for r in candidates if rx.search(r["body"] or "")]
        total = len(matched)
        rows = matched[query.offset: query.offset + query.limit]
        notes.append(f"Regex evaluated over the newest {REGEX_SCAN_LIMIT} matching rows.")
    else:
        fts_expr = build_fts_expression(q)
        if not fts_expr:
            return {"total": 0, "results": [], "took_ms": 0, "query": q}
        match_sql = (f"SELECT m.id, m.conversation_id, c.title AS conversation,"
                     f" m.sender_raw, m.sent_at_utc, m.sent_at_local, m.body,"
                     f" m.message_type, m.has_media, m.is_deleted, m.is_edited,"
                     f" m.source_ref, m.evidence_id, m.parse_confidence,"
                     f" snippet(messages_fts, 2, '{SNIPPET_START}', '{SNIPPET_END}', '…', 14)"
                     f" AS snippet FROM messages_fts f"
                     f" JOIN messages m ON m.id=f.message_id"
                     f" JOIN conversations c ON c.id=m.conversation_id"
                     f" WHERE messages_fts MATCH ? AND f.case_id=? AND {where}"
                     f" ORDER BY rank LIMIT ? OFFSET ?")
        count_sql = (f"SELECT COUNT(*) FROM messages_fts f JOIN messages m"
                     f" ON m.id=f.message_id WHERE messages_fts MATCH ? AND f.case_id=?"
                     f" AND {where}")
        try:
            total = conn.execute(count_sql, (fts_expr, *params)).fetchone()[0]
            rows = conn.execute(match_sql, (fts_expr, *params, query.limit,
                                            query.offset)).fetchall()
        except Exception as exc:  # noqa: BLE001 - FTS syntax edge case
            raise ValueError(f"search expression could not be evaluated: {exc}") from exc
        notes.append(f"FTS expression: {fts_expr}")

    results = []
    for row in rows:
        item = dict(row)
        snippet = item.pop("snippet", None)
        if snippet is None:
            snippet = _snippet_tagged(item["body"] or "", q)
        item["snippet"] = snippet
        item["highlights"] = _highlight_ranges(item["body"] or "", snippet)
        results.append(item)

    return {
        "total": total,
        "results": results,
        "took_ms": round((time.perf_counter() - started) * 1000, 2),
        "query": q,
        "mode": query.mode,
        "notes": notes,
        "filters": {k: v for k, v in query.__dict__.items()
                    if v not in (None, [], "", False) and k not in ("q", "limit", "offset")},
    }


def _highlight_ranges(body: str, snippet: str) -> list[list[int]]:
    """Map snippet markers to (start, end) offsets inside the body."""
    ranges: list[list[int]] = []
    plain_parts = []
    offset_map: list[int] = []
    idx = 0
    while idx < len(snippet):
        if snippet[idx] == SNIPPET_START:
            idx += 1
            continue
        if snippet[idx] == SNIPPET_END:
            idx += 1
            continue
        plain_parts.append(snippet[idx])
        offset_map.append(idx)
        idx += 1
    plain = "".join(plain_parts)
    for match in re.finditer(re.escape(SNIPPET_START) + "(.*?)" + re.escape(SNIPPET_END),
                             snippet, re.S):
        word = match.group(1)
        found = plain.find(word)
        if found >= 0:
            start = body.find(word)
            if start >= 0:
                ranges.append([start, start + len(word)])
    return ranges


def suggestions(conn, case_id: str, prefix: str = "", limit: int = 12) -> list[dict[str, Any]]:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts_vocab USING fts5vocab(messages_fts, 'row')")
        rows = conn.execute(
            "SELECT term, cnt FROM fts_vocab WHERE term LIKE ? ORDER BY cnt DESC LIMIT ?",
            (f"{prefix.lower()}%", limit)).fetchall()
        return [{"term": r["term"], "count": r["cnt"]} for r in rows]
    except Exception:  # noqa: BLE001 - vocab table is optional
        return []


def save_search(conn, case_id: str, name: str, query: dict[str, Any]) -> dict[str, Any]:
    sid = db.new_id()
    conn.execute(
        "INSERT INTO saved_searches(id, case_id, name, query_json, created_at)"
        " VALUES(?,?,?,?,?)", (sid, case_id, name, db.json_dump(query), db.now_utc()))
    db.audit(conn, "search.save", case_id, "user", {"name": name})
    return {"id": sid, "name": name, "query": query}


def list_saved(conn, case_id: str) -> list[dict[str, Any]]:
    out = []
    for row in conn.execute(
            "SELECT * FROM saved_searches WHERE case_id=? ORDER BY created_at DESC",
            (case_id,)):
        out.append({"id": row["id"], "name": row["name"], "created_at": row["created_at"],
                    "query": db.json_load(row["query_json"], {})})
    return out


def delete_saved(conn, case_id: str, search_id: str) -> None:
    conn.execute("DELETE FROM saved_searches WHERE id=? AND case_id=?", (search_id, case_id))
