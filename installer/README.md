# Windows installer

`powershell -File installer/build.ps1` builds the per-user NSIS installer (no admin rights). It needs Rust (`~/.cargo/bin`), Node, `uv`, and network access for the FFmpeg zip, NSIS and the WebView2 bootstrapper on the first run.

Steps: PyInstaller makes the backend folder (`sidecar.spec`, no PyTorch, no CUDA), the pinned LGPL FFmpeg is downloaded, hash-checked, checked for `--enable-gpl` and `--enable-nonfree`, and checked for libraries without a license entry, then `tauri build --bundles nsis` packs the shell, front end, backend, FFmpeg and licenses (`tauri.bundle.conf.json` adds the two build folders). The script fails above 150 MB and runs `tests/test_package_contents.py` against the installer.

Output: `app/src-tauri/target/release/bundle/nsis/*-setup.exe`, its `.sig`, and `installer/build/size.txt`.

## FFmpeg pin

`installer/ffmpeg.json` names the BtbN build: its release tag, zip, SHA-256 and FFmpeg commit. BtbN deletes daily builds after a few weeks and keeps the month-end ones, so pin a month-end tag (`autobuild-YYYY-MM-DD-...` on the last day of a month). `build.ps1` downloads the zip from BtbN, else from this repository's release named in `mirror_release`, and keeps it only when the hash matches. When neither source has it, the build stops and names both addresses.

To keep a copy in this repository, run `installer/mirror_ffmpeg.ps1` after a build. It prints the `gh` command it would run; `-Upload` runs it. The copy is a pre-release, so it never becomes the release the updater reads.

To move to a newer build:

1. Pick the `win64-lgpl-shared-8.1` zip of a month-end tag at https://github.com/BtbN/FFmpeg-Builds/releases and copy the SHA-256 that GitHub shows for it. A new FFmpeg major version changes the DLL names in `build.ps1` and `THIRD_PARTY.md`.
2. Update `installer/ffmpeg.json` and the build, commit and source offer lines in `installer/THIRD_PARTY.md`, and `FFMPEG_SOURCE_URL` in `app/src/settings/LicensesSection.tsx`. `tests/test_ffmpeg_pin.py` fails until they agree.
3. Run `build.ps1`. It stops when the build enables a library that `fetch_ffmpeg_licenses.py` has no license entry for. Add the entry, run `uv run python installer/fetch_ffmpeg_licenses.py`, and review the diff of `installer/licenses/FFmpeg-external-libraries.txt`.

## Updater signing key

The installer is signed for the Tauri updater with a key kept outside the repository, by default `~/.tauri/video-subtitle-translator.key` (public half `.key.pub`, which is the `pubkey` in `app/src-tauri/tauri.conf.json`). Pass another path with `-Key`. The key has no password. Back it up. A new key means installed apps cannot update to builds signed with it. Never commit it.

## Updates

The app checks for updates only when the person presses 檢查更新 on the settings page. It never checks at start. The check reads `latest.json` from the address in `plugins.updater.endpoints` in `app/src-tauri/tauri.conf.json`, downloads the installer it names, and checks its signature against the `pubkey` in the same file before offering 安裝並重新啟動.

To publish a build:

1. Set the key in the environment, never in a file in the repository: `$env:TAURI_SIGNING_PRIVATE_KEY` is the key text or its path (`-Key` is used when it is unset). `build.ps1` never prints it.
2. `powershell -File installer/build.ps1 -UpdateBaseUrl https://<where the files will be>/ -Notes "<what changed>"` writes `installer/build/latest.json`. The `url` inside it is `<UpdateBaseUrl>/<installer file name>`.
3. Upload `latest.json` and `app/src-tauri/target/release/bundle/nsis/*-setup.exe` to that folder, and make `endpoints` in `tauri.conf.json` point at `<UpdateBaseUrl>/latest.json`.

The address must work without signing in: an anonymous request has to get the JSON (or the installer) itself, not a login page. A page that is not JSON shows the person "更新來源回傳的不是更新資訊（網址可能已失效，或需要先登入）". The released app reads `https://github.com/ANONEKO777/speech-subtitle-ai/releases/latest/download/latest.json`, so publishing a build means creating a GitHub release for the tag that has `latest.json` and the `*-setup.exe` as its files and passing `-UpdateBaseUrl https://github.com/ANONEKO777/speech-subtitle-ai/releases/download/<tag>/`. Nothing in this repository creates a release or uploads anything by itself, and no workflow holds the signing key. Apps installed from a build made before this change still look at the old address and need one manual install of a newer build.

`VST_UPDATE_URL` replaces the configured address for one run (the e2e drivers use it). The public key still decides what installs.

### Testing the updater without the real key

`app/e2e/update-lanes.mjs` proves check, available, download and signature verification against a local server, and stops before installing. It needs an exe whose updater trusts a throwaway key and accepts `http://127.0.0.1`:

```
npx tauri signer generate -w <scratch>/test.key -p "" --ci
npx tauri build --no-bundle --config '{"plugins":{"updater":{"pubkey":"<contents of test.key.pub, base64 as in tauri.conf.json>","dangerousInsecureTransportProtocol":true}}}'
node app/e2e/update-lanes.mjs <exe> <shots> <scratch> <scratch>/test.key
```

The overlay is never committed. A real install of an update is not covered by it.
