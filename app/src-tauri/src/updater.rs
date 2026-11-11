//! Update check, download and install, driven by the settings page. Nothing here runs at start.
//! The endpoint comes from `plugins.updater.endpoints` in tauri.conf.json. `VST_UPDATE_URL` replaces
//! it (the e2e drivers do); the signature is still checked against the configured public key.

use serde::Serialize;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager};
use tauri_plugin_updater::{Error, Update, UpdaterExt};

const CHECK_TIMEOUT: Duration = Duration::from_secs(10);
/// A download is cut off when no data arrives for this long. The whole transfer has no limit, so a
/// slow but moving connection still finishes.
const STALL_LIMIT: Duration = Duration::from_secs(30);
const STALLED: &str = "更新檔下載到一半沒有再收到資料，已經放棄。請確認網路連線，再按一次「下載」。";

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

fn plain(error: &Error) -> String {
    match error {
        Error::EmptyEndpoints => "這個版本沒有設定更新來源，無法檢查更新。".into(),
        Error::Reqwest(e) if e.is_timeout() => "更新伺服器沒有在 10 秒內回應。請稍後再試。".into(),
        Error::Reqwest(e) if e.is_decode() => not_update_info(),
        Error::Reqwest(_) | Error::Network(_) => {
            "連不上更新伺服器。請確認網路連線，稍後再試。".into()
        }
        Error::ReleaseNotFound
        | Error::Serialization(_)
        | Error::Semver(_)
        | Error::TargetNotFound(_)
        | Error::TargetsNotFound(_) => not_update_info(),
        Error::Minisign(_) | Error::Base64(_) | Error::SignatureUtf8(_) => {
            "下載的更新檔簽章不符，已放棄，不會安裝。請到專案網頁重新下載安裝程式。".into()
        }
        _ => "更新沒有完成。請稍後再試，或到專案網頁重新下載安裝程式。".into(),
    }
}

fn not_update_info() -> String {
    "更新來源回傳的不是更新資訊（網址可能已失效，或需要先登入）。請稍後再試，或到專案網頁重新下載安裝程式。".into()
}

fn endpoint_override() -> Result<Option<url::Url>, String> {
    let Some(raw) = std::env::var_os("VST_UPDATE_URL") else {
        return Ok(None);
    };
    raw.to_string_lossy().parse().map(Some).map_err(|_| "VST_UPDATE_URL 不是有效的網址。".to_string())
}

#[tauri::command]
pub async fn update_check(app: AppHandle, pending: tauri::State<'_, Pending>) -> Result<Checked, String> {
    let mut builder = app.updater_builder().timeout(CHECK_TIMEOUT);
    if let Some(url) = endpoint_override()? {
        builder = builder.endpoints(vec![url]).map_err(|e| plain(&e))?;
    }
    let updater = builder.build().map_err(|e| plain(&e))?;
    let current = app.package_info().version.to_string();
    let found = updater.check().await.map_err(|e| plain(&e))?;
    let mut slot = pending.0.lock().map_err(|e| e.to_string())?;
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
pub async fn update_download(pending: tauri::State<'_, Pending>) -> Result<(), String> {
    let mut update = {
        let slot = pending.0.lock().map_err(|e| e.to_string())?;
        slot.as_ref().ok_or("請先檢查更新。")?.update.clone()
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
        done = download => done.map_err(|e| plain(&e))?,
        () = stalled(&last_data, STALL_LIMIT) => return Err(STALLED.into()),
    };
    let mut slot = pending.0.lock().map_err(|e| e.to_string())?;
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
pub fn update_install(app: AppHandle, pending: tauri::State<'_, Pending>) -> Result<(), String> {
    let slot = pending.0.lock().map_err(|e| e.to_string())?;
    let Some(Staged { update, bytes: Some(bytes) }) = slot.as_ref() else {
        return Err("更新檔還沒有下載好。".into());
    };
    app.state::<crate::sidecar::BackendState>().stop();
    update.install(bytes).map_err(|e| plain(&e))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn failures_read_as_plain_zh_tw_without_the_library_wording() {
        let html = serde_json::from_str::<serde_json::Value>("<html>sign in</html>").unwrap_err();
        for error in [
            Error::EmptyEndpoints,
            Error::ReleaseNotFound,
            Error::Serialization(html),
            Error::Network("Download request failed with status: 404".into()),
            Error::SignatureUtf8("x".into()),
            Error::UnsupportedArch,
        ] {
            let text = plain(&error);
            assert!(text.chars().any(|c| ('\u{4e00}'..='\u{9fff}').contains(&c)), "{text}");
            assert!(!text.contains("JSON") && !text.contains("expected") && !text.contains("platform"), "{text}");
        }
    }

    #[test]
    fn a_page_that_is_not_json_says_it_may_need_a_sign_in() {
        assert!(plain(&Error::ReleaseNotFound).contains("需要先登入"));
    }

    #[test]
    fn a_bad_signature_is_never_called_a_network_problem() {
        assert!(plain(&Error::SignatureUtf8("x".into())).contains("簽章"));
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

    #[test]
    fn the_stall_message_is_plain_zh_tw() {
        assert!(STALLED.chars().any(|c| ('一'..='鿿').contains(&c)));
        assert!(!STALLED.contains("timeout"));
    }
}
