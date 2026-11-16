# Troubleshooting

## The application says "Forensic engine unavailable"

1. Development: start the engine yourself and confirm it answers:
   ```bash
   cd forensic-engine && PYTHONPATH=. WFS_DATA_DIR=../.wfs-data ../.venv/bin/python -m wfs_engine.cli serve --port 8765
   curl http://127.0.0.1:8765/api/health
   ```
2. Desktop build: the sidecar must exist beside the executable
   (`wfs-engine.exe`). If it is missing, the bundle was produced without
   `scripts/build_sidecar.sh`; rebuild with `scripts/build_windows.ps1`.
3. Check the log directory (`%APPDATA%\WhatsAppForensicStudio\data\logs`). Startup
   errors name the failing stage; logs never contain message text.

## "Request failed: HTTP 401"

The webview is talking to an engine started with a different session token.
Close every engine process, restart the application (the shell mints a new token
on launch), and do not point the UI at a manually started engine with a different
`WFS_TOKEN`.

## Port already in use

The shell allocates an ephemeral port and retries three times. A manual
development server on 8765 is independent; stop it if you want the shell to
manage the engine.

## "no such module: fts5"

The bundled SQLite lacks FTS5. On Windows the engine ships its own consistent
SQLite build through the frozen sidecar; if you run from source, use a CPython
build with FTS5 enabled (`python -c "import sqlite3;print(sqlite3.sqlite_version)"`).
Search degrades to `LIKE` only if FTS5 is truly unavailable, which is reported in
Settings → Diagnostics.

## Import succeeded but fewer messages than expected

* **Date order** — ambiguous `DD/MM` vs `MM/DD` exports default to a proven order
  when the data decides it, otherwise to month-first with confidence 0.6 and an
  `ambiguous_date_order` notice. Re-import with an explicit date order in the
  Import Center.
* **Time zone** — timestamps are interpreted in the selected source time zone;
  DST-ambiguous local times are flagged rather than silently shifted.
* **Duplicates** — identical records already present are skipped (default) or
  stored as another observation. Duplicate detection uses a fingerprint with an
  ordinal suffix, so genuinely repeated identical messages are kept.
* **Encoding** — exports are decoded as UTF-8 with a Latin-1/CP1252 fallback;
  undecodable bytes are preserved and reported, never dropped silently.

## Media shows as "unlinked" or missing

WhatsApp text exports usually contain `<Media omitted>` and do not name files, so
no association is invented. Import the media-inclusive ZIP to link attachments;
the Media → Missing media tab lists placeholders and unreferenced files
separately.

## PDF report is blank or shows boxes

ReportLab needs a font covering the script in use. The renderer tries
Noto/DejaVu families and falls back to Helvetica; Malayalam, Tamil and Arabic
may need `fonts-noto` (Linux) or the Noto fonts installed on Windows. Missing
glyphs are reported in the report's methodology section rather than silently
dropped.

## AI answers are unavailable

* Ollama not running: start it and pull a model (`ollama pull llama3.1`), then
  refresh Settings → AI.
* Model not selected: pick one from the installed list.
* AI disabled: the toggle is off by default for external providers; local
  Ollama is used only when enabled.
* Without a model the assistant still returns retrieved evidence and computed
  statistics with `status: unavailable` — that is expected, not a defect.

## Transcription is unavailable

Install `whisper.cpp` (with a model) or `faster-whisper`, or set the model name in
Settings. Playback, waveform and duration keep working without any STT engine.

## Import of a large archive feels slow

Text import is the tuned path (see benchmarks in the README). Media analysis,
thumbnails, transcription and AI are separate background stages. Cancel a job
from the Import Center; the job stops at the next batch boundary and records why.

## "database is locked"

One writer at a time is the SQLite model. Close a second engine instance pointed
at the same `WFS_DATA_DIR`; the API serialises writes, but two processes do not.

## Backup restore

Backups are encrypted with a passphrase (AES-256-GCM, scrypt). Restore from
Welcome → Restore backup into a **new** case; existing cases are never
overwritten. A forgotten passphrase cannot be recovered — that is the point.

## Uninstall removed the application but kept my data

That is intended. Case directories and the database live in the user data folder.
Remove them deliberately (and remember that secure deletion on SSDs cannot be
guaranteed by software).

## Collecting diagnostics

Settings → Diagnostics shows engine version, Python, SQLite, FTS5 availability,
data paths, disk usage, AI/STT status and media tool detection. Include that
panel when reporting a problem; it contains counts and paths only.
