//! The shell sentences the window words in its own language, in the shape the backend uses
//! (`backend/core/notices.py`): an English text, and the notices inside it, outermost first. The
//! window replaces each notice's `message` inside the text with its wording of the code.
//!
//! `app/src/i18n/notices.shell.json` is this table as the window reads it. A test here keeps the
//! two equal, and the window's tests fail while a code has no catalog entry.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub struct Template {
    pub code: &'static str,
    english: &'static str,
    /// The `{name}`s of `english`. Each is sent as text.
    params: &'static [&'static str],
}

/// Declares each template as a constant and lists it in `ALL`, so none can be left out of the JSON.
macro_rules! templates {
    ($($name:ident: $code:literal, [$($param:literal),*], $english:literal;)*) => {
        $(pub const $name: Template = Template { code: $code, english: $english, params: &[$($param),*] };)*
        #[cfg(test)]
        const ALL: &[&Template] = &[$(&$name),*];
    };
}

templates! {
    BACKEND_SPAWN_FAILED: "shell.backend.spawnFailed", ["error"], "Couldn't start the backend: {error}";
    BACKEND_EXITED_EARLY: "shell.backend.exitedEarly", ["detail"], "The backend stopped before it was ready.\n{detail}";
    BACKEND_STOPPED: "shell.backend.stopped", [], "The backend stopped, and restarting it several times didn't help. Close the app and open it again.";
    UPDATE_UNSUPPORTED: "shell.update.unsupported", [], "This platform doesn't have automatic updates yet. Download the new installer from the project page and replace the app you have.";
    UPDATE_STALLED: "shell.update.stalled", [], "The download stopped receiving data partway, so the app gave up on it. Check your internet connection, then click \"Download update\" again.";
    UPDATE_NO_SOURCE: "shell.update.noSource", [], "This version has no update source set up, so it can't check for updates.";
    UPDATE_TIMEOUT: "shell.update.timeout", [], "The update server didn't respond within 10 seconds. Try again later.";
    UPDATE_UNREACHABLE: "shell.update.unreachable", [], "Can't reach the update server. Check your internet connection, then try again later.";
    UPDATE_BAD_SIGNATURE: "shell.update.badSignature", [], "The signature of the downloaded update doesn't match, so the app discarded it and won't install it. Download the installer again from the project page.";
    UPDATE_INCOMPLETE: "shell.update.incomplete", [], "The update didn't finish. Try again later, or download the installer again from the project page.";
    UPDATE_NOT_INFO: "shell.update.notUpdateInfo", [], "The update source didn't return update information (the address may no longer work, or you may need to sign in first). Try again later, or download the installer again from the project page.";
    UPDATE_BAD_URL: "shell.update.badUrl", [], "VST_UPDATE_URL isn't a valid address.";
    UPDATE_CHECK_FIRST: "shell.update.checkFirst", [], "Check for updates first.";
    UPDATE_NOT_DOWNLOADED: "shell.update.notDownloaded", [], "The update hasn't finished downloading yet.";
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Notice {
    pub code: String,
    /// The backend also sends lists, so a value is any JSON the window can word.
    pub params: BTreeMap<String, serde_json::Value>,
    pub message: String,
}

/// A text for the window: what a command rejects with, and what `backend-failed` carries.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Said {
    pub message: String,
    pub notices: Vec<Notice>,
}

impl Said {
    /// Words the shell did not write, such as another library's error. They are shown as they are.
    pub fn plain(message: impl ToString) -> Said {
        Said { message: message.to_string(), notices: Vec::new() }
    }
}

impl Template {
    pub fn say(&self) -> Said {
        self.with(&[])
    }

    pub fn with(&self, values: &[(&str, &str)]) -> Said {
        debug_assert_eq!(values.iter().map(|(name, _)| *name).collect::<Vec<_>>(), self.params);
        // One pass over the template, so a `{name}` inside a value stays as it is.
        let mut message = String::new();
        let mut rest = self.english;
        while let Some(open) = rest.find('{') {
            let Some(length) = rest[open..].find('}') else { break };
            let name = &rest[open + 1..open + length];
            message.push_str(&rest[..open]);
            match values.iter().find(|(known, _)| *known == name) {
                Some((_, value)) => message.push_str(value),
                None => message.push_str(&rest[open..=open + length]),
            }
            rest = &rest[open + length + 1..];
        }
        message.push_str(rest);
        let params = values.iter().map(|(name, value)| (name.to_string(), (*value).into())).collect();
        let notice = Notice { code: self.code.into(), params, message: message.clone() };
        Said { message, notices: vec![notice] }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_checked_in_json_is_this_table() {
        let ours: serde_json::Value = ALL
            .iter()
            .map(|t| {
                let params: serde_json::Map<_, _> =
                    t.params.iter().map(|p| (p.to_string(), "text".into())).collect();
                (t.code.to_string(), serde_json::json!({ "english": t.english, "params": params }))
            })
            .collect::<serde_json::Map<_, _>>()
            .into();
        let theirs: serde_json::Value =
            serde_json::from_str(include_str!("../../src/i18n/notices.shell.json")).unwrap();

        assert_eq!(
            theirs,
            ours,
            "app/src/i18n/notices.shell.json must read:\n{}",
            serde_json::to_string_pretty(&ours).unwrap()
        );
    }

    #[test]
    fn no_code_is_used_twice_and_every_placeholder_is_declared() {
        let mut codes: Vec<_> = ALL.iter().map(|t| t.code).collect();
        codes.sort_unstable();
        codes.dedup();
        assert_eq!(codes.len(), ALL.len());
        for t in ALL {
            let named: Vec<_> =
                t.english.split('{').skip(1).filter_map(|rest| rest.split_once('}').map(|(n, _)| n)).collect();
            assert_eq!(named, t.params, "{}", t.code);
        }
    }

    #[test]
    fn a_value_that_looks_like_a_placeholder_is_left_alone() {
        let said = BACKEND_SPAWN_FAILED.with(&[("error", "no {error} here")]);

        assert_eq!(said.message, "Couldn't start the backend: no {error} here");
        assert_eq!(said.notices[0].message, said.message);
        assert_eq!(said.notices[0].params["error"], "no {error} here");
    }
}
