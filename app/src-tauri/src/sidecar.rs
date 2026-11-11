//! Starts the Python backend, reads its `READY port=<n> token=<t>` line, and kills it, with every
//! process it started, when the window closes or the app exits.
//!
//! An installed app runs the packaged backend (`backend/vst-backend.exe` in the resource folder)
//! with the bundled FFmpeg. `tauri dev` runs it from the repository's virtual environment.

use serde::Serialize;
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager};

#[derive(Clone, Serialize)]
pub struct Backend {
    pub port: u16,
    pub token: String,
}

#[derive(Default)]
struct Inner {
    ready: Option<Backend>,
    /// Set once the window closes, so a backend that ends then is not started again.
    stopped: bool,
    /// How many times a backend that died after it was ready has been started again.
    restarts: u32,
    child: Option<Child>,
    #[cfg(windows)]
    job: Option<job::Job>,
}

#[derive(Default)]
pub struct BackendState(Mutex<Inner>);

impl BackendState {
    pub fn ready(&self) -> Option<Backend> {
        self.0.lock().unwrap().ready.clone()
    }

    /// Ends the backend and all of its children. Safe to call more than once.
    pub fn stop(&self) {
        let mut inner = self.0.lock().unwrap();
        inner.stopped = true;
        #[cfg(windows)]
        let job = inner.job.take();
        if let Some(mut child) = inner.child.take() {
            #[cfg(windows)]
            if job.is_none() {
                kill_tree(child.id());
            }
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

/// The packaged backend and its FFmpeg, in the folders the installer puts beside the app.
struct Packaged {
    exe: PathBuf,
    ffmpeg: PathBuf,
}

/// An exe inside this crate's own `target` folder is a developer build. `tauri build` leaves a copy
/// of the packaged backend beside it that goes stale, so it must not win over the `.venv`.
fn in_build_tree(exe: &Path) -> bool {
    let target = Path::new(env!("CARGO_MANIFEST_DIR")).join("target");
    let canon = |p: &Path| p.canonicalize().unwrap_or_else(|_| p.to_path_buf());
    canon(exe).starts_with(canon(&target))
}

fn packaged(app: &AppHandle) -> Option<Packaged> {
    if std::env::current_exe().is_ok_and(|exe| in_build_tree(&exe)) {
        return None;
    }
    let resources = app.path().resource_dir().ok()?;
    let exe = resources.join("backend").join("vst-backend.exe");
    exe.is_file().then(|| Packaged { exe, ffmpeg: resources.join("ffmpeg") })
}

/// `VST_BACKEND_PYTHON` wins (the drivers use it), then the packaged executable, then the
/// repository's own virtual environment for `tauri dev`.
fn command(app: &AppHandle) -> Command {
    let mut cmd = match (std::env::var_os("VST_BACKEND_PYTHON"), packaged(app)) {
        (None, Some(p)) => {
            let mut cmd = Command::new(&p.exe);
            if let Some(dir) = p.exe.parent() {
                cmd.current_dir(dir);
            }
            if std::env::var_os("VST_FFMPEG_DIR").is_none() {
                cmd.env("VST_FFMPEG_DIR", &p.ffmpeg);
            }
            cmd
        }
        (python, _) => {
            let root = repo_root();
            let python = python
                .map(PathBuf::from)
                .unwrap_or_else(|| root.join(".venv").join("Scripts").join("python.exe"));
            let mut cmd = Command::new(python);
            cmd.args(["-m", "backend.main"]).current_dir(root);
            cmd
        }
    };
    if let Some(dir) = std::env::var_os("VST_PROJECTS") {
        cmd.arg("--projects").arg(dir);
    }
    cmd
}

fn parse_ready(line: &str) -> Option<Backend> {
    let rest = line.strip_prefix("READY ")?;
    let (mut port, mut token) = (None, None);
    for part in rest.split_whitespace() {
        match part.split_once('=') {
            Some(("port", v)) => port = v.parse().ok(),
            Some(("token", v)) => token = Some(v.to_string()),
            _ => {}
        }
    }
    Some(Backend { port: port?, token: token? })
}

/// Fallback when the job object could not be set up: ends the backend and the whisper and llama
/// processes below it through their parent links.
#[cfg(windows)]
fn kill_tree(pid: u32) {
    use std::os::windows::process::CommandExt;
    let _ = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .creation_flags(0x0800_0000)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

/// How much of the backend's stderr is kept to explain a failed start.
const STDERR_KEEP: usize = 64 * 1024;

/// A backend that dies after it was ready is started again this many times. The queue is on disk,
/// so a restart resumes the running item, and the page follows the new port and token.
const MAX_RESTARTS: u32 = 5;

/// A backend that ran this long since it was ready counts as healthy: its death starts the restart
/// count again, so five crashes over days of uptime do not leave it dead for good.
const HEALTHY_FOR: std::time::Duration = std::time::Duration::from_secs(10 * 60);

pub fn start(app: AppHandle) {
    if app.state::<BackendState>().0.lock().unwrap().stopped {
        return;
    }
    let mut cmd = command(&app);
    cmd.stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    let mut child = match cmd.spawn() {
        Ok(child) => child,
        Err(e) => {
            let _ = app.emit("backend-failed", format!("無法啟動後端：{e}"));
            return;
        }
    };
    let stdout = child.stdout.take().expect("piped");
    let stderr = child.stderr.take().expect("piped");
    {
        let state = app.state::<BackendState>();
        let mut inner = state.0.lock().unwrap();
        if inner.stopped {
            let _ = child.kill();
            let _ = child.wait();
            return;
        }
        #[cfg(windows)]
        {
            inner.job = job::Job::adopt(&child);
            if inner.job.is_none() {
                eprintln!("cannot put the backend in a job object; stop() will kill its process tree instead");
            }
        }
        inner.child = Some(child);
    }
    let tail = Arc::new(Mutex::new(Vec::<u8>::new()));
    let tail_writer = Arc::clone(&tail);
    std::thread::spawn(move || {
        let mut stderr = stderr;
        let mut chunk = [0u8; 8192];
        while let Ok(n @ 1..) = stderr.read(&mut chunk) {
            let mut kept = tail_writer.lock().unwrap();
            kept.extend_from_slice(&chunk[..n]);
            if kept.len() > STDERR_KEEP {
                let excess = kept.len() - STDERR_KEEP;
                kept.drain(..excess);
            }
        }
    });
    std::thread::spawn(move || {
        let mut out = BufReader::new(stdout);
        let mut raw = Vec::new();
        let mut ready_at = None;
        loop {
            raw.clear();
            if !matches!(out.read_until(b'\n', &mut raw), Ok(1..)) {
                break;
            }
            if let Some(backend) = parse_ready(String::from_utf8_lossy(&raw).trim_end()) {
                ready_at.get_or_insert_with(std::time::Instant::now);
                app.state::<BackendState>().0.lock().unwrap().ready = Some(backend.clone());
                let _ = app.emit("backend-ready", backend);
            }
        }
        if app.state::<BackendState>().ready().is_none() {
            std::thread::sleep(std::time::Duration::from_millis(200));
            let text = String::from_utf8_lossy(&tail.lock().unwrap()).into_owned();
            let _ = app.emit("backend-failed", format!("後端在就緒前就結束了。\n{text}"));
            return;
        }
        let again = {
            let state = app.state::<BackendState>();
            let mut inner = state.0.lock().unwrap();
            if ready_at.is_some_and(|t| t.elapsed() >= HEALTHY_FOR) {
                inner.restarts = 0;
            }
            if inner.stopped || inner.restarts >= MAX_RESTARTS {
                false
            } else {
                inner.restarts += 1;
                inner.ready = None;
                true
            }
        };
        if again {
            std::thread::sleep(std::time::Duration::from_millis(500));
            start(app);
        } else if !app.state::<BackendState>().0.lock().unwrap().stopped {
            let _ = app.emit("backend-failed", "後端已停止，重新啟動多次仍失敗。請關閉並重新開啟應用程式。".to_string());
        }
    });
}

#[cfg(windows)]
mod job {
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    /// A job object that kills every process in it when its handle closes, which also happens
    /// when the app is killed, so a hard-killed app leaves no backend behind.
    pub struct Job(HANDLE);

    // SAFETY: a job handle is a kernel object id that any thread may use or close.
    unsafe impl Send for Job {}

    impl Job {
        pub fn adopt(child: &Child) -> Option<Job> {
            // SAFETY: plain Win32 calls with a zeroed, correctly sized info struct and a live
            // process handle owned by `child`.
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return None;
                }
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                let set = SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    (&info as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
                if set == 0 || AssignProcessToJobObject(handle, child.as_raw_handle() as HANDLE) == 0 {
                    CloseHandle(handle);
                    return None;
                }
                Some(Job(handle))
            }
        }
    }

    impl Drop for Job {
        fn drop(&mut self) {
            // SAFETY: the handle was created in `adopt` and is closed once.
            unsafe { CloseHandle(self.0) };
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_binary_built_in_this_crate_is_a_developer_build() {
        assert!(in_build_tree(&std::env::current_exe().unwrap()));
    }

    #[test]
    fn an_installed_copy_elsewhere_is_not() {
        assert!(!in_build_tree(&std::env::temp_dir().join("Video Subtitle Translator").join("app.exe")));
    }
}
