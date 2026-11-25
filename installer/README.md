# Windows installer

`powershell -File installer/build.ps1` builds the per-user NSIS installer (no admin rights). It needs Rust (`~/.cargo/bin`), Node, `uv`, and network access for the FFmpeg zip, NSIS and the WebView2 bootstrapper on the first run.

Steps: PyInstaller makes the backend folder (`sidecar.spec`, no PyTorch, no CUDA), the pinned LGPL FFmpeg is downloaded, hash-checked and checked for `--enable-gpl` and `--enable-nonfree`, then `tauri build --bundles nsis` packs the shell, front end, backend, FFmpeg and licenses (`tauri.bundle.conf.json` adds the two build folders). The script fails above 150 MB and runs `tests/test_package_contents.py` against the installer.

Output: `app/src-tauri/target/release/bundle/nsis/*-setup.exe`, its `.sig`, and `installer/build/size.txt`.

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
