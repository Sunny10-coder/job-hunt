# WhatsApp Forensic Studio AI

A local-first Windows forensic workstation for analysing WhatsApp conversation
exports that **you own or are authorised to examine**.

Everything runs on your machine: evidence stays in a case directory on disk, the
database is SQLite, retrieval and search are local, and AI is optional and local
(Ollama) by default. There is no account, no telemetry, no cloud database and no
automatic synchronisation.

![stack](https://img.shields.io/badge/Tauri-2-24C8DB) ![stack](https://img.shields.io/badge/React-18-61DAFB) ![stack](https://img.shields.io/badge/Python-3.12-3776AB) ![stack](https://img.shields.io/badge/SQLite-FTS5-003B57)

---

## What it does

| Area | Capability |
| --- | --- |
| Case management | Independent cases, evidence inventory, authorisation record, notes, bookmarks, tags, audit log, chain of custody, encrypted backup, duplication |
| Import | WhatsApp TXT exports, media-inclusive ZIPs, standalone media, contact cards, accessible plain SQLite databases, previously exported case packages; streaming parser, provenance per record, import quality report |
| Explorer | Conversation list and message view with media, system events, deleted/edited/forwarded markers, source references, annotations |
| Search | FTS5 full text (boolean, phrase, prefix), exact and bounded regex modes, structured filters, saved searches, exportable results |
| Analytics | Volume and cadence, hourly/daily/weekly/monthly/weekday series, heatmaps, response times with documented session boundaries, participation balance, words/emojis/languages, sessions, anomalies (z-score / robust median) |
| Contacts & groups | Per-contact profiles, side-by-side comparison, group participant rankings, membership events |
| Network | Cytoscape graph of contacts, groups and (inferred, dashed) topics with metrics and PNG export |
| Timeline | Unified, filterable chronology of messages, media, events and annotations |
| Recovery | Deletion indicators, missing attachments, cross-snapshot differences — supportable findings only, never reconstructed text |
| Media | Gallery, EXIF/metadata inspection, hashing, exact and perceptual duplicates, missing-media report |
| Voice | Playback, waveform (when peaks are extractable), offline transcription, editable transcripts, transcript search |
| AI | Ollama by default, OpenAI-compatible optional; RAG over local records with sanitised context, validated citations, and an explicit observed/statistics/interpretation split |
| Reporting | PDF, HTML, XLSX, CSV, JSON for ten report templates with selectable sections, scope and theme |

## Architecture

```
┌──────────────────────────── Tauri 2 shell (Rust) ────────────────────────────┐
│  sidecar lifecycle · native file pickers · OS credential store · open path   │
│                                   │ HTTP/JSON (loopback, bearer token)       │
│  ┌────────────────────────────────▼───────────────────────────────────────┐  │
│  │  React + TypeScript + Vite + Tailwind  (webview, 17 screens)           │  │
│  └────────────────────────────────▲───────────────────────────────────────┘  │
└───────────────────────────────────│──────────────────────────────────────────┘
                                    │ 127.0.0.1:<ephemeral port>
                    ┌───────────────▼────────────────┐
                    │  Python 3.12 forensic engine   │
                    │  parsers · importer · search   │
                    │  analytics · media · audio     │
                    │  ai · reporting · HTTP API     │
                    └───────────────┬────────────────┘
                                    │
                         SQLite + FTS5  +  case directories
```

* **Rust** owns only process lifetime, native dialogs, credential storage and
  revealing paths. It performs no parsing and makes no network calls.
* **Python** is the forensic engine; it is frozen with PyInstaller into a
  `wfs-engine` sidecar so end users never install Python.
* **SQLite** is the single store, scoped by `case_id`, with FTS5 for search.

## Quick start (development)

```bash
npm install
python3 -m venv .venv
.venv/bin/pip install -r forensic-engine/requirements.txt

# terminal 1 - engine
cd forensic-engine && PYTHONPATH=. WFS_DATA_DIR=../.wfs-data ../.venv/bin/python -m wfs_engine.cli serve --port 8765

# terminal 2 - UI
npm run dev          # http://localhost:1420 (proxies /api to 127.0.0.1:8765)
```

Then open the app, create a case, and use **Load sample dataset** to populate it
with the synthetic multilingual fixtures.

Desktop shell (requires Rust + WebKitGTK on Linux / WebView2 on Windows):

```bash
npm run tauri:dev
```

## Tests and benchmarks

```bash
cd forensic-engine && PYTHONPATH=. ../.venv/bin/python -m pytest -q
WFS_PERF=1 PYTHONPATH=. ../.venv/bin/python -m pytest tests/perf -q   # 100k-message import
```

The parser, integrity, import, API, recovery, reporting and AI suites run offline
against synthetic fixtures in `forensic-engine/tests/fixtures/`. No real
conversation data is included anywhere in this repository. The current suite is
`172 passed, 1 skipped`; the skipped test requires a model or media tool that is
not installed in the sandbox.

The assistant has an end-to-end offline test that stands a stub
OpenAI-compatible endpoint on loopback
(`tests/integration/test_ai_stub_provider.py`) and proves that citations resolve
to stored message records, unresolved markers are stripped, the external
provider is never called while disabled, and instruction-like text inside
imported messages is neutralised in the prompt while the evidence row stays
byte-intact.

Measured on this development VM (Linux, Python 3.12, SQLite WAL):

| Workload | Time |
| --- | --- |
| 20,000 text messages | 2.87 s |
| 100,000 text messages | 19.07 s |
| Indexed FTS search over 20k messages | < 2 s |
| First page of a 5k-message conversation | < 1 s |

Bulk import commits once per 1,000-message batch (savepoint-scoped) instead of
once per statement; the same run before that change took 152.99 s for 100k, so
the numbers above are a measured improvement, not an estimate. The 60 s target
is an engineering goal that depends on storage and CPU; the benchmark asserts it
and will fail loudly on slower hardware.

## Windows build

`.github/workflows/ci.yml` builds the frozen sidecar, the NSIS and MSI bundles
on `windows-latest`, smoke-tests the frozen engine's authenticated health check
and uploads the installers as workflow artifacts. To build locally, on Windows
10/11 x64 with Rust (MSVC), Node 20+, Python 3.12 and WiX/NSIS provisioned by
Tauri:

```powershell
pwsh -File scripts/build_windows.ps1
```

Outputs `src-tauri/target/release/bundle/nsis/*.exe`,
`src-tauri/target/release/bundle/msi/*.msi` and the portable executable.
See [docs/SETUP.md](docs/SETUP.md) for prerequisites and
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for recovery steps.

## Repository layout

```
src/                     React application (pages, components, hooks, stores, lib)
src-tauri/               Rust shell: main.rs, engine.rs, commands.rs, capabilities
forensic-engine/         Python engine (parsers, importer, analytics, ai, reporting)
  wfs_engine/            engine package + migrations
  tests/                 unit, integrity, integration, api, perf suites + fixtures
scripts/                 icon generation, sidecar freeze, Windows build pipeline
installers/              NSIS/MSI notes and optional installer hooks
docs/                    setup, troubleshooting, user guide, architecture
```

## Scope and honest limits

* **Not implemented, by design:** iPhone backup acquisition, Crypt12/14/15
  decryption, key extraction, device acquisition, and anything that bypasses
  WhatsApp encryption.
* **Not reconstructed:** deleted text. Recovery reports indicators and
  cross-snapshot differences only; AI hypotheses are labelled and kept separate.
* Text-only exports frequently contain `<Media omitted>` without the file, so
  attachments are never guessed — they are reported as unlinked.
* Metadata (EXIF) is reported as found and never treated as proof of authenticity.
* Response times, sentiment and emotion indicators are estimates with documented
  formulas, not statements about people.
* The Windows installer must be produced on Windows; the build pipeline is
  provided and documented, and this repository cannot build it on Linux.

## Forensic guarantees added in the repair round

* **Chat identity, not file names.** A conversation is identified by the people
  in it (`conversations.identity_key`) or by the database JID, so two snapshots
  exported as `export-1.txt`/`export-2.txt` reconcile, while identical text sent
  at the same second in two different chats stays two messages. Legacy cases are
  backfilled by migration `0003_conversation_identity.sql`.
* **Readable is not the same as understood.** Rows from accessible SQLite
  databases are scored 0.9 (0.85 for media rows); databases without a
  conversation identifier or timestamps are rejected with an explanation rather
  than imported under an invented conversation name.
* **Restore is all-or-nothing.** Backups are validated and staged before
  anything is written, every row insert is fatal, per-table counts are verified,
  and a failure removes the half-built case instead of leaving a plausible but
  incomplete one.
* **Evidence products are never overwritten.** Reports, exports and backups get
  unique, never-reused paths; spreadsheet output escapes formula-leading text.
* **The API is closed by default.** The engine requires its per-session bearer
  token on every route (including `/api/health`) and only answers the desktop
  shell and loopback origins validated by exact scheme/host/port.
* **Migrations ship with the sidecar.** A packaged build without migrations
  refuses to start instead of creating an empty database.

See [docs/CHANGELOG.md](docs/CHANGELOG.md) for the defect list and the executed
verification results.

## Licence

MIT. Bundled third-party components keep their own licences (see
`docs/SETUP.md`).
