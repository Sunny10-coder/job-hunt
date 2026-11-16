# Windows packaging

The installer is produced by Tauri from `src-tauri/tauri.conf.json`:

```powershell
pwsh -File scripts/build_windows.ps1
```

```
src-tauri/target/release/bundle/
  nsis/WhatsApp Forensic Studio AI_1.0.0_x64-setup.exe
  msi/WhatsApp Forensic Studio AI_1.0.0_x64_en-US.msi
src-tauri/target/release/whatsapp-forensic-studio.exe   (portable)
```

## What the installer does

| Setting | Value | Why |
| --- | --- | --- |
| `installMode` | `currentUser` | No elevation; installs under `%LOCALAPPDATA%\Programs`. |
| `webviewInstallMode` | `downloadBootstrapper` | WebView2 is installed only if missing. |
| `externalBin` | `binaries/wfs-engine` | The frozen engine is copied beside the executable. |
| `targets` | `nsis`, `msi` | Per-user setup plus an MSI for managed deployment. |
| Start menu shortcut | created by Tauri | Standard entry point. |

## Optional desktop shortcut

Tauri's NSIS template creates the Start menu shortcut. For a desktop shortcut,
enable the hook:

1. copy `installers/hooks.nsh` to a path inside the repo;
2. add to `bundle.windows.nsis` in `tauri.conf.json`:
   ```json
   "installerHooks": "../installers/hooks.nsh"
   ```
3. rebuild.

## Uninstall behaviour

The uninstaller removes the application, the WebView2 bundle and shortcuts.
**It never removes case data**, which lives in
`%APPDATA%\WhatsAppForensicStudio\` (database, cases, reports). Removing a case is
an explicit action inside the application.

## Reproducibility

* The engine sidecar is built from `forensic-engine/` with the pinned
  `requirements.txt`; rebuild it whenever engine code changes.
* `scripts/build_windows.ps1` runs the engine test suite before bundling, so a
  failing parser or integrity test stops the release.
* Version numbers appear in `package.json`, `src-tauri/Cargo.toml` and
  `src-tauri/tauri.conf.json`; bump all three together.
