# Running the backend on a Mac (command line)

Status: written on Windows and **not yet run on a Mac**. Everything below the "Steps" heading is
what the code is built to do; the check on a real Mac is P37d. Speed and memory numbers do not
exist yet: any figure you see in the profiles is a design limit, not a measurement.

Scope of this page: the Python backend from a terminal (`python -m backend.cli` and the local
service). The desktop window and its installer for a Mac are a separate step (P37c).

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
   needed only for the desktop window (P37c), not for this page.

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

## Child programs and quitting

A Mac has no kill-on-parent-exit. The backend stops `llama-server`, `whisper-cli`, `crispasr` and
`ffmpeg` when it exits normally and when it gets SIGTERM or SIGHUP. A `kill -9` of the backend
cannot be caught and leaves them running; the desktop shell (P37c) is meant to stop the whole
process group. If you used `kill -9`, check `ps aux | grep -E "llama-server|whisper-cli|crispasr"`.

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
- stopping child programs after a signal.
