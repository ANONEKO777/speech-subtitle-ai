//! Everything the shell does differently per operating system, as plain functions of an `Os` value,
//! so each branch is tested on whatever machine runs `cargo test`.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Os {
    Windows,
    MacOs,
    Other,
}

impl Os {
    pub const CURRENT: Os = if cfg!(windows) {
        Os::Windows
    } else if cfg!(target_os = "macos") {
        Os::MacOs
    } else {
        Os::Other
    };
}

/// The packaged backend inside the resource folder: PyInstaller's `vst-backend` folder contents.
pub fn packaged_backend(os: Os) -> &'static str {
    if os == Os::Windows { "vst-backend.exe" } else { "vst-backend" }
}

/// The interpreter of the repository's `.venv`, relative to the repository root.
pub fn venv_python(os: Os) -> PathBuf {
    if os == Os::Windows {
        PathBuf::from(".venv").join("Scripts").join("python.exe")
    } else {
        PathBuf::from(".venv").join("bin").join("python")
    }
}

/// The folder holding the app's data, below `APP_DIR`. It must equal `default_user_data` in
/// `backend/manager/storage.py`: a Mac keeps it in `~/Library/Application Support`, Windows in
/// `%LOCALAPPDATA%`, and anything else in `~/.local/share` as the backend does.
pub fn data_base(os: Os, local_app_data: Option<OsString>, home: Option<OsString>) -> PathBuf {
    let non_empty = |v: Option<OsString>| v.filter(|v| !v.is_empty()).map(PathBuf::from);
    match os {
        Os::Windows => non_empty(local_app_data).unwrap_or_default(),
        Os::MacOs => non_empty(home).unwrap_or_default().join("Library").join("Application Support"),
        Os::Other => non_empty(local_app_data)
            .unwrap_or_else(|| non_empty(home).unwrap_or_default().join(".local").join("share")),
    }
}

/// A program and its arguments, built for a test to read before anything starts.
#[derive(Debug, PartialEq, Eq)]
pub struct Launch {
    pub program: &'static str,
    pub args: Vec<OsString>,
}

/// Shows a file selected in the file manager, or opens a folder.
pub fn reveal(os: Os, path: &Path, is_file: bool) -> Launch {
    match (os, is_file) {
        (Os::Windows, true) => Launch { program: "explorer", args: vec![format!("/select,{}", path.display()).into()] },
        (Os::Windows, false) => Launch { program: "explorer", args: vec![path.into()] },
        (Os::MacOs, true) => Launch { program: "open", args: vec!["-R".into(), path.into()] },
        (Os::MacOs, false) => Launch { program: "open", args: vec![path.into()] },
        (Os::Other, true) => Launch { program: "xdg-open", args: vec![path.parent().unwrap_or(path).into()] },
        (Os::Other, false) => Launch { program: "xdg-open", args: vec![path.into()] },
    }
}

/// Opens an address in the default browser.
pub fn browse(os: Os, url: &str) -> Launch {
    let program = match os {
        Os::Windows => "explorer",
        Os::MacOs => "open",
        Os::Other => "xdg-open",
    };
    Launch { program, args: vec![url.into()] }
}

impl Launch {
    pub fn spawn(self) -> Result<(), String> {
        std::process::Command::new(self.program).args(self.args).spawn().map(|_| ()).map_err(|e| e.to_string())
    }
}

/// Only the Windows installer has update artifacts and a `latest.json` entry. A Mac is updated by
/// installing a newer build by hand, so the check says so instead of reporting a broken source.
pub fn updates_supported(os: Os) -> bool {
    os == Os::Windows
}

#[cfg(test)]
mod tests {
    use super::*;

    fn os_str(s: &str) -> Option<OsString> {
        Some(OsString::from(s))
    }

    #[test]
    fn the_packaged_backend_has_an_exe_suffix_only_on_windows() {
        assert_eq!(packaged_backend(Os::Windows), "vst-backend.exe");
        assert_eq!(packaged_backend(Os::MacOs), "vst-backend");
        assert_eq!(packaged_backend(Os::Other), "vst-backend");
    }

    #[test]
    fn the_venv_interpreter_is_in_scripts_on_windows_and_bin_elsewhere() {
        assert_eq!(venv_python(Os::Windows), Path::new(".venv").join("Scripts").join("python.exe"));
        assert_eq!(venv_python(Os::MacOs), Path::new(".venv").join("bin").join("python"));
    }

    #[test]
    fn a_mac_keeps_its_data_where_the_backend_does() {
        let base = data_base(Os::MacOs, os_str(r"C:\ignored"), os_str("/Users/me"));
        assert_eq!(base, Path::new("/Users/me").join("Library").join("Application Support"));
    }

    #[test]
    fn windows_keeps_its_data_in_local_app_data_and_ignores_home() {
        assert_eq!(data_base(Os::Windows, os_str(r"C:\Users\me\AppData\Local"), os_str("/x")), Path::new(r"C:\Users\me\AppData\Local"));
    }

    #[test]
    fn a_missing_or_empty_base_gives_an_empty_one_as_before_on_windows() {
        assert_eq!(data_base(Os::Windows, None, os_str("/x")), PathBuf::new());
        assert_eq!(data_base(Os::Windows, os_str(""), None), PathBuf::new());
    }

    #[test]
    fn other_systems_follow_the_backend_default() {
        assert_eq!(data_base(Os::Other, os_str("/data"), os_str("/home/me")), Path::new("/data"));
        assert_eq!(data_base(Os::Other, None, os_str("/home/me")), Path::new("/home/me").join(".local").join("share"));
    }

    #[test]
    fn explorer_selects_a_file_and_opens_a_folder() {
        let file = reveal(Os::Windows, Path::new(r"C:\a\b.png"), true);
        assert_eq!(file, Launch { program: "explorer", args: vec![OsString::from(r"/select,C:\a\b.png")] });
        let dir = reveal(Os::Windows, Path::new(r"C:\a"), false);
        assert_eq!(dir, Launch { program: "explorer", args: vec![OsString::from(r"C:\a")] });
    }

    #[test]
    fn a_mac_reveals_a_file_with_open_dash_r_and_opens_a_folder_plainly() {
        let file = reveal(Os::MacOs, Path::new("/Users/me/out.srt"), true);
        assert_eq!(file, Launch { program: "open", args: vec!["-R".into(), "/Users/me/out.srt".into()] });
        let dir = reveal(Os::MacOs, Path::new("/Users/me/out"), false);
        assert_eq!(dir, Launch { program: "open", args: vec!["/Users/me/out".into()] });
    }

    #[test]
    fn an_address_opens_with_the_launcher_of_each_system() {
        for (os, program) in [(Os::Windows, "explorer"), (Os::MacOs, "open"), (Os::Other, "xdg-open")] {
            assert_eq!(browse(os, "https://spdx.org/licenses/MIT.html"), Launch { program, args: vec!["https://spdx.org/licenses/MIT.html".into()] });
        }
    }

    #[test]
    fn only_windows_checks_for_updates() {
        assert!(updates_supported(Os::Windows));
        assert!(!updates_supported(Os::MacOs));
    }
}
