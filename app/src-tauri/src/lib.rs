mod folders;
mod links;
mod sidecar;
mod updater;

use folders::Folders;

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

/// Opens the native file dialog for several files and returns their paths. The backend reads
/// them itself when they are queued, so nothing is added to the asset scope here.
#[tauri::command]
async fn pick_videos(app: AppHandle) -> Result<Vec<String>, String> {
    let files = app
        .dialog()
        .file()
        .add_filter("影片與音訊", &MEDIA)
        .blocking_pick_files()
        .unwrap_or_default();
    files
        .into_iter()
        .map(|f| f.into_path().map(|p| p.to_string_lossy().into_owned()).map_err(|e| e.to_string()))
        .collect()
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

/// A file name with no folders in it, so the dialog's suggestion and the test folder below stay in
/// one directory.
fn plain_name(name: &str) -> Result<String, String> {
    Path::new(name)
        .file_name()
        .and_then(|n| n.to_str())
        .filter(|n| !n.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| format!("{name:?} is not a file name"))
}

/// Opens the native save dialog and writes `content` to the file chosen, as UTF-8. The dialog runs
/// here, not in the page, so a page script cannot choose a path. Returns the path written, or None
/// when the person cancelled. When `VST_EXPORT_DIR` is set the file goes there under `name` with
/// no dialog, which is how the automated drivers, which cannot click a native dialog, collect exports.
#[tauri::command]
async fn save_export(app: AppHandle, folders: tauri::State<'_, Folders>, name: String, content: String) -> Result<Option<String>, String> {
    let name = plain_name(&name)?;
    let path = if let Some(dir) = std::env::var_os("VST_EXPORT_DIR") {
        PathBuf::from(dir).join(&name)
    } else {
        let ext = Path::new(&name).extension().and_then(|e| e.to_str()).unwrap_or("txt").to_owned();
        let Some(file) = app
            .dialog()
            .file()
            .set_file_name(&name)
            .add_filter(ext.to_uppercase(), &[ext.as_str()])
            .blocking_save_file()
        else {
            return Ok(None);
        };
        file.into_path().map_err(|e| e.to_string())?
    };
    std::fs::write(&path, content).map_err(|e| format!("cannot write {}: {e}", path.display()))?;
    folders.wrote(&path);
    Ok(Some(path.to_string_lossy().into_owned()))
}

/// Opens the native folder dialog and returns the folder picked, or None when the person cancelled.
/// The dialog runs here, not in the page, so a page script cannot forge a pick.
#[tauri::command]
async fn pick_folder(app: AppHandle, folders: tauri::State<'_, Folders>) -> Result<Option<String>, String> {
    let Some(folder) = app.dialog().file().blocking_pick_folder() else {
        return Ok(None);
    };
    let path = folder.into_path().map_err(|e| e.to_string())?;
    folders.picked(&path)?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

/// Shows a file in Explorer (selected), or opens a folder. The path must be a file this process
/// wrote, or lie in the app's screenshot and export folders or a folder the person picked, so a
/// page script cannot open or reveal anything else.
/// With `VST_OPEN_FOLDER_LOG` set (the e2e drivers do), the resolved path is appended to that file
/// and no Explorer window opens.
#[tauri::command]
fn open_folder(folders: tauri::State<'_, Folders>, path: String) -> Result<(), String> {
    let path = PathBuf::from(path);
    let Some(path) = folders.allowed(&path) else {
        return Err(format!("{} is not in a folder this app writes to", path.display()));
    };
    let shown = PathBuf::from(path.to_string_lossy().trim_start_matches(r"\\?\"));
    if let Some(log) = std::env::var_os("VST_OPEN_FOLDER_LOG") {
        use std::io::Write;
        let mut file = std::fs::OpenOptions::new().create(true).append(true).open(log).map_err(|e| e.to_string())?;
        return writeln!(file, "{}", shown.display()).map_err(|e| e.to_string());
    }
    let mut explorer = std::process::Command::new("explorer");
    if path.is_file() {
        explorer.arg(format!("/select,{}", shown.display()));
    } else if path.is_dir() {
        explorer.arg(&shown);
    } else {
        return Err(format!("{} does not exist", path.display()));
    }
    explorer.spawn().map(|_| ()).map_err(|e| e.to_string())
}

/// Opens an https address in the default browser. Only a host the license pages already link to
/// (see `links`), so the page cannot start a program or send the person to a site of its choice.
/// With `VST_OPEN_URL_LOG` set (the e2e drivers do), the address is appended to that file and no
/// browser starts.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    links::open(&url, std::env::var_os("VST_OPEN_URL_LOG").map(PathBuf::from).as_deref())
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(BackendState::default())
        .manage(Picked::default())
        .manage(updater::Pending::default())
        .manage(Folders::new(folders::user_data()))
        .invoke_handler(tauri::generate_handler![backend_info, pick_video, allow_video, save_export, pick_folder, open_folder, open_url, pick_videos, updater::update_check, updater::update_download, updater::update_install])
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
