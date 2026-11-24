//! The Unix counterpart of the Windows job object in `sidecar`. The backend leads a process group of
//! its own, and every program it starts (llama-server, whisper-cli, crispasr, ffmpeg) stays in that
//! group, so one signal to the group reaches all of them.
//!
//! A Mac has nothing like kill-on-job-close, so a shell that is killed hard cannot stop the group.
//! The backend covers that case itself: it is told the shell's pid in `VST_PARENT_PID` and ends
//! when that process is gone (`backend/core/parent_watch.py`).

use std::os::unix::process::CommandExt;
use std::process::{Child, Command};
use std::time::{Duration, Instant};

/// Names the shell's pid for the backend's parent watch.
pub const PARENT_ENV: &str = "VST_PARENT_PID";

/// How long the group gets to end after SIGTERM before it is killed.
const TERM_GRACE: Duration = Duration::from_secs(2);

/// Makes the command start as the leader of a new process group and tells it who its parent is.
pub fn lead_own_group(cmd: &mut Command) {
    cmd.process_group(0);
    cmd.env(PARENT_ENV, std::process::id().to_string());
}

/// The group a leader with this pid owns, or None for a pid that would address every process of the
/// caller's group (0) or of the system (1, or one too large to be a pid).
fn group_of(pid: u32) -> Option<libc::pid_t> {
    libc::pid_t::try_from(pid).ok().filter(|p| *p > 1)
}

fn signal(group: libc::pid_t, sig: libc::c_int) {
    // SAFETY: `killpg` takes two integers. A group that is already gone makes it fail with ESRCH,
    // which is the outcome wanted, so the result is not read.
    unsafe { libc::killpg(group, sig) };
}

/// Ends the child and everything in its group: SIGTERM so each program can clean up, then SIGKILL
/// once the child has ended or `TERM_GRACE` has passed, which also takes any program that ignored
/// SIGTERM or outlived the leader. Safe to call after the child has already ended.
pub fn end(child: &mut Child) {
    let Some(group) = group_of(child.id()) else {
        return;
    };
    signal(group, libc::SIGTERM);
    let deadline = Instant::now() + TERM_GRACE;
    while Instant::now() < deadline && !matches!(child.try_wait(), Ok(Some(_))) {
        std::thread::sleep(Duration::from_millis(25));
    }
    signal(group, libc::SIGKILL);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use std::process::Stdio;

    fn group_exists(group: libc::pid_t) -> bool {
        // SAFETY: signal 0 only checks that the group can be signalled.
        unsafe { libc::killpg(group, 0) == 0 }
    }

    fn gone_within(group: libc::pid_t, wait: Duration) -> bool {
        let deadline = Instant::now() + wait;
        while group_exists(group) {
            if Instant::now() >= deadline {
                return false;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        true
    }

    fn shell(script: &str) -> Command {
        let mut cmd = Command::new("sh");
        cmd.args(["-c", script]).stdout(Stdio::piped()).stderr(Stdio::null());
        cmd
    }

    #[test]
    fn pids_that_would_address_more_than_the_backend_are_refused() {
        assert_eq!(group_of(0), None);
        assert_eq!(group_of(1), None);
        assert_eq!(group_of(u32::MAX), None);
        assert_eq!(group_of(4242), Some(4242));
    }

    #[test]
    fn the_command_leads_its_own_group_and_is_told_the_shell_pid() {
        let mut cmd = shell("echo $VST_PARENT_PID; sleep 5");
        lead_own_group(&mut cmd);
        let mut child = cmd.spawn().unwrap();
        let mut line = [0u8; 32];
        let n = child.stdout.take().unwrap().read(&mut line).unwrap();
        // SAFETY: plain query of a live child's group.
        let group = unsafe { libc::getpgid(child.id() as libc::pid_t) };
        end(&mut child);
        let _ = child.wait();
        assert_eq!(group, child.id() as libc::pid_t);
        assert_ne!(group, unsafe { libc::getpgrp() });
        assert_eq!(String::from_utf8_lossy(&line[..n]).trim(), std::process::id().to_string());
    }

    #[test]
    fn ending_the_child_ends_the_programs_it_started() {
        let mut cmd = shell("sleep 60 & sleep 60 & echo up; wait");
        lead_own_group(&mut cmd);
        let mut child = cmd.spawn().unwrap();
        let mut up = [0u8; 8];
        child.stdout.take().unwrap().read_exact(&mut up[..3]).unwrap();
        let group = group_of(child.id()).unwrap();
        assert!(group_exists(group));
        end(&mut child);
        let _ = child.wait();
        assert!(gone_within(group, Duration::from_secs(3)), "the group still has processes");
    }

    #[test]
    fn a_program_that_ignores_sigterm_is_killed_after_the_grace_time() {
        let mut cmd = shell("trap '' TERM; echo up; while :; do sleep 1; done");
        lead_own_group(&mut cmd);
        let mut child = cmd.spawn().unwrap();
        let mut up = [0u8; 8];
        child.stdout.take().unwrap().read_exact(&mut up[..3]).unwrap();
        let group = group_of(child.id()).unwrap();
        let start = Instant::now();
        end(&mut child);
        let _ = child.wait();
        assert!(start.elapsed() >= TERM_GRACE);
        assert!(gone_within(group, Duration::from_secs(3)));
    }

    #[test]
    fn ending_a_child_that_already_exited_does_nothing_and_does_not_hang() {
        let mut cmd = shell("exit 0");
        lead_own_group(&mut cmd);
        let mut child = cmd.spawn().unwrap();
        let _ = child.wait();
        let start = Instant::now();
        end(&mut child);
        assert!(start.elapsed() < TERM_GRACE);
    }
}
