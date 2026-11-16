"""Reader for *accessible, unencrypted* WhatsApp SQLite databases.

Only databases that can already be opened without any key are read: no
Crypt12/14/15 decryption, no key extraction, no acquisition from a device.
Rows are normalised into the same record shape as the text parser so that all
downstream analytics work identically.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..hashing import message_fingerprint
from . import dates


@dataclass
class SqliteInspection:
    supported: bool
    tables: list[str] = field(default_factory=list)
    message_table: str | None = None
    row_count: int = 0
    reason: str = ""


LEGACY_COLUMNS = {"key_remote_jid", "data", "timestamp", "from_me"}


def inspect_db(path: Path) -> SqliteInspection:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return SqliteInspection(False, reason=f"cannot open: {exc}")
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for candidate in ("message", "messages", "message_view"):
            if candidate not in tables:
                continue
            cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{candidate}")')}
            if {"timestamp"} <= cols and ({"data"} <= cols or {"text_data"} <= cols):
                count = conn.execute(f'SELECT COUNT(*) FROM "{candidate}"').fetchone()[0]
                return SqliteInspection(True, tables, candidate, count)
        return SqliteInspection(False, tables, reason="no recognised message table")
    except sqlite3.Error as exc:
        return SqliteInspection(False, reason=f"schema read failed: {exc}")
    finally:
        conn.close()


def _ms_to_dt(value) -> datetime | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    if num > 10_000_000_000:      # milliseconds
        num /= 1000.0
    try:
        return datetime.fromtimestamp(num, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def iter_messages(path: Path, source_label: str, tz_name: str = "UTC") -> Iterator[dict]:
    """Yield normalised message dicts from an unencrypted msgstore-like DB."""
    info = inspect_db(path)
    if not info.supported:
        raise ValueError(info.reason or "unsupported database schema")
    table = info.message_table
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        text_col = "data" if "data" in cols else "text_data"
        jid_col = "key_remote_jid" if "key_remote_jid" in cols else None
        select = ["timestamp", text_col, "from_me"]
        if jid_col:
            select.append("key_remote_jid")
        for col in ("key_from_me", "remote_resource", "status", "message_type",
                    "_id", "media_mime_type"):
            if col in cols:
                select.append(col)
        sql = f'SELECT {", ".join(chr(34) + c + chr(34) for c in select)} FROM "{table}"'
        for row in conn.execute(sql):
            dt = _ms_to_dt(row["timestamp"])
            if dt is None:
                continue
            body = row[text_col] or ""
            from_me = bool(row["from_me"]) if "from_me" in row.keys() else False
            jid = row[jid_col] if jid_col and jid_col in row.keys() else ""
            sender = "You" if from_me else (jid or "Unknown")
            local = dt.astimezone(timezone.utc)
            yield {
                "sender_raw": sender,
                "original_timestamp": str(row["timestamp"]),
                "sent_at_local": local.strftime("%Y-%m-%dT%H:%M:%S"),
                "sent_at_utc": local.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tz_offset_min": 0,
                "tz_ambiguous": False,
                "raw_text": str(body),
                "body": str(body),
                "message_type": "text",
                "is_system": False,
                "is_deleted": False,
                "is_edited": False,
                "is_forwarded": False,
                "has_media": False,
                "media_ref": None,
                "source_ref": f"{source_label}:row{row['_id'] if '_id' in row.keys() else '?'}",
                "parse_confidence": 1.0,
                "content_hash": message_fingerprint(
                    local.strftime("%Y-%m-%dT%H:%M:%SZ"), sender, str(body), source_label),
                "session_id": None,
                "word_count": len(str(body).split()),
                "char_count": len(str(body)),
                "emojis": [],
                "urls": [],
                "emails": [],
                "phones": [],
                "group_event": None,
                "jid": jid,
            }
    finally:
        conn.close()
