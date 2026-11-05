mod sidecar;

use sidecar::{Backend, BackendState};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use tauri::{AppHandle, Manager, RunEvent, WindowEvent};
use tauri_plugin_dialog::DialogExt;

#[tauri::command]
fn backend_info(state: tauri::State<'_, BackendState>) -> Option<Backend> {
    state.ready()
}

const MEDIA: [&str; 9] = ["mp4", "mkv", "mov", "webm", "m4v", "avi", "mp3", "wav", "m4a"];

/// Paths the user chose in the native dialog, which this process opened itself.
#[derive(Default)]
struct Picked(Mutex<HashSet<PathBuf>>);

fn allow(app: &AppHandle, path: &Path) -> Result<(), String> {
    app.asset_protocol_scope().allow_file(path).map_err(|e| e.to_string())
}

/// Opens the native file dialog and lets the asset protocol serve the one file picked. The dialog
/// runs here, not in the page, so a page script cannot forge a pick.
#[tauri::command]
async fn pick_video(app: AppHandle, picked: tauri::State<'_, Picked>) -> Result<Option<String>, String> {
    let Some(file) = app
        .dialog()
        .file()
        .add_filter("影片與音訊", &MEDIA)
        .blocking_pick_file()
    else {
        return Ok(None);
    };
    let path = file.into_path().map_err(|e| e.to_string())?;
    allow(&app, &path)?;
    picked.0.lock().unwrap().insert(path.clone());
    Ok(Some(path.to_string_lossy().into_owned()))
}

/// Lets the asset protocol serve a path typed into the import box. The path must be a file the
/// user picked, or an existing regular file whose real path (symlinks followed) has a media
/// extension, so a page script cannot widen the scope to documents, keys or other data.
#[tauri::command]
fn allow_video(app: AppHandle, picked: tauri::State<'_, Picked>, path: String) -> Result<(), String> {
    let path = PathBuf::from(path);
    if !picked.0.lock().unwrap().contains(&path) {
        let real = path.canonicalize().map_err(|e| format!("cannot read {}: {e}", path.display()))?;
        let media = real
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| MEDIA.iter().any(|m| m.eq_ignore_ascii_case(e)));
        if !real.is_file() || !media {
            return Err(format!("{} is not a video or audio file", path.display()));
        }
    }
    allow(&app, &path)
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState::default())
        .manage(Picked::default())
        .invoke_handler(tauri::generate_handler![backend_info, pick_video, allow_video])
        .setup(|app| {
            sidecar::start(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                window.state::<BackendState>().stop();
            }
        })
        .build(tauri::generate_context!())
        .expect("failed to build the app");
    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            handle.state::<BackendState>().stop();
        }
    });
}
