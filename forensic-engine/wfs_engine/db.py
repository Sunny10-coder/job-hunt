"""SQLite access layer: connection factory, migrations, small helpers."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import config

_MIGRATION_LOCK = threading.Lock()


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex
    return f"{prefix}{raw}" if prefix else raw


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or config.db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    # Import writes are batched; a larger page cache and memory-mapped reads
    # keep index maintenance off the critical path for 100k-message archives.
    conn.execute("PRAGMA cache_size=-65536")
    conn.execute("PRAGMA mmap_size=268435456")
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def batch(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Group many writes into one commit without assuming the caller's state.

    A SAVEPOINT works both in autocommit mode and inside an existing
    transaction, so batch importers can commit once per batch instead of once
    per statement, without breaking callers that already hold a transaction.
    """
    conn.execute("SAVEPOINT wfs_batch")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK TO wfs_batch")
        conn.execute("RELEASE wfs_batch")
        raise
    else:
        conn.execute("RELEASE wfs_batch")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def migrate(path: Path | None = None) -> list[int]:
    """Apply pending SQL migrations in version order. Idempotent."""
    applied: list[int] = []
    with _MIGRATION_LOCK, session(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        files = sorted(migrations_dir().glob("*.sql"))
        for f in files:
            try:
                version = int(f.name.split("_", 1)[0])
            except ValueError:
                continue
            if version in done:
                continue
            sql = f.read_text(encoding="utf-8")
            with transaction(conn):
                for statement in _split_statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES(?,?)",
                    (version, now_utc()),
                )
            applied.append(version)
    return applied


def _split_statements(sql: str) -> list[str]:
    """Split on semicolons outside of string literals and BEGIN..END blocks."""
    statements: list[str] = []
    buf: list[str] = []
    in_single = False
    for char in sql:
        if char == "'":
            in_single = not in_single
            buf.append(char)
            continue
        if char == ";" and not in_single:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            continue
        buf.append(char)
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def json_load(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_list(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def audit(conn: sqlite3.Connection, action: str, case_id: str | None = None,
          actor: str = "user", detail: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_logs(id, case_id, at, actor, action, detail_json)"
        " VALUES(?,?,?,?,?,?)",
        (new_id(), case_id, now_utc(), actor, action, json_dump(detail or {})),
    )


def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    return config.read_settings_from(conn)


def set_settings(conn: sqlite3.Connection, patch: dict[str, Any]) -> dict[str, Any]:
    ts = now_utc()
    with transaction(conn):
        for key, value in patch.items():
            if key not in config.DEFAULT_SETTINGS:
                continue
            conn.execute(
                "INSERT INTO application_settings(key, value_json, updated_at) VALUES(?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,"
                " updated_at=excluded.updated_at",
                (key, json_dump(value), ts),
            )
        audit(conn, "settings.update", None, "user", {"keys": sorted(patch.keys())})
    return get_settings(conn)
