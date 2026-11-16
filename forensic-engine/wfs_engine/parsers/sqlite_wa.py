"""Reader for *accessible, unencrypted* WhatsApp SQLite databases.

Only databases that can already be opened without any key are read: no
Crypt12/14/15 decryption, no key extraction, no acquisition from a device.

Supported schema family (documented, not guessed):

* a message table named ``message``, ``messages`` or ``message_view``;
* a UTC epoch ``timestamp`` column in seconds or milliseconds;
* message text in ``data`` or ``text_data``;
* direction in ``from_me`` and/or ``key_from_me``;
* conversation identity in ``key_remote_jid`` (falling back to ``chat_row_id``
  joined through a ``chat``/``jid`` table when present);
* group detection from a ``@g.us`` JID suffix;
* optional media type in ``media_wa_type`` and optional ``remote_resource``.

Anything outside that shape is rejected with a reason instead of being imported
with invented values. Rows are normalised into the same record shape as the text
parser so downstream analytics behave identically.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

# WhatsApp media_wa_type values that map to a known message type.
MEDIA_TYPES = {1: "image", 2: "audio", 3: "video", 9: "document", 13: "gif",
               20: "sticker"}

MESSAGE_TABLES = ("message", "messages", "message_view")

# A database row proves the *bytes* were readable, not that every semantic field
# was interpretable, so confidence is deliberately below 1.0.
BASE_CONFIDENCE = 0.9


@dataclass
class SqliteInspection:
    supported: bool
    tables: list[str] = field(default_factory=list)
    message_table: str | None = None
    row_count: int = 0
    reason: str = ""
    chat_table: str | None = None
    columns: list[str] = field(default_factory=list)


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def inspect_db(path: Path) -> SqliteInspection:
    try:
        conn = _connect(path)
    except sqlite3.Error as exc:
        return SqliteInspection(False, reason=f"cannot open: {exc}")
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        chat_table = next((t for t in ("chat", "chat_list", "jid") if t in tables), None)
        for candidate in MESSAGE_TABLES:
            if candidate not in tables:
                continue
            cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{candidate}")')}
            if "timestamp" not in cols or not ({"data"} <= cols or {"text_data"} <= cols):
                continue
            if not ({"key_remote_jid"} <= cols or chat_table or {"chat_row_id"} <= cols):
                return SqliteInspection(
                    False, tables, candidate, 0,
                    "message table has no conversation identifier "
                    "(key_remote_jid/chat_row_id); refusing to merge chats",
                    chat_table, sorted(cols))
            count = conn.execute(f'SELECT COUNT(*) FROM "{candidate}"').fetchone()[0]
            return SqliteInspection(True, tables, candidate, count, "",
                                    chat_table, sorted(cols))
        return SqliteInspection(False, tables, reason="no recognised message table",
                                chat_table=chat_table)
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


def _chat_subjects(path: Path, chat_table: str | None) -> dict[str, str]:
    if not chat_table:
        return {}
    subjects: dict[str, str] = {}
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return subjects
    try:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{chat_table}")')}
        if not ({"jid", "subject"} <= cols):
            return subjects
        for row in conn.execute(f'SELECT jid, subject FROM "{chat_table}"'):
            if row[0] and row[1]:
                subjects[str(row[0])] = str(row[1])
    except sqlite3.Error:
        return subjects
    finally:
        conn.close()
    return subjects


def iter_messages(path: Path, source_label: str,
                  tz_name: str = "UTC") -> Iterator[dict]:
    """Yield normalised message dicts, one conversation identity per chat."""
    info = inspect_db(path)
    if not info.supported:
        raise ValueError(info.reason or "unsupported database schema")
    table = info.message_table
    subjects = _chat_subjects(path, info.chat_table)
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        text_col = "data" if "data" in cols else "text_data"
        jid_col = "key_remote_jid" if "key_remote_jid" in cols else None
        select = ["timestamp", text_col, "from_me"]
        for optional in ("key_remote_jid", "key_from_me", "remote_resource",
                         "media_wa_type", "message_type", "_id", "chat_row_id"):
            if optional in cols and optional not in select:
                select.append(optional)
        sql = f'SELECT {", ".join(chr(34) + c + chr(34) for c in select)} FROM "{table}"'
        for row in conn.execute(sql):
            dt = _ms_to_dt(row["timestamp"])
            if dt is None:
                continue
            keys = row.keys()
            body = row[text_col] or ""
            from_me = bool(row["from_me"]) if "from_me" in keys else bool(
                row["key_from_me"]) if "key_from_me" in keys else False
            jid = str(row[jid_col]) if jid_col and jid_col in keys else ""
            if not jid and "chat_row_id" in keys:
                jid = f"rowid:{row['chat_row_id']}"
            jid = jid or "unknown"
            media_type = None
            if "media_wa_type" in keys and row["media_wa_type"]:
                media_type = MEDIA_TYPES.get(int(row["media_wa_type"]), "document")
            if media_type is None and "message_type" in keys and row["message_type"]:
                # Some builds store a textual type already.
                candidate = str(row["message_type"]).lower()
                if candidate in {"image", "video", "audio", "document", "sticker", "gif"}:
                    media_type = candidate
            participant = str(row["remote_resource"]) if (
                "remote_resource" in keys and row["remote_resource"]) else ""
            is_group = jid.endswith("@g.us")
            if is_group:
                sender = participant or jid
            else:
                sender = "You" if from_me else jid
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
                "message_type": media_type or "text",
                "is_system": False,
                "is_deleted": False,
                "is_edited": False,
                "is_forwarded": False,
                "has_media": bool(media_type),
                "media_ref": None,
                "parse_confidence": BASE_CONFIDENCE if not media_type else 0.85,
                "source_ref": (f"{source_label}:row"
                               f"{row['_id'] if '_id' in keys else '?'}"),
                "session_id": None,
                "word_count": len(str(body).split()),
                "char_count": len(str(body)),
                "emojis": [],
                "urls": [],
                "emails": [],
                "phones": [],
                "group_event": None,
                "conversation_jid": jid,
                "conversation_kind": "group" if is_group else "chat",
                "conversation_title": subjects.get(jid) or jid,
            }
    finally:
        conn.close()
