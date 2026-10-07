//! Tauri shell: spawns the bundled FastAPI backend (a PyInstaller *onedir* app under
//! `resources/backend/`) on a free localhost port, injects that port into the webview as
//! `window.__BACKEND_URL__` (api.ts reads it), and serves the built React UI. The backend
//! is terminated when the app exits.

use std::net::TcpListener;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

/// Holds the backend child so we can kill it when the app exits (no orphans).
struct BackendChild(Mutex<Option<Child>>);

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
        // Single-instance must be registered FIRST: a second launch focuses the existing
        // window instead of spawning a second backend.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
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

            // The speech helper (WhisperKit/SpeakerKit/Apple speech) is bundled the same way.
            let speech_bin = app
                .path()
                .resolve("resources/speech-engine", tauri::path::BaseDirectory::Resource)
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_default();

            // The onedir backend lives at Contents/Resources/resources/backend/backend, with
            // its `_internal/` libs alongside (found relative to the exe — no re-extraction).
            let backend = app
                .path()
                .resolve("resources/backend/backend", tauri::path::BaseDirectory::Resource)
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_default();

            // Spawn the backend directly, pointed at the per-user data dir for its DB + caches.
            // Spawn failures are logged (not a panic) — the webview's startup gate then surfaces
            // "backend unreachable" with a retry. The backend writes its own rotating log under
            // the data dir, so we don't need to pipe its output here.
            match Command::new(&backend)
                .env("APP_DATA_DIR", &data_dir)
                .env("SYSTEM_AUDIO_SIDECAR", &capture_bin)
                .env("SPEECH_ENGINE_HELPER", &speech_bin)
                .args(["--host", "127.0.0.1", "--port", &port.to_string()])
                .spawn()
            {
                Ok(child) => {
                    app.manage(BackendChild(Mutex::new(Some(child))));
                }
                Err(e) => eprintln!("[backend] failed to start ({backend}): {e}"),
            }

            // The window first loads the bundled UI (tauri://), which shows the
            // "Starting backend…" splash. We then navigate it to the backend over http
            // so the app runs *same-origin* — a tauri:// (secure) page can't fetch
            // http://127.0.0.1 (mixed content), but an http:// page served by the
            // backend can. `__BACKEND_URL__` keeps api.ts working in both phases.
            let init = format!("window.__BACKEND_URL__ = 'http://127.0.0.1:{port}';");
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("Sirina")
                .inner_size(1200.0, 800.0)
                .min_inner_size(800.0, 600.0)
                .initialization_script(&init)
                .build()?;

            // Once the backend accepts connections, navigate the window to it.
            let nav_window = window.clone();
            std::thread::spawn(move || {
                let addr = std::net::SocketAddr::from(([127, 0, 0, 1], port));
                // Bounded wait (~60s). If the backend never comes up we stop trying and
                // leave the webview on its splash, which times out into an error + retry.
                for _ in 0..120 {
                    if std::net::TcpStream::connect_timeout(
                        &addr,
                        std::time::Duration::from_millis(500),
                    )
                    .is_ok()
                    {
                        if let Ok(url) = format!("http://127.0.0.1:{port}/").parse::<tauri::Url>() {
                            let _ = nav_window.navigate(url);
                        }
                        return;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(500));
                }
                eprintln!("[backend] not reachable after ~60s; staying on the splash (offers retry)");
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
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
