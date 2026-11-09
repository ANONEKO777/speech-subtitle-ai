//! The folders the app may write into and show: the ones the person picked in the native dialog,
//! plus the app's own screenshot and export folders. The list lives in a file under the app data
//! folder that only this process writes, so the backend can read it and the page cannot forge it.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

pub const LIST_FILE: &str = "output-folders.txt";
const APP_DIR: &str = "video-subtitle-translator";

pub fn user_data() -> PathBuf {
    if let Some(dir) = std::env::var_os("VST_USER_DATA").filter(|d| !d.is_empty()) {
        return PathBuf::from(dir);
    }
    let base = std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_default();
    base.join(APP_DIR)
}

fn real(path: &Path) -> Option<PathBuf> {
    path.canonicalize().ok()
}

fn is_network(path: &Path) -> bool {
    path.to_string_lossy().starts_with(r"\?\UNC\")
}

#[derive(Default)]
pub struct Folders {
    user_data: PathBuf,
    written: Mutex<HashSet<PathBuf>>,
}

impl Folders {
    pub fn new(user_data: PathBuf) -> Self {
        Self { user_data, written: Mutex::default() }
    }

    fn list(&self) -> PathBuf {
        self.user_data.join(LIST_FILE)
    }

    /// Remembers a folder the person picked, for the backend and for `allowed`.
    pub fn picked(&self, folder: &Path) -> Result<(), String> {
        if real(folder).is_none() {
            return Ok(());
        }
        fs::create_dir_all(&self.user_data).map_err(|e| e.to_string())?;
        let mut lines = fs::read_to_string(self.list()).unwrap_or_default();
        let line = folder.to_string_lossy().into_owned();
        if lines.lines().any(|l| l == line) {
            return Ok(());
        }
        lines.push_str(&line);
        lines.push('\n');
        fs::write(self.list(), lines).map_err(|e| e.to_string())
    }

    /// Remembers a file this process wrote.
    pub fn wrote(&self, file: &Path) {
        if let Some(file) = real(file) {
            self.written.lock().unwrap().insert(file);
        }
    }

    fn roots(&self) -> Vec<PathBuf> {
        let mut roots: Vec<PathBuf> = fs::read_to_string(self.list())
            .unwrap_or_default()
            .lines()
            .filter(|l| !l.is_empty())
            .map(PathBuf::from)
            .collect();
        roots.push(self.user_data.join("screenshots"));
        roots.push(self.user_data.join("exports"));
        if let Some(dir) = std::env::var_os("VST_EXPORT_DIR") {
            roots.push(PathBuf::from(dir));
        }
        roots.iter().filter_map(|r| real(r)).filter(|r| !is_network(r)).collect()
    }

    /// The resolved path when `path` is a file this process wrote, or lies in a folder the app may
    /// show. Callers act on the returned path, so a link swapped in afterwards changes nothing.
    pub fn allowed(&self, path: &Path) -> Option<PathBuf> {
        let path = real(path)?;
        let ok = !is_network(&path)
            && (self.written.lock().unwrap().contains(&path) || self.roots().iter().any(|r| path.starts_with(r)));
        ok.then_some(path)
    }

}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("vst-folders-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn shows_only_the_app_folders_and_picked_ones() {
        let data = scratch("data");
        let picked = scratch("picked");
        let other = scratch("other");
        fs::create_dir_all(data.join("screenshots")).unwrap();
        fs::write(data.join("screenshots").join("a.png"), b"x").unwrap();
        fs::write(picked.join("b.png"), b"x").unwrap();
        fs::write(other.join("c.png"), b"x").unwrap();
        let folders = Folders::new(data.clone());

        assert!(folders.allowed(&data.join("screenshots")).is_some());
        assert!(folders.allowed(&data.join("screenshots").join("a.png")).is_some());
        assert!(folders.allowed(&picked.join("b.png")).is_none());
        folders.picked(&picked).unwrap();
        assert!(folders.allowed(&picked.join("b.png")).is_some());
        assert!(folders.allowed(&other.join("c.png")).is_none());
        assert!(folders.allowed(Path::new(r"C:\Windows\System32")).is_none());
        assert!(folders.allowed(&data.join("screenshots").join("..").join("..")).is_none());
        assert!(folders.allowed(&data.join("screenshots").join("missing.png")).is_none());
        folders.wrote(&other.join("c.png"));
        assert!(folders.allowed(&other.join("c.png")).is_some());
    }

    #[test]
    fn the_list_survives_a_restart_and_has_no_duplicates() {
        let data = scratch("list");
        let picked = scratch("again");
        Folders::new(data.clone()).picked(&picked).unwrap();
        Folders::new(data.clone()).picked(&picked).unwrap();
        assert_eq!(fs::read_to_string(data.join(LIST_FILE)).unwrap().lines().count(), 1);
        assert!(Folders::new(data).allowed(&picked).is_some());
    }
}
