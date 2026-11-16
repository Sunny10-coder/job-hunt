# Changelog

All verification steps below were executed in the development sandbox except
where explicitly marked as requiring Windows.

## 1.0.1 — repair round

### Startup and packaging

* **Packaged sidecar never started.** The frozen executable was launched without
  its `serve` subcommand, so the installer shipped an app that could not reach
  the engine. The subcommand is now passed in both development and packaged
  modes.
* **Authenticated health check mismatch.** The Rust probe called `/api/health`
  without credentials while the engine requires the session token on every
  route. The probe now sends `Authorization: Bearer <session token>` in the
  request header; the token still never appears in the URL, the command line or
  the logs. `tests/unit/test_api_security.py` covers 401 without a token, 401
  with a wrong token and 200 with the session token.
* **Engine logs were discarded.** Stdout/stderr now go to
  `<data dir>/logs/engine.log` with a 5 MiB rotation, so startup failures are
  diagnosable without exposing chat content.
* **Migrations were missing from the frozen build.** `db.migrations_dir()` now
  resolves PyInstaller's `sys._MEIPASS` layout, `build_sidecar.sh` bundles
  `wfs_engine/migrations`, and a packaged build with no migrations fails loudly
  instead of silently creating an empty schema. Migration splitting also strips
  full-line SQL comments and rejects trigger bodies rather than truncating them.

### Data integrity

* **Cross-conversation deduplication.** Message fingerprints included only
  timestamp, sender and text, so identical content in two different chats merged
  into one record. The fingerprint is now scoped by conversation identity, and
  identity comes from the chat participants (or the database JID), not the
  export file name — so `export-1.txt` and `export-2.txt` of the same chat still
  reconcile. Schema change: migration `0003_conversation_identity.sql` adds
  `conversations.identity_key` and backfills legacy rows from their title.
* **SQLite imports collapsed into one conversation.** Accessible databases are
  now read per JID: 1:1 chats and groups become separate conversations with real
  subjects from the `chat` table when present, group senders come from
  `remote_resource`, and required columns are validated. Databases without a
  conversation identifier or timestamps are rejected with a reason instead of
  being imported under an invented chat name. Readable rows are scored 0.9/0.85
  confidence, never 1.0.
* **Partial restore.** Restore previously created the case first, swallowed row
  insert failures and continued. Now the archive is validated and staged before
  anything is written, every row insert is fatal, per-table insert counts are
  verified, and any failure deletes the half-built case (rows and files). Case
  settings, which were silently dropped before, are restored explicitly.
  Restores also enforce path containment and a 16 GiB expansion limit.

### Security

* **CORS prefix matching.** `Origin` was accepted when it merely started with a
  loopback prefix, so `http://localhost.evil.com` was reflected back. Origins
  are now validated by scheme, host and port against an exact loopback/Tauri
  allowlist, including rejection of userinfo and malformed ports.
* **Evidence products no longer overwrite each other.** Report, export and
  backup names used minute-resolution stamps; they now include milliseconds and
  a collision check that never returns an existing path.
* **Spreadsheet formula injection.** Imported chat text beginning with `=`, `+`,
  `-`, `@`, tab or CR is neutralised in XLSX and CSV output, so evidence can
  never execute as a formula.

### Verification

* `172 passed, 1 skipped` (`cd forensic-engine && PYTHONPATH=. ../.venv/bin/python -m pytest -q`).
  New suites: `tests/unit/test_safety.py`, `tests/unit/test_api_security.py`,
  `tests/unit/test_migrations.py`, `tests/integration/test_dedupe_conversations.py`,
  `tests/integration/test_sqlite_conversations.py`,
  `tests/integration/test_restore_atomic.py`,
  `tests/integration/test_report_safety.py`.
* Benchmark (`WFS_PERF=1 … pytest tests/perf -q -s`): 20,000 messages 2.87 s,
  100,000 messages 19.07 s. The participant pre-scan added for conversation
  identity did not regress the previous 19.82 s baseline.
* Not executable here: Rust compilation and Windows installer builds. The
  GitHub Actions workflow (`.github/workflows/ci.yml`) builds the sidecar, NSIS
  and MSI bundles on `windows-latest`, runs an authenticated smoke test of the
  frozen engine and uploads the artifacts. That workflow has not yet run in this
  environment.
