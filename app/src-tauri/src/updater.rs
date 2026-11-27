//! Update check, download and install, driven by the settings page. Nothing here runs at start.
//! The endpoint comes from `plugins.updater.endpoints` in tauri.conf.json. `VST_UPDATE_URL` replaces
//! it (the e2e drivers do); the signature is still checked against the configured public key.

use serde::Serialize;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_updater::{Error, Update, UpdaterExt};

use crate::notice::{self, Said, Template};
use crate::platform;

const CHECK_TIMEOUT: Duration = Duration::from_secs(10);
/// A download is cut off when no data arrives for this long. The whole transfer has no limit, so a
/// slow but moving connection still finishes.
const STALL_LIMIT: Duration = Duration::from_secs(30);
#[derive(Default)]
pub struct Pending(Mutex<Option<Staged>>);

struct Staged {
    update: Update,
    bytes: Option<Vec<u8>>,
}

#[derive(Serialize)]
#[serde(tag = "state", rename_all = "camelCase")]
pub enum Checked {
    UpToDate { current: String },
    Available { current: String, version: String, notes: Option<String> },
}

fn plain(error: &Error) -> &'static Template {
    match error {
        Error::EmptyEndpoints => &notice::UPDATE_NO_SOURCE,
        Error::Reqwest(e) if e.is_timeout() => &notice::UPDATE_TIMEOUT,
        Error::Reqwest(e) if e.is_decode() => &notice::UPDATE_NOT_INFO,
        Error::Reqwest(_) | Error::Network(_) => &notice::UPDATE_UNREACHABLE,
        Error::ReleaseNotFound
        | Error::Serialization(_)
        | Error::Semver(_)
        | Error::TargetNotFound(_)
        | Error::TargetsNotFound(_) => &notice::UPDATE_NOT_INFO,
        Error::Minisign(_) | Error::Base64(_) | Error::SignatureUtf8(_) => &notice::UPDATE_BAD_SIGNATURE,
        _ => &notice::UPDATE_INCOMPLETE,
    }
}

fn failed(error: Error) -> Said {
    plain(&error).say()
}

fn endpoint_override() -> Result<Option<url::Url>, Said> {
    let Some(raw) = std::env::var_os("VST_UPDATE_URL") else {
        return Ok(None);
    };
    raw.to_string_lossy().parse().map(Some).map_err(|_| notice::UPDATE_BAD_URL.say())
}

/// Only the Windows installer has update artifacts, so any other system is told so before anything is fetched.
fn ensure_supported() -> Result<(), Said> {
    if platform::here::updates_supported() {
        Ok(())
    } else {
        Err(notice::UPDATE_UNSUPPORTED.say())
    }
}

#[tauri::command]
pub async fn update_check<R: Runtime>(app: AppHandle<R>, pending: tauri::State<'_, Pending>) -> Result<Checked, Said> {
    ensure_supported()?;
    let mut builder = app.updater_builder().timeout(CHECK_TIMEOUT);
    if let Some(url) = endpoint_override()? {
        builder = builder.endpoints(vec![url]).map_err(failed)?;
    }
    let updater = builder.build().map_err(failed)?;
    let current = app.package_info().version.to_string();
    let found = updater.check().await.map_err(failed)?;
    let mut slot = pending.0.lock().map_err(Said::plain)?;
    match found {
        None => {
            *slot = None;
            Ok(Checked::UpToDate { current })
        }
        Some(update) => {
            let seen = Checked::Available { current, version: update.version.clone(), notes: update.body.clone() };
            *slot = Some(Staged { update, bytes: None });
            Ok(seen)
        }
    }
}

/// Downloads the announced installer and checks its signature against the configured public key.
/// Nothing is installed.
#[tauri::command]
pub async fn update_download(pending: tauri::State<'_, Pending>) -> Result<(), Said> {
    let mut update = {
        let slot = pending.0.lock().map_err(Said::plain)?;
        slot.as_ref().ok_or_else(|| notice::UPDATE_CHECK_FIRST.say())?.update.clone()
    };
    update.timeout = None;
    let last_data = Arc::new(Mutex::new(Instant::now()));
    let touch = Arc::clone(&last_data);
    let download = update.download(
        move |_, _| {
            if let Ok(mut at) = touch.lock() {
                *at = Instant::now();
            }
        },
        || {},
    );
    let bytes = tokio::select! {
        done = download => done.map_err(failed)?,
        () = stalled(&last_data, STALL_LIMIT) => return Err(notice::UPDATE_STALLED.say()),
    };
    let mut slot = pending.0.lock().map_err(Said::plain)?;
    *slot = Some(Staged { update, bytes: Some(bytes) });
    Ok(())
}

/// Resolves once `limit` has passed since the time in `last_data` was last refreshed.
async fn stalled(last_data: &Mutex<Instant>, limit: Duration) {
    loop {
        let idle = last_data.lock().map(|at| at.elapsed()).unwrap_or(limit);
        if idle >= limit {
            return;
        }
        tokio::time::sleep(limit - idle).await;
    }
}

/// Starts the downloaded installer, which closes this app. The backend is stopped first.
#[tauri::command]
pub fn update_install(app: AppHandle, pending: tauri::State<'_, Pending>) -> Result<(), Said> {
    let slot = pending.0.lock().map_err(Said::plain)?;
    let Some(Staged { update, bytes: Some(bytes) }) = slot.as_ref() else {
        return Err(notice::UPDATE_NOT_DOWNLOADED.say());
    };
    app.state::<crate::sidecar::BackendState>().stop();
    update.install(bytes).map_err(failed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_library_failure_gets_its_own_sentence_without_the_library_wording() {
        let html = serde_json::from_str::<serde_json::Value>("<html>sign in</html>").unwrap_err();
        for (error, code) in [
            (Error::EmptyEndpoints, "shell.update.noSource"),
            (Error::ReleaseNotFound, "shell.update.notUpdateInfo"),
            (Error::Serialization(html), "shell.update.notUpdateInfo"),
            (Error::Network("Download request failed with status: 404".into()), "shell.update.unreachable"),
            (Error::SignatureUtf8("x".into()), "shell.update.badSignature"),
            (Error::UnsupportedArch, "shell.update.incomplete"),
        ] {
            let said = failed(error);
            assert_eq!(said.notices.iter().map(|n| n.code.as_str()).collect::<Vec<_>>(), [code]);
            let text = said.message;
            assert!(!text.contains("JSON") && !text.contains("expected") && !text.contains("404"), "{text}");
        }
    }

    #[cfg(not(windows))]
    #[test]
    fn the_update_check_command_refuses_before_it_reaches_the_network_on_a_system_without_updates() {
        let app = tauri::test::mock_builder()
            .manage(Pending::default())
            .build(tauri::test::mock_context(tauri::test::noop_assets()))
            .unwrap();
        let handle = app.handle().clone();

        let answer = tauri::async_runtime::block_on(update_check(handle.clone(), handle.state::<Pending>()));

        assert_eq!(answer.err(), Some(notice::UPDATE_UNSUPPORTED.say()));
    }

    #[test]
    fn a_page_that_is_not_json_says_it_may_need_a_sign_in() {
        assert!(failed(Error::ReleaseNotFound).message.contains("sign in first"));
    }

    #[test]
    fn only_windows_may_check_and_the_rest_are_told_why() {
        if cfg!(windows) {
            assert_eq!(ensure_supported(), Ok(()));
        } else {
            assert_eq!(ensure_supported(), Err(notice::UPDATE_UNSUPPORTED.say()));
        }
    }

    #[test]
    fn a_bad_signature_is_never_called_a_network_problem() {
        assert_eq!(plain(&Error::SignatureUtf8("x".into())).code, "shell.update.badSignature");
    }

    #[test]
    fn a_download_with_no_data_is_cut_off_and_data_keeps_it_alive() {
        tauri::async_runtime::block_on(async {
            let limit = Duration::from_millis(200);
            let last = Arc::new(Mutex::new(Instant::now()));
            let start = Instant::now();
            let touch = Arc::clone(&last);
            let feeder = tauri::async_runtime::spawn(async move {
                for _ in 0..4 {
                    tokio::time::sleep(Duration::from_millis(100)).await;
                    *touch.lock().unwrap() = Instant::now();
                }
            });
            stalled(&last, limit).await;
            feeder.await.unwrap();
            assert!(start.elapsed() >= Duration::from_millis(550), "{:?}", start.elapsed());
            assert!(start.elapsed() < Duration::from_secs(2), "{:?}", start.elapsed());
        });
    }
}
