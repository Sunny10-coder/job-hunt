"""Small safety helpers shared by reports, exports and backups.

Two problems live here because they are both "untrusted output" issues:

* **Overwriting evidence products.** Report and export filenames used a
  minute-resolution timestamp, so two products generated in the same minute
  silently replaced each other. ``unique_path`` never returns an existing path.
* **Spreadsheet formula injection.** Excel and LibreOffice evaluate cells that
  begin with ``=``, ``+``, ``-`` or ``@`` (and control-character variants), so
  imported chat text could execute as a formula. ``spreadsheet_safe`` prefixes
  such values with an apostrophe, which both applications render as literal text.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def stamp_now() -> str:
    """Filesystem-safe UTC stamp with millisecond resolution."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3] + "Z"


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Return a non-existing path inside *directory*; never clobbers a file.

    A deterministic counter is used instead of randomness so repeated exports
    stay sortable, reviewable and reproducible in support conversations.
    """
    directory.mkdir(parents=True, exist_ok=True)
    safe_stem = "".join(ch for ch in stem if ch.isalnum() or ch in "-_") or "output"
    candidate = directory / f"{safe_stem}-{stamp_now()}.{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{safe_stem}-{stamp_now()}-{counter}.{suffix}"
        counter += 1
    return candidate


def spreadsheet_safe(value):
    """Neutralise formula-leading strings coming from untrusted evidence."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value
