//! Tauri commands exposed to the webview.
//!
//! Everything here is deliberately narrow: no arbitrary filesystem traversal,
//! no shell execution, no network access. `open_path` refuses anything that is
//! not an absolute existing path, and secret commands are keyed to this
//! application's own service namespace.

use std::path::PathBuf;

use serde::Serialize;
use tauri::{AppHandle, State};

use crate::engine::{EngineInfo, EngineState};

const KEYRING_SERVICE: &str = "whatsapp-forensic-studio";

#[derive(Serialize)]
pub struct EngineHandle {
    base_url: String,
    token: String,
    port: u16,
}

impl From<EngineInfo> for EngineHandle {
    fn from(info: EngineInfo) -> Self {
        EngineHandle {
            base_url: info.base_url,
            token: info.token,
            port: info.port,
        }
    }
}

#[tauri::command]
pub fn engine_info(state: State<'_, EngineState>) -> Result<EngineHandle, String> {
    state.info().map(EngineHandle::from)
}

#[tauri::command]
pub fn restart_engine(state: State<'_, EngineState>) -> Result<EngineHandle, String> {
    state.restart().map(EngineHandle::from)
}

#[tauri::command]
pub fn app_info(app: AppHandle) -> Result<serde_json::Value, String> {
    // Report the same directory the engine receives through WFS_DATA_DIR, not
    // Tauri's own app-data key, so Diagnostics and the shell agree.
    let data_dir = crate::engine::data_dir()?;
    let log_dir = data_dir.join("logs");
    Ok(serde_json::json!({
        "name": "WhatsApp Forensic Studio AI",
        "version": app.package_info().version.to_string(),
        "data_dir": data_dir.to_string_lossy(),
        "log_dir": log_dir.to_string_lossy(),
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
    }))
}

/// Multi-select native picker for evidence files.
#[tauri::command]
pub async fn pick_evidence_files() -> Result<Vec<String>, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let picked = rfd::FileDialog::new()
            .set_title("Select authorised WhatsApp exports or media")
            .add_filter(
                "WhatsApp exports",
                &["txt", "zip", "db", "sqlite", "sqlite3", "json", "wfs-case"],
            )
            .add_filter(
                "Media",
                &[
                    "jpg", "jpeg", "png", "gif", "webp", "heic", "mp4", "3gp", "mov", "opus",
                    "ogg", "m4a", "mp3", "wav", "aac", "pdf", "vcf", "txt", "docx", "xlsx",
                ],
            )
            .add_filter("All files", &["*"])
            .pick_files();
        picked
            .unwrap_or_default()
            .into_iter()
            .map(|path| path.to_string_lossy().to_string())
            .collect::<Vec<String>>()
    })
    .await
    .map_err(|err| err.to_string())
}

#[tauri::command]
pub async fn pick_directory(title: Option<String>) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        rfd::FileDialog::new()
            .set_title(title.unwrap_or_else(|| "Select a folder".to_string()))
            .pick_folder()
            .map(|path| path.to_string_lossy().to_string())
    })
    .await
    .map_err(|err| err.to_string())
}

#[tauri::command]
pub async fn pick_save_path(
    suggested_name: Option<String>,
    filter_name: Option<String>,
    extensions: Option<Vec<String>>,
) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut dialog = rfd::FileDialog::new();
        if let Some(name) = suggested_name {
            dialog = dialog.set_file_name(name);
        }
        if let Some(extensions) = extensions {
            let owned: Vec<&str> = extensions.iter().map(String::as_str).collect();
            if !owned.is_empty() {
                dialog =
                    dialog.add_filter(filter_name.as_deref().unwrap_or("Files"), owned.as_slice());
            }
        }
        dialog
            .save_file()
            .map(|path| path.to_string_lossy().to_string())
    })
    .await
    .map_err(|err| err.to_string())
}

/* -------------------------------------------------------------------------- */
/* Credential storage                                                         */
/* -------------------------------------------------------------------------- */

fn keyring_entry(account: &str) -> Result<keyring::Entry, String> {
    if account.trim().is_empty() {
        return Err("an account name is required".to_string());
    }
    keyring::Entry::new(KEYRING_SERVICE, account).map_err(|err| err.to_string())
}

#[tauri::command]
pub fn save_secret(account: String, value: String) -> Result<(), String> {
    keyring_entry(&account)?
        .set_password(&value)
        .map_err(|err| format!("the operating-system credential store rejected the key: {err}"))
}

#[tauri::command]
pub fn read_secret(account: String) -> Result<Option<String>, String> {
    match keyring_entry(&account)?.get_password() {
        Ok(value) => Ok(Some(value)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(err) => Err(err.to_string()),
    }
}

#[tauri::command]
pub fn delete_secret(account: String) -> Result<(), String> {
    match keyring_entry(&account)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(err) => Err(err.to_string()),
    }
}

/* -------------------------------------------------------------------------- */
/* Reveal in file manager                                                     */
/* -------------------------------------------------------------------------- */

fn ensure_absolute(path: &str) -> Result<PathBuf, String> {
    let candidate = PathBuf::from(path);
    if !candidate.is_absolute() {
        return Err("only absolute paths can be opened".to_string());
    }
    if !candidate.exists() {
        return Err(format!("path does not exist: {}", candidate.display()));
    }
    Ok(candidate)
}

#[tauri::command]
pub fn open_path(path: String, reveal_only: Option<bool>) -> Result<(), String> {
    let target = ensure_absolute(&path)?;
    let reveal = reveal_only.unwrap_or(false);

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        let mut command = std::process::Command::new("explorer.exe");
        if reveal && target.is_file() {
            command.arg(format!("/select,{}", target.display()));
        } else {
            command.arg(&target);
        }
        // CREATE_NO_WINDOW: never flash a console window for a shell call.
        command.creation_flags(0x0800_0000);
        command
            .spawn()
            .map(|_| ())
            .map_err(|err| format!("could not open the path: {err}"))
    }

    #[cfg(target_os = "macos")]
    {
        let mut command = std::process::Command::new("open");
        if reveal {
            command.arg("-R");
        }
        command
            .arg(&target)
            .spawn()
            .map(|_| ())
            .map_err(|err| format!("could not open the path: {err}"))
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let dir = if reveal && target.is_file() {
            target
                .parent()
                .map(|p| p.to_path_buf())
                .unwrap_or(target.clone())
        } else {
            target.clone()
        };
        std::process::Command::new("xdg-open")
            .arg(dir)
            .spawn()
            .map(|_| ())
            .map_err(|err| format!("could not open the path: {err}"))
    }
}
