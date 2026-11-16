"""Application paths, settings defaults and constants.

Everything lives on the local machine. No paths are ever taken from imported
evidence, and no network location is used for evidence storage.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

APP_NAME = "WhatsAppForensicStudio"
ENGINE_VERSION = "1.0.0"

#: Message gaps longer than this are treated as conversation-session breaks and
#: are excluded from response-time pairing (documented methodology).
SESSION_GAP_MINUTES = 60

#: Hard limits that protect the host from hostile or malformed inputs.
MAX_FILE_BYTES = 4 * 1024 * 1024 * 1024          # 4 GiB per imported file
MAX_ARCHIVE_ENTRIES = 50_000
MAX_ARCHIVE_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
MAX_ARCHIVE_RATIO = 400                          # decompression bomb guard
MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024 * 1024

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "dark",
    "density": "comfortable",
    "language": "en",
    "date_format": "locale",
    "source_timezone": "UTC",
    "default_evidence_dir": "",
    "default_report_dir": "",
    "hash_verification": True,
    "validate_imports": True,
    "duplicate_handling": "skip",
    "audit_retention_days": 3650,
    "auto_backup": False,
    "auto_backup_interval_hours": 24,
    "application_lock": False,
    "ai_provider": "ollama",
    "ai_model": "llama3.1",
    "ai_embedding_model": "nomic-embed-text",
    "ai_context_length": 8192,
    "ai_temperature": 0.2,
    "ai_enabled": True,
    "ai_external_enabled": False,
    "ai_external_base_url": "",
    "transcription_model": "base",
    "transcription_model_path": "",
    "interpretive_analysis": True,
    "anomaly_sensitivity": 3.0,
    "report_theme": "graphite",
    "report_include_charts": True,
    "keyboard_shortcuts": True,
}


def data_dir() -> Path:
    """Root of all application data (cases, db, logs)."""
    override = os.environ.get("WFS_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    home = Path.home()
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return base / APP_NAME
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / APP_NAME


def cases_dir() -> Path:
    return data_dir() / "cases"


def db_path() -> Path:
    return data_dir() / "app.db"


def logs_dir() -> Path:
    return data_dir() / "logs"


def reports_dir() -> Path:
    return data_dir() / "reports"


def case_subdirs(root: Path) -> list[str]:
    return [
        "evidence/originals",
        "derived",
        "media",
        "thumbnails",
        "transcripts",
        "analysis",
        "reports",
        "exports",
        "logs",
    ]


def ensure_dirs() -> None:
    for p in (data_dir(), cases_dir(), logs_dir(), reports_dir()):
        p.mkdir(parents=True, exist_ok=True)


def read_settings_from(conn) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        rows = conn.execute("SELECT key, value_json FROM application_settings").fetchall()
    except Exception:  # noqa: BLE001 - settings table may not exist yet
        return merged
    for row in rows:
        try:
            merged[row["key"]] = json.loads(row["value_json"])
        except (ValueError, TypeError):
            continue
    return merged
