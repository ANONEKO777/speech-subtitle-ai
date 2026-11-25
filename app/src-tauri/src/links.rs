//! Which addresses `open_url` may open: https links on a host the license pages already use (the
//! registry's license URLs), the project's own host, and the SPDX host the license page builds its
//! part links from.

use std::collections::BTreeSet;
use std::io::Write;
use std::path::Path;
use url::Url;

use crate::platform::{self, Launch};

pub const PROJECT_URL: &str = "https://github.com/ANONEKO777/speech-subtitle-ai";
const SPDX_HOST: &str = "spdx.org";
/// The Microsoft page the wizard sends people to for the Visual C++ runtime.
const MICROSOFT_HOST: &str = "learn.microsoft.com";
const REGISTRY: &str = include_str!("../../../backend/manager/registry.json");

#[derive(serde::Deserialize)]
struct Asset {
    license_url: String,
}

#[derive(serde::Deserialize)]
struct Registry {
    models: Vec<Asset>,
    runtimes: Vec<Asset>,
}

fn host_of(address: &str) -> Option<String> {
    let url = Url::parse(address).ok()?;
    (url.scheme() == "https").then(|| url.host_str().map(str::to_ascii_lowercase)).flatten()
}

fn allowed_hosts() -> BTreeSet<String> {
    let registry: Registry = serde_json::from_str(REGISTRY).expect("registry.json is valid");
    registry
        .models
        .iter()
        .chain(&registry.runtimes)
        .map(|a| a.license_url.as_str())
        .chain([PROJECT_URL])
        .filter_map(host_of)
        .chain([SPDX_HOST, MICROSOFT_HOST].map(String::from))
        .collect()
}

/// Checks `address`, then appends it to `log` when one is given, else starts the default browser
/// on it. A log means no process is started.
pub fn open(address: &str, log: Option<&Path>) -> Result<(), String> {
    open_with(address, log, Launch::spawn)
}

fn open_with(address: &str, log: Option<&Path>, launch: impl FnOnce(Launch) -> Result<(), String>) -> Result<(), String> {
    let url = check(address)?;
    let Some(log) = log else {
        return launch(platform::here::browse(&url));
    };
    let mut file = std::fs::OpenOptions::new().create(true).append(true).open(log).map_err(|e| e.to_string())?;
    writeln!(file, "{url}").map_err(|e| e.to_string())
}

/// The address in the form it is opened in, when `address` is a plain https address (no
/// credentials, no port, nothing a shell could read as more than one argument) whose host is in
/// the allow-list.
pub fn check(address: &str) -> Result<String, String> {
    check_against(address, &allowed_hosts())
}

fn check_against(address: &str, hosts: &BTreeSet<String>) -> Result<String, String> {
    let plain = !address.chars().any(|c| c.is_whitespace() || c.is_control() || matches!(c, '"' | '^' | '&' | '\\'));
    let url = Url::parse(address).ok().filter(|u| {
        plain && u.scheme() == "https" && u.username().is_empty() && u.password().is_none() && u.port().is_none()
    });
    let Some(url) = url.filter(|u| u.as_str() == address) else {
        return Err(format!("{address} is not a plain https address in its canonical form"));
    };
    let host = url.host_str().unwrap_or_default();
    if hosts.contains(host) {
        Ok(url.into())
    } else {
        Err(format!("{host} is not a host this app opens links to"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_license_hosts_project_and_spdx_open() {
        for ok in [
            "https://github.com/ggml-org/whisper.cpp/blob/b5454/LICENSE",
            "https://huggingface.co/Qwen/Qwen3-8B-GGUF",
            "https://docs.nvidia.com/cuda/eula/index.html",
            PROJECT_URL,
            "https://spdx.org/licenses/MIT.html",
            "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        ] {
            assert_eq!(check(ok).as_deref(), Ok(ok), "{ok}");
        }
    }

    #[test]
    fn without_a_log_the_address_goes_to_the_launcher_of_the_system_this_runs_on() {
        let program = if cfg!(windows) {
            "explorer"
        } else if cfg!(target_os = "macos") {
            "open"
        } else {
            "xdg-open"
        };
        let mut seen = None;
        open_with(PROJECT_URL, None, |launch| {
            seen = Some(launch);
            Ok(())
        })
        .unwrap();
        assert_eq!(seen, Some(Launch { program, args: vec![PROJECT_URL.into()] }));
        assert!(open_with("https://example.com/", None, |_| panic!("a host that is not allowed")).is_err());
    }

    #[test]
    fn a_log_records_the_address_and_starts_nothing() {
        let log = std::env::temp_dir().join(format!("vst-open-url-{}.log", std::process::id()));
        let _ = std::fs::remove_file(&log);
        let launched = |_: Launch| -> Result<(), String> { panic!("a browser would have started") };
        open_with("https://github.com/ggml-org/whisper.cpp/blob/b5454/LICENSE", Some(&log), launched).unwrap();
        open_with(PROJECT_URL, Some(&log), launched).unwrap();
        assert!(open_with("https://example.com/", Some(&log), launched).is_err());
        let written = std::fs::read_to_string(&log).unwrap();
        std::fs::remove_file(&log).unwrap();
        assert_eq!(written, format!("https://github.com/ggml-org/whisper.cpp/blob/b5454/LICENSE
{PROJECT_URL}
"));
    }

    #[test]
    fn everything_else_is_refused() {
        for bad in [
            "http://github.com/x",
            "https://example.com/",
            "https://github.com.evil.com/",
            "https://evil.com/github.com",
            "https://github.com@evil.com/",
            "https://user@github.com/",
            "https://github.com:8443/",
            "https://github.com/a b",
            "https://github.com/a&calc",
            "file:///C:/Windows/System32/calc.exe",
            "calc.exe",
            "https:github.com/x",
            "https:/github.com/x",
            "https://github.com",
            "https://GitHub.com/x",
            "https://git\u{200b}hub.com/x",
            "https://github.com/x\u{200b}",
            "https://github.com:443/x",
            "",
        ] {
            assert!(check(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn every_registry_license_address_is_already_canonical() {
        let registry: Registry = serde_json::from_str(REGISTRY).unwrap();
        for asset in registry.models.iter().chain(&registry.runtimes) {
            assert_eq!(check(&asset.license_url).as_deref(), Ok(asset.license_url.as_str()));
        }
    }

    #[test]
    fn the_allow_list_is_the_three_registry_hosts_plus_project_spdx_and_microsoft() {
        let hosts: Vec<String> = allowed_hosts().into_iter().collect();
        assert_eq!(
            hosts,
            ["docs.nvidia.com", "github.com", "huggingface.co", "learn.microsoft.com", "spdx.org"]
        );
    }
}
