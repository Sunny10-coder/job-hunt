//! Lifecycle management for the Python forensic engine sidecar.
//!
//! The engine is started on a loopback interface only, on an ephemeral port,
//! with a per-session bearer token passed through the environment (never the
//! command line, so it does not appear in process listings). The webview learns
//! the base URL and token through the `engine_info` command.

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use rand::RngCore;
use serde::Serialize;
use tauri::AppHandle;

#[derive(Debug, Clone, Serialize)]
pub struct EngineInfo {
    pub base_url: String,
    pub token: String,
    pub port: u16,
}

pub struct EngineState {
    info: Mutex<EngineInfo>,
    child: Mutex<Option<Child>>,
}

impl EngineState {
    pub fn info(&self) -> Result<EngineInfo, String> {
        self.info
            .lock()
            .map(|guard| guard.clone())
            .map_err(|_| "engine state poisoned".to_string())
    }

    pub fn shutdown(&self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }

    /// Start a replacement engine on a fresh port *before* stopping the old one.
    ///
    /// The previous implementation killed the running engine first and then
    /// reused its port, so a failed restart left the examiner with no engine at
    /// all. Now a failure returns an error while the original engine keeps
    /// serving, and only a readiness-checked replacement is published.
    pub fn restart(&self) -> Result<EngineInfo, String> {
        let token = self
            .info
            .lock()
            .map_err(|_| "engine state poisoned".to_string())?
            .token
            .clone();
        let port = free_port().map_err(|err| err.to_string())?;
        let mut child = spawn_process(port, &token)?;
        if !wait_until_ready(port, &token, Duration::from_secs(45)) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!(
                "the restarted engine on port {port} never answered /api/health; the previous engine is still running"
            ));
        }
        let info = EngineInfo {
            base_url: format!("http://127.0.0.1:{port}"),
            token,
            port,
        };
        if let Some(mut previous) = self
            .child
            .lock()
            .map_err(|_| "engine state poisoned".to_string())?
            .take()
        {
            let _ = previous.kill();
            let _ = previous.wait();
        }
        *self
            .info
            .lock()
            .map_err(|_| "engine state poisoned".to_string())? = info.clone();
        *self
            .child
            .lock()
            .map_err(|_| "engine state poisoned".to_string())? = Some(child);
        Ok(info)
    }
}

/// Create the data/log directories, start the engine and wait until it answers.
///
/// One canonical directory is used by the shell, the UI and the engine. The
/// shell previously created its folders under Tauri's app-data key while the
/// engine received a *different* `WFS_DATA_DIR`, so cases and logs could end up
/// in two places. `data_dir()` is now the only source of truth.
pub fn bootstrap(_app: &AppHandle) -> Result<EngineState, Box<dyn std::error::Error>> {
    let data_root = data_dir()?;
    let cases_root = data_root.join("cases");
    let log_root = data_root.join("logs");
    for dir in [&cases_root, &log_root] {
        std::fs::create_dir_all(dir)?;
    }

    let token = session_token();
    let mut last_error = String::from("the forensic engine did not start");

    for _ in 0..3 {
        let port = free_port()?;
        match spawn_process(port, &token) {
            Ok(mut child) => {
                if wait_until_ready(port, &token, Duration::from_secs(45)) {
                    let info = EngineInfo {
                        base_url: format!("http://127.0.0.1:{port}"),
                        token: token.clone(),
                        port,
                    };
                    return Ok(EngineState {
                        info: Mutex::new(info),
                        child: Mutex::new(Some(child)),
                    });
                }
                last_error = format!(
                    "the engine process started on port {port} but never answered /api/health"
                );
                let _ = child.kill();
                let _ = child.wait();
            }
            Err(err) => last_error = err,
        }
    }
    Err(last_error.into())
}

const KEYRING_SERVICE: &str = "whatsapp-forensic-studio";
const API_KEY_ACCOUNT: &str = "ai-api-key";

/// Read the external AI key from the operating-system credential store.
///
/// The key is never written to disk, logs or the command line; only the engine
/// child process receives it, through its environment.
fn stored_api_key() -> Option<String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, API_KEY_ACCOUNT).ok()?;
    match entry.get_password() {
        Ok(value) if !value.trim().is_empty() => Some(value),
        _ => None,
    }
}

fn session_token() -> String {
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn free_port() -> Result<u16, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

fn spawn_process(port: u16, token: &str) -> Result<Child, String> {
    let data_dir = data_dir()?;
    let mut command = if cfg!(debug_assertions) {
        // Development: run the engine from source with the developer's Python.
        let python = std::env::var("WFS_PYTHON").unwrap_or_else(|_| "python".to_string());
        let engine_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../forensic-engine");
        let mut command = Command::new(python);
        command
            .arg("-m")
            .arg("wfs_engine.cli")
            .arg("serve")
            .current_dir(&engine_dir)
            .env("PYTHONPATH", &engine_dir)
            .env("PYTHONUNBUFFERED", "1");
        command
    } else {
        // Packaged: the frozen sidecar sits beside the application executable.
        let exe = std::env::current_exe().map_err(|err| err.to_string())?;
        let dir = exe
            .parent()
            .ok_or_else(|| "cannot resolve the application directory".to_string())?;
        let sidecar = if cfg!(windows) {
            dir.join("wfs-engine.exe")
        } else {
            dir.join("wfs-engine")
        };
        if !sidecar.exists() {
            return Err(format!(
                "the packaged engine is missing at {} (run scripts/build_sidecar.sh before bundling)",
                sidecar.display()
            ));
        }
        let mut command = Command::new(sidecar);
        // The frozen entry point is the CLI, so the subcommand is required here
        // exactly as it is in development.
        command.arg("serve").current_dir(dir);
        command
    };

    // Engine output goes to a rotating log file so a failed start can be
    // diagnosed. The log holds startup messages and errors only - chat content
    // is never written there by the engine.
    let log_dir = data_dir.join("logs");
    std::fs::create_dir_all(&log_dir).map_err(|err| err.to_string())?;
    let log_path = log_dir.join("engine.log");
    if let Ok(meta) = std::fs::metadata(&log_path) {
        if meta.len() > 5 * 1024 * 1024 {
            let _ = std::fs::rename(&log_path, log_dir.join("engine.log.1"));
        }
    }
    let log = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|err| format!("cannot open {}: {err}", log_path.display()))?;
    let log_err = log.try_clone().map_err(|err| err.to_string())?;

    // Optional external-provider key: the UI stores it in the OS credential
    // store (never the database or a file), and the engine receives it through
    // the environment of its own process. A missing keyring or entry is normal
    // in development and on machines that never enabled an external provider.
    if let Some(key) = stored_api_key() {
        command.env("OPENAI_API_KEY", key);
    }

    command
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .env("WFS_DATA_DIR", &data_dir)
        .env("WFS_TOKEN", token)
        .env("WFS_LOG_DIR", log_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_err));

    command
        .spawn()
        .map_err(|err| format!("could not start the forensic engine: {err}"))
}

pub fn data_dir() -> Result<PathBuf, String> {
    if let Ok(value) = std::env::var("WFS_DATA_DIR") {
        return Ok(PathBuf::from(value));
    }
    let base = std::env::var("APPDATA")
        .map(PathBuf::from)
        .or_else(|_| std::env::var("XDG_DATA_HOME").map(PathBuf::from))
        .map_err(|_| "cannot resolve a user data directory".to_string())?;
    Ok(base.join("WhatsAppForensicStudio").join("data"))
}

/// Poll `/api/health` until the engine answers 200 or the deadline passes.
fn wait_until_ready(port: u16, token: &str, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if health_ok(port, token) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

/// Health probe. The engine authenticates every route, including `/api/health`,
/// so the probe presents the session token in the request header (never in the
/// URL, never on the command line).
fn health_ok(port: u16, token: &str) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(500)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1500)));
    let request = format!(
        "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut buffer = [0u8; 128];
    match stream.read(&mut buffer) {
        Ok(read) if read > 0 => {
            let head = String::from_utf8_lossy(&buffer[..read]);
            head.starts_with("HTTP/1.1 200") || head.starts_with("HTTP/1.0 200")
        }
        _ => false,
    }
}
