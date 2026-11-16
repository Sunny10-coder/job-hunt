# Changelog

All verification steps below were executed in the development sandbox except
where explicitly marked as requiring Windows.

## Unreleased — Rust shell repair

### Rust shell

* **The desktop shell had never compiled.** `engine.rs` called
  `spawn_process(&port, ...)` with a `u16` reference, and both call sites failed
  with `E0308`. Fixed in bootstrap and restart. `cargo check` on the Windows
  target now finishes with no crate warnings.
* **Missing `rfd` dependency.** `commands.rs` used `rfd::FileDialog` for the
  native evidence, folder and save pickers, but `rfd` was absent from
  `Cargo.toml`, so the crate could not build. Added `rfd = "0.15"`.
* **Unused privileges removed.** `tauri-plugin-dialog`, `tauri-plugin-opener`
  and `tauri-plugin-shell` were dependencies that were never registered or
  called (native dialogs use `rfd` directly, and revealing a path uses the
  dedicated `open_path` command). The crates and their capability permissions
  (`dialog:default`, `opener:*`) are gone; the capability set is now `core:default`
  plus window title only.
* **Two data directories.** The shell created cases/logs under Tauri's
  app-data key while passing a different `WFS_DATA_DIR` to the engine, so
  Diagnostics and the filesystem could disagree. `engine::data_dir()` is now the
  single source of truth for the cases folder, logs, the engine environment and
  `app_info`.
* **Restart could leave the examiner with no engine.** The old code killed the
  running engine first and reused its port. It now starts a replacement on a
  fresh port, waits for its authenticated health check, and only then stops the
  previous process; a failed restart returns an error and leaves the running
  engine serving.
* **Credential store is now functional end to end.** Settings → AI can store or
  remove the external-provider key through `save_secret`/`delete_secret`; the
  shell reads it from the OS credential store at spawn time and passes it to the
  engine in its environment only (never argv, disk, database or logs). The UI
  also calls `restart_engine` after changing the key, and reveals generated
  reports and backups with `open_path`.
* **CI smoke test used the wrong database.** The engine writes `app.db`
  (`config.db_path()`), not `wfs.db`; the Windows workflow now verifies
  `app.db` exists and is non-empty, and also runs `cargo fmt --check` and
  `cargo check --locked` before building the installers. `src-tauri/Cargo.lock`
  is committed for reproducible builds.

### Verification for this round

* `rustc 1.100.0` / `cargo 1.100.0` installed with rustup in the sandbox.
* `cargo check --target x86_64-pc-windows-msvc` — **passes**, no warnings from
  the crate. `cargo fmt --check` — clean.
* `npx tsc --noEmit` and `npm run build` — pass.
* `PYTHONPATH=. python -m pytest -q` — 172 passed, 1 skipped.
* The Linux host target cannot be checked here: no root, so `libglib2.0-dev`,
  `libgtk-3-dev` and `libwebkit2gtk-4.1-dev` cannot be installed. The Windows
  target check needed a stand-in `llvm-rc` for `tauri-winres` resource embedding
  only; rustc type-checked the crate for the real target. A genuine link and
  installer build still requires CI's `windows-latest`.

## Unreleased — repair round

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
