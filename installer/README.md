# Windows installer

`powershell -File installer/build.ps1` builds the per-user NSIS installer (no admin rights). It needs Rust (`~/.cargo/bin`), Node, `uv`, and network access for the FFmpeg zip, NSIS and the WebView2 bootstrapper on the first run.

Steps: PyInstaller makes the backend folder (`sidecar.spec`, no PyTorch, no CUDA), the pinned LGPL FFmpeg is downloaded, hash-checked, checked for `--enable-gpl` and `--enable-nonfree`, and checked for libraries without a license entry, then `tauri build --bundles nsis` packs the shell, front end, backend, FFmpeg and licenses (`tauri.bundle.conf.json` adds the two build folders). The script fails above 150 MB and runs `tests/test_package_contents.py` against the installer.

Output: `installer/build/release` holds the files to upload: the installer, its `.sig`, `latest.json` when `-UpdateBaseUrl` is given, and `SHA256SUMS.txt`. Tauri's own output stays in `app/src-tauri/target/release/bundle/nsis`, and `installer/build/size.txt` records the size.

## FFmpeg pin

`installer/ffmpeg.json` names the BtbN build: its release tag, zip, SHA-256 and FFmpeg commit. BtbN deletes daily builds after a few weeks and keeps the month-end ones, so pin a month-end tag (`autobuild-YYYY-MM-DD-...` on the last day of a month). `build.ps1` downloads the zip from BtbN, else from this repository's release named in `mirror_release`, and keeps it only when the hash matches. When neither source has it, the build stops and names both addresses.

To keep a copy in this repository, run `installer/mirror_ffmpeg.ps1` after a build. It prints the `gh` command it would run; `-Upload` runs it. The copy is a pre-release, so it never becomes the release the updater reads.

To move to a newer build:

1. Pick the `win64-lgpl-shared-8.1` zip of a month-end tag at https://github.com/BtbN/FFmpeg-Builds/releases and copy the SHA-256 that GitHub shows for it. A new FFmpeg major version changes the DLL names in `build.ps1` and `THIRD_PARTY.md`.
2. Update `installer/ffmpeg.json` and the build, commit and source offer lines in `installer/THIRD_PARTY.md`, and `FFMPEG_SOURCE_URL` in `app/src/settings/LicensesSection.tsx`. `tests/test_ffmpeg_pin.py` fails until they agree.
3. Run `build.ps1`. It stops when the build enables a library that `fetch_ffmpeg_licenses.py` has no license entry for. Add the entry, run `uv run python installer/fetch_ffmpeg_licenses.py`, and review the diff of `installer/licenses/FFmpeg-external-libraries.txt`.

## Updater signing key

The installer is signed for the Tauri updater with a password-protected key kept outside the repository: minisign key id `501D2BFE8D7BD4B3`, by default at `~/.tauri/video-subtitle-translator-v2.key`. Its public half (`.key.pub`) is the `pubkey` in `app/src-tauri/tauri.conf.json`. Pass another path with `-Key`, and the password in `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. The release workflow reads both from the `release` environment, as the secrets `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. The operator made the key and set up that environment on 2026-11-28 (`docs/RELEASE-KEY.zh-TW.md`). Never commit the key.

The key used before, id `6B4A3984C4140F4D` at `~/.tauri/video-subtitle-translator.key` without a password, signed the 0.1.0 builds. Those installs trust only it, so they cannot update to a build signed with the new key and need one manual install of a newer build. The old key stays until no installed copy needs it.

`-Unsigned` builds without any key and without the updater files. Such an installer installs normally but cannot be offered as an update.

## Versions

`version` in `app/src-tauri/tauri.conf.json` is the app version. `package.json`, `Cargo.toml`, `pyproject.toml` and their lock files carry copies. `python scripts/version.py --set X.Y.Z` writes all of them, and `tests/test_version.py` fails when they disagree.

## Releases

`.github/workflows/release.yml` builds releases.

- **A tag `vX.Y.Z`** (the version in `tauri.conf.json`) checks the versions, runs the CI tests, builds on `windows-latest` with the key from the `release` environment, checks the files with `scripts/check_release_files.py`, and creates a **draft** release with the installer, its `.sig`, `latest.json` and `SHA256SUMS.txt`. The release text comes from `installer/release-notes.md`, with the annotated tag's message at the top; that message is also the `notes` in `latest.json`, which the app shows with the update. Nobody sees the draft, and no app finds it, until the operator presses Publish.
- **A pull request** that touches the release files builds the installer with `-Unsigned`, checks the files, and keeps `installer/build/release` as the workflow artifact `installer-<version>`. It reads no secret and creates no release.

To make a release:

1. `python scripts/version.py --set X.Y.Z`, commit, merge to `main`.
2. `git tag -a vX.Y.Z -m "<what changed, for the update prompt>"` on that commit, then `git push origin vX.Y.Z`.
3. Approve the `release` environment when GitHub asks.
4. Read the draft release, then press Publish.

A tag that does not equal the version stops the workflow before the build. To build again for the same tag, delete its draft release first. The release builds use no dependency cache, so a cache written by a pull request cannot reach a signed build.

Before the draft, `check_release_files.py` verifies the `.sig` against `plugins.updater.pubkey` in `tauri.conf.json`, as the app's updater does, so a release signed with any other key stops there with both key ids named.

Follow-up, not done yet: the signing key and its password are in the environment of the whole `Build and sign` step, so `uv sync`, PyInstaller, `npm ci` and every crate's `build.rs` run beside them. A tighter shape builds unsigned in one step and signs the finished installer with `tauri signer sign` in a second step that alone holds the secrets.

## Updates

The app checks for updates only when the person presses 檢查更新 on the settings page. It never checks at start. The check reads `latest.json` from the address in `plugins.updater.endpoints` in `app/src-tauri/tauri.conf.json`, downloads the installer it names, and checks its signature against the `pubkey` in the same file before offering 安裝並重新啟動.

The released app reads `https://github.com/ANONEKO777/speech-subtitle-ai/releases/latest/download/latest.json`, which GitHub serves from the newest published release that is not a pre-release. The release workflow checks that `endpoints` still names this repository. The address must work without signing in: an anonymous request has to get the JSON (or the installer) itself, not a login page. A page that is not JSON shows the person "更新來源回傳的不是更新資訊（網址可能已失效，或需要先登入）".

To publish a build by hand instead, set the key as above and run `powershell -File installer/build.ps1 -UpdateBaseUrl https://<where the files will be>/ -Notes "<what changed>"`. Upload everything in `installer/build/release` to that folder, and make `endpoints` point at `<UpdateBaseUrl>/latest.json`. GitHub turns spaces in a release file's name into dots, so `build.ps1` names the installer there with hyphens instead and `latest.json` uses that name.

`VST_UPDATE_URL` replaces the configured address for one run (the e2e drivers use it). The public key still decides what installs.

### Testing the updater without the real key

`app/e2e/update-lanes.mjs` proves check, available, download and signature verification against a local server, and stops before installing. It needs an exe whose updater trusts a throwaway key and accepts `http://127.0.0.1`:

```
npx tauri signer generate -w <scratch>/test.key -p "" --ci
npx tauri build --no-bundle --config '{"plugins":{"updater":{"pubkey":"<contents of test.key.pub, base64 as in tauri.conf.json>","dangerousInsecureTransportProtocol":true}}}'
node app/e2e/update-lanes.mjs <exe> <shots> <scratch> <scratch>/test.key
```

The overlay is never committed. A real install of an update is not covered by it.
