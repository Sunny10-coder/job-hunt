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
use tauri::{AppHandle, Manager};

#[derive(Debug, Clone, Serialize)]
pub struct EngineInfo {
    pub base_url: String,
    pub token: String,
    pub port: u16,
}

pub struct EngineState {
    pub info: EngineInfo,
    child: Mutex<Option<Child>>,
}

impl EngineState {
    pub fn shutdown(&self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }

    pub fn restart(&self) -> Result<(), String> {
        self.shutdown();
        let child = spawn_process(&self.info.port, &self.info.token)?;
        *self.child.lock().map_err(|_| "engine state poisoned".to_string())? = Some(child);
        Ok(())
    }
}

/// Create the data/log directories, start the engine and wait until it answers.
pub fn bootstrap(app: &AppHandle) -> Result<EngineState, Box<dyn std::error::Error>> {
    let data_root = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("cannot resolve the application data directory: {err}"))?;
    let cases_root = data_root.join("cases");
    let log_root = app
        .path()
        .app_log_dir()
        .unwrap_or_else(|_| data_root.join("logs"));
    for dir in [&cases_root, &log_root] {
        std::fs::create_dir_all(dir)?;
    }

    let token = session_token();
    let mut last_error = String::from("the forensic engine did not start");

    for _ in 0..3 {
        let port = free_port()?;
        match spawn_process(&port, &token) {
            Ok(mut child) => {
                if wait_until_ready(port, Duration::from_secs(45)) {
                    let info = EngineInfo {
                        base_url: format!("http://127.0.0.1:{port}"),
                        token: token.clone(),
                        port,
                    };
                    return Ok(EngineState {
                        info,
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
        command.current_dir(dir);
        command
    };

    command
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .env("WFS_DATA_DIR", &data_dir)
        .env("WFS_TOKEN", token)
        .env("WFS_LOG_DIR", data_dir.join("logs"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    command
        .spawn()
        .map_err(|err| format!("could not start the forensic engine: {err}"))
}

fn data_dir() -> Result<PathBuf, String> {
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
fn wait_until_ready(port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if health_ok(port) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

fn health_ok(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(500)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1500)));
    let request = "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
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
