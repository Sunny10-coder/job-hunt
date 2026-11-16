# Setup

## 1. Supported platforms

| Component | Requirement |
| --- | --- |
| Application | Windows 10/11 64-bit (primary). Linux/macOS work for development. |
| Node.js | 20 LTS or newer (build only) |
| Python | 3.12 x64 (build only; end users never install Python) |
| Rust | stable with the `x86_64-pc-windows-msvc` target (build only) |
| Windows tooling | Visual Studio Build Tools (C++ workload), WebView2 runtime |

End users need **none** of the above: the installer ships the frozen engine and
relies on the bundled WebView2 bootstrapper.

## 2. Install dependencies

```bash
npm ci
python3 -m venv .venv
.venv/bin/pip install -r forensic-engine/requirements.txt

# Rust shell (1.77+). On Windows install the MSVC build tools and WebView2;
# on Linux install webkit2gtk-4.1 / gtk3 development packages.
rustup toolchain install stable
rustup component add rustfmt clippy
```

Verify the Rust shell at any time:

```bash
cargo fmt --manifest-path src-tauri/Cargo.toml --check
cargo check --manifest-path src-tauri/Cargo.toml
# headless Linux without GTK/WebKit dev packages:
cargo check --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-msvc
```

`forensic-engine/requirements.txt` pins the runtime libraries used for reports
and crypto:

* `reportlab` - PDF rendering
* `openpyxl` - XLSX reporting
* `Pillow` - thumbnails, perceptual hashes, icons
* `cryptography` - AES-256-GCM case backups (scrypt key derivation)
* `pytest` - test suite (development)

Optional external binaries, discovered at runtime:

| Tool | Enables |
| --- | --- |
| `ffprobe` / `ffmpeg` | video/audio duration, codecs, keyframes, waveforms |
| `exiftool` | richer EXIF for images and video |
| `whisper.cpp` or `faster-whisper` | offline speech-to-text |
| Ollama | local LLM answers |

Missing tools degrade features; they never block imports or analysis.

## 3. Run in development

Engine (terminal 1):

```bash
cd forensic-engine
PYTHONPATH=. WFS_DATA_DIR=../.wfs-data .venv/../.venv/bin/python -m wfs_engine.cli serve --port 8765
```

UI (terminal 2):

```bash
npm run dev            # Vite on :1420, /api proxied to 127.0.0.1:8765
```

Desktop shell (terminal 3, optional):

```bash
npm run tauri:dev      # shell starts the engine itself
```

In `tauri dev` the Rust shell launches the engine from source using `python`
(or `$WFS_PYTHON`) with `WFS_DATA_DIR` under the platform app-data folder.

## 4. Environment variables

| Variable | Used by | Meaning |
| --- | --- | --- |
| `WFS_DATA_DIR` | engine | Root for `app.db` and `cases/`. Defaults to the platform app-data directory. |
| `WFS_TOKEN` | engine | Bearer token required on every `/api` request. The shell generates one per session. |
| `WFS_LOG_DIR` | engine | Diagnostic log directory (never contains chat content). |
| `WFS_PYTHON` | shell (dev) | Interpreter used to launch the engine from source. |
| `OPENAI_API_KEY` | engine | Optional external-provider key. The desktop shell reads it from the OS credential store (Settings → AI) and passes it only in the engine's environment. |
| `WFS_PERF` | tests | `1` enables the 100k-message import benchmark. |
| `OLLAMA_HOST` | engine | Ollama endpoint, default `http://127.0.0.1:11434`. |

## 5. First investigation

1. Launch the application. The status panel confirms the engine, database and
   FTS5 are ready.
2. **Create case** — enter a name, examiner and the authorisation declaration
   (the statement is stored with the case and appears in reports).
3. **Load sample dataset** (synthetic, clearly labelled) or import your own
   export from the Import Center.
4. Review the import quality report: source type, detected date order and
   confidence, parsed/failed records, participants, media placeholders.
5. Explore, search, analyse, bookmark findings, then generate a report.

## 6. Build the Windows package

```powershell
pwsh -File scripts/build_windows.ps1
```

Order of operations (the script performs all of it):

1. verify Rust MSVC target, Node and Python;
2. `npm ci` and a `.venv` with `forensic-engine/requirements.txt`;
3. freeze the engine: `bash scripts/build_sidecar.sh x86_64-pc-windows-msvc`
   → `src-tauri/binaries/wfs-engine-x86_64-pc-windows-msvc.exe`;
4. `pytest` for the engine;
5. `npm run build` (typecheck + Vite production build);
6. `npm run tauri:build` → NSIS and MSI installers.

`src-tauri/tauri.conf.json` declares the sidecar with
`"externalBin": ["binaries/wfs-engine"]`, so Tauri copies it next to the
executable; the shell resolves it from the application directory at launch.

## 7. Where data lives

```
%APPDATA%\studio.forensic.whatsapp\        app data (Tauri)
%APPDATA%\WhatsAppForensicStudio\data\
  app.db                                   SQLite + FTS5
  cases\CASE-0001\
    manifest.json  evidence\originals\  derived\  media\  thumbnails\
    transcripts\  analysis\  reports\  exports\  logs\
```

Application binaries live in `%LOCALAPPDATA%\Programs\...`; case data is never
inside the install directory, so uninstalling never removes evidence.

## 8. Verification checklist after install

```text
[ ] application launches from the Start menu
[ ] engine health is green on the welcome screen
[ ] a case can be created and reopened after a restart
[ ] importing forensic-engine/tests/fixtures/android_24h.txt yields messages
[ ] search returns rows and clicking one opens the source record
[ ] a PDF report is generated and opens
[ ] the case directory still exists after uninstall
```
