//! Tauri shell: spawns the bundled FastAPI backend (a PyInstaller sidecar) on a
//! free localhost port, injects that port into the webview as `window.__BACKEND_URL__`
//! (api.ts reads it), and serves the built React UI. The sidecar is terminated when
//! the app exits.
//!
//! NOTE: scaffolding — build/iterate on-device with the real Tauri 2 toolchain
//! (`cargo tauri dev` / `cargo tauri build`). It has not been compiled here.

use std::net::TcpListener;

use std::sync::Mutex;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend sidecar child so we can kill it when the app exits (no orphans).
struct BackendChild(Mutex<Option<CommandChild>>);

/// Ask the OS for an unused localhost port.
fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .expect("could not find a free port")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let port = free_port();
            let data_dir = app
                .path()
                .app_data_dir()
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_default();

            // The native system-audio capture helper is bundled as a resource; tell the
            // backend where it is so native capture is available in the packaged app.
            let capture_bin = app
                .path()
                .resolve("resources/system-audio-capture", tauri::path::BaseDirectory::Resource)
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_default();

            // Start the backend, pointed at the per-user data dir for its DB + caches.
            let sidecar = app
                .shell()
                .sidecar("backend")
                .expect("backend sidecar is not bundled (see scripts/build-macos-app.sh)")
                .env("APP_DATA_DIR", &data_dir)
                .env("SYSTEM_AUDIO_SIDECAR", &capture_bin)
                .args(["--host", "127.0.0.1", "--port", &port.to_string()]);
            let (mut rx, child) = sidecar.spawn().expect("failed to start the backend sidecar");
            app.manage(BackendChild(Mutex::new(Some(child))));

            // Surface backend logs to the Tauri process output for debugging.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                            println!("[backend] {}", String::from_utf8_lossy(&line));
                        }
                        _ => {}
                    }
                }
            });

            // The window first loads the bundled UI (tauri://), which shows the
            // "Starting backend…" splash. We then navigate it to the backend over http
            // so the app runs *same-origin* — a tauri:// (secure) page can't fetch
            // http://127.0.0.1 (mixed content), but an http:// page served by the
            // backend can. `__BACKEND_URL__` keeps api.ts working in both phases.
            let init = format!("window.__BACKEND_URL__ = 'http://127.0.0.1:{port}';");
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("Meeting Recorder")
                .inner_size(1200.0, 800.0)
                .min_inner_size(800.0, 600.0)
                .initialization_script(&init)
                .build()?;

            // Once the backend accepts connections, navigate the window to it.
            let nav_window = window.clone();
            std::thread::spawn(move || {
                let addr = std::net::SocketAddr::from(([127, 0, 0, 1], port));
                loop {
                    if std::net::TcpStream::connect_timeout(
                        &addr,
                        std::time::Duration::from_millis(500),
                    )
                    .is_ok()
                    {
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(500));
                }
                if let Ok(url) = format!("http://127.0.0.1:{port}/").parse::<tauri::Url>() {
                    let _ = nav_window.navigate(url);
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Tauri application")
        .run(|app_handle, event| {
            // Kill the backend sidecar on exit so it doesn't linger as an orphan.
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<BackendChild>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
