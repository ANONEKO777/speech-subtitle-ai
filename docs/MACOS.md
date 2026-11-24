# Running the backend on a Mac (command line)

Status: written on Windows and **not yet run on a Mac**. Everything below the "Steps" heading is
what the code is built to do; the check on a real Mac is P37d. Speed and memory numbers do not
exist yet: any figure you see in the profiles is a design limit, not a measurement.

Scope of this page: the Python backend from a terminal (`python -m backend.cli` and the local
service), then the desktop window and its disk image built on your Mac ("Build the app" below).

## What is supported

- A Mac with Apple silicon (M1 or later). An Intel Mac and Linux are not supported: the program
  stops at start with one sentence that says so.
- macOS 13 or later is assumed for the prebuilt llama.cpp and CrispASR archives (not checked).
- The default profile for a Mac with 32 GB or more of memory is `metal-32gb`: the speech model
  and the translation model run **one after the other**, never together. A second profile,
  `metal-32gb-parallel`, runs both at once. Nothing selects it for you; choose it on the profile
  page (or in `settings.json`) after you have measured that your Mac holds both.
- A 16 GB Mac gets `metal-16gb` (one at a time, translation context 8192, no second speech
  engine). A Mac below 16 GB gets `apple-cpu`, which recommends a cloud model.
- Japanese talks use CrispASR with the Qwen3-ASR model, as on Windows.

Not available yet:

- Saving a cloud API key. The settings page refuses with a plain sentence. Use the local model
  (the default) or Ollama.
- Playing `.mkv`, `.avi` and similar files in the window. Not worked on.
- Updates from inside the app. "Check for updates" on the settings page says that this platform
  has no automatic update; install a newer build by hand (see "Updating" below).
- ffmpeg inside the app. The app uses the Homebrew `ffmpeg` (step 2), so it is not packed in.

## What is installed where

The app's data folder on a Mac is `~/Library/Application Support/video-subtitle-translator`
(set `VST_USER_DATA` to use another one). Inside it:

| Folder | Holds |
|---|---|
| `runtimes/llama.cpp-b12068-macos-metal/` | `llama-server`, downloaded (about 16 MB) |
| `runtimes/crispasr-v0.8.49-macos-metal/` | `crispasr`, downloaded (about 18 MB) |
| `runtimes/whispercpp-b5454-macos-metal/` | `whisper-cli`, **built on your Mac** by the script below |
| `models/` | the model files, downloaded by the app |

whisper.cpp publishes no ready-made macOS program, so `whisper-cli` is built once on your Mac.
The app looks for it in the folder above first, then on `PATH`, then in `/opt/homebrew/bin` and
`/usr/local/bin`. If it is missing, the program stops with a message that names the script.

## Steps

1. Install the Xcode command line tools (gives you `git`, the compiler and Metal headers):

   ```
   xcode-select --install
   ```

2. Install Homebrew from <https://brew.sh> if you do not have it, then:

   ```
   brew install cmake ffmpeg uv
   ```

   `ffmpeg` and `ffprobe` are searched on `PATH` and in `/opt/homebrew/bin`. Burn-in needs an
   ffmpeg that has the VideoToolbox H.264 encoder; the Homebrew build is expected to (not checked). Node.js and Rust are
   needed only to build the desktop window (see "Build the app").

3. Get the code and the Python environment:

   ```
   git clone <the repository address> video-subtitle-translator
   cd video-subtitle-translator
   uv sync
   ```

4. Build `whisper-cli` (a few minutes, no `sudo`, writes only to a temporary folder and to the
   runtimes folder above):

   ```
   bash scripts/mac/build_whisper_cli.sh
   ```

   The script clones whisper.cpp at the tag the registry names (`b5454`), configures it with
   Metal and the shaders embedded, builds only `whisper-cli`, and copies it into place. To try
   another tag set `WHISPER_CPP_TAG=<tag>` before the command. The tag and the Metal switches
   have not been run by the author; if the build fails, the last lines of cmake's output say why.

5. Start the local service and download the runtimes and models for your profile. The service
   prints `READY port=<n> token=<t>`:

   ```
   uv run python -m backend.main
   ```

   In a second terminal, with that port and token:

   ```
   curl -s -X POST -H "Authorization: Bearer <t>" http://127.0.0.1:<n>/api/profile/download
   curl -s -H "Authorization: Bearer <t>" http://127.0.0.1:<n>/api/downloads
   ```

   The models are several gigabytes; the second command shows progress. Stop the service with
   Ctrl+C when the jobs are `done`.

6. Run a file:

   ```
   uv run python -m backend.cli talk.mp4 --lang zh-TW
   uv run python -m backend.cli talk.mp4 --source-lang ja
   ```

   `--cpu` keeps the speech and translation models off the GPU (the same programs, run on the
   CPU).

## Build the app

This makes `Video Subtitle Translator.app` and a `.dmg` disk image on your own Mac. Nothing here
needs `sudo` or an Apple account.

1. Do steps 1 to 4 of "Steps" above (command line tools, Homebrew packages, the code and `uv sync`,
   `whisper-cli`). Then install Node.js and Rust, which only the build needs:

   ```
   brew install node
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```

   Open a new Terminal window afterwards so `cargo` is on the path.

2. From the repository folder run:

   ```
   bash scripts/mac/build_app.sh
   ```

   It packs the backend with PyInstaller, installs the frontend packages, and runs `tauri build`
   for the `app` and `dmg` bundles. The first run compiles Rust and downloads packages: expect
   tens of minutes. It prints the two paths when it is done, under
   `app/src-tauri/target/release/bundle/` (`macos/` for the app, `dmg/` for the disk image).

3. To use it yourself, drag the `.app` from `bundle/macos/` into `Applications`. To pass it on,
   send the `.dmg`.

The app is signed **ad hoc** (no developer certificate). macOS accepts that for an app you built on
this Mac. For a copy that came from somewhere else (a download, a chat, an AirDrop), macOS treats
the app as from an unidentified developer and blocks the first start. That is expected.

### Open an app that macOS blocks (the first time only)

The steps differ a little between macOS versions. The idea is the same: you tell macOS once that you
trust this app.

- **macOS 15 (Sequoia) and later.** Open the app once (double-click). A window says the app cannot be
  checked. Click **Done**. Then open **System Settings**, **Privacy & Security**, scroll down to the
  line that names the app and click **Open Anyway**, enter your Mac password, and click **Open**.
- **macOS 14 (Sonoma) and earlier.** In Finder, right-click (or Control-click) the app and choose
  **Open**, then click **Open** in the window that appears. A plain double-click does not offer that
  button.
- **If neither shows a button**, remove the "downloaded from the Internet" mark in Terminal and open
  the app again. This only affects the one app you name:

  ```
  xattr -dr com.apple.quarantine "/Applications/Video Subtitle Translator.app"
  ```

An app you built yourself with the script is not marked as downloaded, so it normally opens with a
plain double-click. These steps are from Apple's documented behavior, not from a run on your Mac:
the wording of the buttons may differ.

### If the app will not open

- "is damaged and can't be opened": the signature is broken. Run
  `codesign --verify --deep --strict --verbose=2 "/Applications/Video Subtitle Translator.app"`. If
  it fails, sign the app again with
  `codesign --force --deep --sign - "/Applications/Video Subtitle Translator.app"` and send back
  the output of both commands.
- The window opens and stays empty, or says the backend did not start: run the app from Terminal to
  see the backend's messages:
  `"/Applications/Video Subtitle Translator.app/Contents/MacOS/video-subtitle-translator"`.

### Updating

There is no update button on a Mac. Build again (step 2) and replace the app in `Applications`. Your
projects, models and runtimes are in `~/Library/Application Support/video-subtitle-translator` and
stay.

### What the build cannot promise

- Nobody has built or run this on a Mac. The Mac-specific code was checked by unit tests and a
  compile on Windows and Linux. Every item under "What only a Mac can prove" is still open.
- A copy of the app for other people. Without a paid Apple Developer account the app cannot be
  notarized, so each person who receives it must do the "Open Anyway" steps above, and a later macOS
  release may make them harder. A notarized build needs the paid account and is a separate step.
- ffmpeg is not inside the app, so every Mac that runs it needs `brew install ffmpeg`.
- The PyInstaller backend has not been started from inside the `.app`. If the window says the
  backend did not start, that is the first place to look.

## Keyboard and menu

The app has the standard Mac menu bar that Tauri adds: the app menu with Quit (Cmd+Q) and Hide
(Cmd+H), a File menu with Close Window (Cmd+W), an Edit menu (Cmd+C, Cmd+V and the rest, so copy
and paste work in the page), and a Window menu. Closing the last window quits the app, as on
Windows, and stops the backend and every program it started.

## Child programs and quitting

A Mac has no kill-on-parent-exit. The backend stops `llama-server`, `whisper-cli`, `crispasr` and
`ffmpeg` when it exits normally and when it gets SIGTERM or SIGHUP. A `kill -9` of the backend
cannot be caught and leaves them running.

The desktop window covers that. It starts the backend as the leader of its own process group. When
you close the window or quit, it sends SIGTERM to the whole group, waits up to 2 seconds, then sends
SIGKILL to the group. If the window itself is killed (`kill -9`, or Force Quit), the backend notices
within about 2 seconds that the window's process is gone (the window passes its pid in
`VST_PARENT_PID`) and shuts down, which stops its children. A backend you start from Terminal has
no such variable and keeps running until you stop it. If something was killed hard anyway, check
`ps aux | grep -E "vst-backend|llama-server|whisper-cli|crispasr"`.

## Sleep and shutdown after a queue

"Sleep" runs `pmset sleepnow`. "Shut down" asks System Events to shut down, and macOS asks once
whether this app may control System Events. If you refuse, the machine does not shut down.

## What only a Mac can prove (P37d)

Nothing below has been run:

- that `llama-server`, `crispasr` and the built `whisper-cli` start and use Metal;
- that the downloaded programs run without a Gatekeeper prompt (downloads made by the app are
  not quarantined, but this was not tried);
- Qwen3-ASR quality and speed on Metal, and whether the Q8 model files load in this CrispASR;
- speed and memory of any stage, and whether the 36 GB default can run both models at once;
- the VideoToolbox quality value (`-q:v 65`) and the look of burned-in subtitles;
- that libass in the Homebrew ffmpeg finds the system fonts, and that `PingFang TC`, `Apple SD
  Gothic Neo` and `Hiragino Sans` are found in the folders the code scans (the
  `/System/Library/AssetsV2` folder for newer system fonts is a guess);
- the self-test on Metal: the checks only start the programs, they do not yet look for the word
  "Metal" in their output;
- stopping child programs after a signal;
- the window: that the built `.app` opens, shows the chip name and "unified memory" on the hardware
  page and the profile name for your memory size, starts the backend packed inside it, plays a
  video, and that "show in folder" opens Finder (`open -R`);
- that Cmd+Q and Cmd+W stop the backend (nothing left in `ps aux | grep vst-backend`), and that
  force-quitting the window ends the backend within a few seconds;
- that ad hoc signing is enough for the PyInstaller folder inside the app (the build script runs
  `codesign --verify --deep --strict` and only prints a warning if it fails);
- whether the macOS web view (WebKit) plays the files and draws the page as the Windows one does.

Not run on a Mac: every line above.
