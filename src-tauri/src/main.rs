#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! WhatsApp Forensic Studio AI - desktop shell.
//!
//! The Rust layer owns exactly three things:
//!   1. the lifetime of the local Python forensic engine (sidecar process),
//!   2. native file/folder pickers so the webview never needs broad fs access,
//!   3. operating-system credential storage for optional external AI keys.
//!
//! It deliberately performs no forensic processing, holds no chat content and
//! makes no network calls of its own.

mod commands;
mod engine;

use engine::EngineState;
use tauri::Manager;

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle().clone();
            let state = engine::bootstrap(&handle)?;
            app.manage(state);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::engine_info,
            commands::app_info,
            commands::pick_evidence_files,
            commands::pick_directory,
            commands::pick_save_path,
            commands::save_secret,
            commands::read_secret,
            commands::delete_secret,
            commands::open_path,
            commands::restart_engine,
        ])
        .build(tauri::generate_context!())
        .expect("failed to build the application shell");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(state) = app_handle.try_state::<EngineState>() {
                state.shutdown();
            }
        }
    });
}
