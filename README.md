<div align="center">

**English** | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

# Video Subtitle Translator

**Turn a long English or Japanese talk into well-timed bilingual subtitles and a key-points summary, on your own PC and your own GPU.**

![license](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)
![platform](https://img.shields.io/badge/platform-Windows-0078D6)
![runs](https://img.shields.io/badge/runs-locally%20on%20your%20GPU-f0b23e)
![status](https://img.shields.io/badge/status-build%20from%20source-lightgrey)

<img src="docs/media/hero.png" alt="The player with English and Traditional Chinese subtitles under the video, and the cue list on the right" width="900">

</div>

Pick an English, Japanese, or mixed Japanese and English talk video that has no subtitles. The app recognizes the speech, cuts it into subtitle lines, translates them, writes a summary with chapters, and plays the video with the subtitles under it. Every step runs on your machine. On an RTX 4090 a 38-minute talk takes about 5 to 6 minutes.

## Features

### The whole pipeline runs locally

Import a video and the window shows the seven steps as they happen: audio extraction, voice detection, speech recognition, sentence splitting, translation, subtitle output and the summary. Every step is cached in the project folder. Run it again and finished steps are skipped. Stop it halfway and it resumes at the step it stopped on. Change the translation model and only translation, export and the summary run again.

<img src="docs/media/import-progress.png" alt="The import screen at 61 percent, in the translation step, with the seven-step strip" width="760">

### Bilingual subtitles under the video

The subtitles sit under the video, not on top of it, and they are separate from the video file. Switch between the original only, the translation only, or both. The video never changes size when you switch, and the cue list on the right follows playback. Click a cue to jump to it.

| Original only | Translation only | Both |
| --- | --- | --- |
| <img src="docs/media/mode-en.png" alt="Original only mode (the original of this talk is English)" width="290"> | <img src="docs/media/mode-zh.png" alt="Chinese only mode" width="290"> | <img src="docs/media/mode-both.png" alt="Bilingual mode, original and translation" width="290"> |

### Fix a line right in the list

Double-click a cue, or press F2 on it, to edit its time and text. Enter saves, Esc cancels, and Ctrl+Z undoes. A bad edit is refused with the reason shown in the row: overlapping the next cue, ending before it starts, running longer than 7 seconds, empty text, or a malformed time. The English line is the recognition result and stays read-only, because the translations and the summary are built from it.

An edited cue is never overwritten silently. If you translate the same project again from the command line or the API, your edits are laid back over the new translation, and the run reports how many were kept and how many no longer fit.

| A refused edit | A saved edit |
| --- | --- |
| <img src="docs/media/edit-error.png" alt="An overlapping time refused, with the reason shown in the row" width="440"> | <img src="docs/media/edit-saved.png" alt="A saved edit marked with a pencil" width="440"> |

### A summary with chapters

The summary tab shows a one-line gist, chapters with timestamps, key points and takeaways. Click a chapter's timestamp and the video jumps there.

<img src="docs/media/summary.png" alt="The summary tab with a chapter card and key points" width="760">

### A real player with a library

Every finished talk sits in a library with a thumbnail, its languages and a resume bar. The play queue steps from one talk to the next, and a talk reopens where you stopped. The controls sit over the bottom of the picture, so the subtitles stay below it. You get play, previous and next talk, previous and next line, volume, a seek bar, speed from 0.5 to 2, an A-B loop, a subtitle offset, a screenshot of the current frame, picture in picture and fullscreen. Frame step and the other keys are on the keyboard, and `?` lists them all. Drop a video on the window to import it.

The offset does not rewrite the cues. It is applied when you play and when you export, so you can take it back.

<img src="docs/media/library.png" alt="The library tab with thumbnails, language chips and the play queue" width="760">

<img src="docs/media/shortcuts.png" alt="The keyboard shortcut list opened over the player" width="760">

### Export

Export SRT (original, translation or bilingual), ASS, VTT, and the summary as Markdown. Subtitle files are plain UTF-8 and open in any player. You can also burn the subtitles into an MP4, for the whole video or for 30 seconds from where you are.

<img src="docs/media/export-menu.png" alt="The export menu listing SRT, ASS, VTT, the summary and the burned-in video" width="760">

### Batch queue

Queue many videos and let them run, overnight if you like. Add several files at once, pick a folder, or drop files on the window, and choose a target language for each video. The panel shows each video's state, its current step and an estimate of the time left. Pause the queue or one video, cancel, retry, remove, or drag a row to reorder. A finished row opens in the player. When the queue ends you get a notice in the window and a Windows notification. The app can also put the PC to sleep or shut it down, but that is off by default and needs your confirmation first.

| Adding videos, one language each | A queue at work |
| --- | --- |
| <img src="docs/media/queue-add.png" alt="The add dialog with five clips and a language for each" width="440"> | <img src="docs/media/queue-running.png" alt="The queue with one video done, one nearly done and three waiting" width="440"> |

### Settings and first-run setup

The first time you start the app with no speech or translation model installed, a setup wizard detects your GPU, VRAM, driver, RAM and free disk. It recommends one of three profiles (24 GB GPU, 8 GB GPU, CPU only), lists every download with its size and license, downloads with progress and a cancel button, and ends with a self-test. If the GPU test fails, it falls back to the CPU and says why.

The gear button opens the settings page. There you can verify, repair, re-download or delete each model and runtime, check for updates, move the models folder, switch the profile at any time, choose the language model (built in, Ollama, or a cloud model after you agree that the text leaves your PC), and read the license of every component.

| First-run wizard | Downloading, with progress |
| --- | --- |
| <img src="docs/media/wizard.png" alt="The first-run wizard with the detected RTX 4090 and three profiles" width="440"> | <img src="docs/media/wizard-downloading.png" alt="The wizard downloading models, with overall and per-file progress" width="440"> |

| Models and runtimes | Hardware and profile |
| --- | --- |
| <img src="docs/media/settings-models.png" alt="The settings page listing installed models and runtimes" width="440"> | <img src="docs/media/settings-hardware.png" alt="The hardware page with the detected GPU and the three profiles" width="440"> |

### Thirteen target languages

Traditional Chinese (Taiwan) is the default. A project can hold several languages side by side, and a selector in the cue column switches between them. Each language has its own prompt and its own script check, so a reply in the wrong writing system is rejected and asked again. See [Target languages](#target-languages).

<img src="docs/media/languages.png" alt="The same talk shown in Japanese, with the language selector in the cue column" width="760">

### English, Japanese and mixed videos

At import, the "video language" menu says what language the people in the video speak: English (the default) or Japanese. A Japanese video is recognized as Japanese, cut into subtitle lines at Japanese punctuation and meaning units, and translated into the language you pick beside it: Traditional Chinese (Taiwan) by default, or English, Simplified Chinese or Korean (experimental). The subtitle language menu sits next to the video language menu. A Japanese project can hold several subtitle languages: a button in the cue column adds another one, which only translates again, and the language selector there switches between them, for playing, export and burned-in subtitles. In the batch queue one video can have several subtitle languages, each its own row with its own state, and a failed one can be retried alone. A sentence that failed every check is marked in the cue list with a count and the reason, and can be filtered. The bilingual mode of the player shows the Japanese original and the Traditional Chinese together under the video. The subtitle offset, editing, export and burned-in subtitles work the same as for English. Each item in the batch queue can have its own video language, and the library and the queue put a small tag on a Japanese video. The original is the source of the translation and the summary, so the list does not let you edit it, only the translation and the times. Burning Japanese subtitles needs one of the fonts Yu Gothic, Meiryo or MS Gothic on the PC, and the window says so when there is none.

The third choice, "Japanese and English mixed", is for a talk where a Japanese speaker is followed by an English speaker. The app recognizes both languages in the one video, and every subtitle line keeps its own language. The cue list and the editor put a small 日 or 英 next to each original line, and only in a mixed video. In the bilingual mode of the player, each original line is shown in its own language, together with the Traditional Chinese line. The Traditional Chinese line is on top by default, and the toolbar switch 繁體中文在上 swaps the order. Editing never merges two neighbouring lines of different languages. The library and the queue put the tag 日英混合 on these videos. The original subtitle file of a mixed video is exported as `<video>.ja-en.srt`, and burning subtitles into it needs the same Japanese font as a Japanese video. Picking the mixed choice shows a note that only Traditional Chinese subtitles come out and that it needs the Qwen3 model files, which the 24 GB model set installs. The choice needs those Qwen3 speech engine files and a GPU, because it has no CPU mode. When this PC cannot run it, the choice is greyed out and its text says why, for example that the models are not installed or that this PC runs on the CPU. If a job starts anyway, the window shows the refusal message as it is. The app does not fall back to another engine.

<!-- PLACEHOLDER(P24a): add a Japanese example screenshot here. It needs Japanese material that may be shown publicly, and none is available yet. -->
> Japanese example screenshot: to come. The example must use Japanese material that may be shown publicly, and there is none yet, so there is no picture here.

<!-- PLACEHOLDER(P24b): add a mixed Japanese and English example screenshot here. The talks used in testing are private, and no public material exists yet. -->
> Mixed-language example screenshot: to come. The talks used in testing are private and cannot be shown, and there is no public material yet, so there is no picture here.

**Automatic language guess.** After you pick a video (paste a path, press "Choose file", or add a file in the Add dialog), the app takes 24 pieces of audio of 5 seconds each, spread evenly over the video, in the background and asks Whisper which language each piece is in. This takes about 3 to 5 seconds on an RTX 4090 and does not depend on the length of the video. When nearly every piece is in one language, the "video language" menu is set to it and a line under the toolbar says so, for example "偵測到：日文（信心 100%）" (detected: Japanese, confidence 100%). When the smaller language holds at least 15% of the pieces, the menu is set to the mixed choice. A language you picked yourself is never replaced. When your choice differs from a clear guess, a short hint appears with a button that switches in one click. This is a guess and it can be wrong. For example, a long stretch of English in a Japanese talk can make the app call the talk mixed, and a very short video has too few pieces to say anything. A video with only music or noise gets no guess either, because a piece counts only when a voice detector finds speech in it. Songs with vocals are untested and may be named as a language. When no guess can be made, or it fails or takes too long, the window does nothing and the menu stays as it was. Only English and Japanese are recognized. When this PC cannot process mixed talks, a mixed talk preselects its main language and the line says so. A PC that runs on the CPU makes no guess (each piece takes about 10 seconds). A single file dropped on the window is imported at once with the current choice and is not guessed about.

**Limits:** A Japanese video can produce subtitles and a summary in Traditional Chinese (Taiwan), English, Simplified Chinese and Korean (experimental). A mixed Japanese and English video can only produce Traditional Chinese (Taiwan). Other target languages are not supported yet. The mixed choice needs the Qwen3 model files (installed with the 24 GB model set) and a GPU. You can pick the video language yourself. The app also guesses it once (see above), but the guess can be wrong, and it cannot choose between audio tracks.

### More

- Translation uses a fixed seed. Two cold runs of the same talk gave byte-identical subtitle files.
- Closing the window stops the backend and every speech or language process under it.
- Everything the window does is also available from the command line and a token-guarded local API.

## Demo video

https://github.com/user-attachments/assets/e2ca30a6-9098-4748-a5a7-86c3687cb118

[Download the video](docs/media/demo.mp4). About a minute and a half: import, progress, playback, switching modes, the shortcut list, an edit, a summary chapter jump, a second language and export, then the batch queue, the settings page and the first-run wizard. The progress and the queue run are sped up.

## In development

These are not in the app yet.

- **An installer.** There is no installer and no download, so you build the app from source. See [Install and run from source](#install-and-run-from-source).
- **More target languages for a Japanese video, and any other than Traditional Chinese for a mixed one.** A Japanese video can be translated into four languages (see [Target languages](#target-languages)). A mixed Japanese and English video only into Traditional Chinese (Taiwan).
- **Choosing an audio track.** When a video has several audio tracks, the app uses the first one and you cannot choose.
- **Other source languages.** Only English, Japanese and the mix of the two are supported.
- **Deleting a saved cloud key.** The window can save a key and replace it, but not remove it.

## System requirements

This project is developed and measured on one machine: Windows 11, an NVIDIA RTX 4090 with 24 GB of VRAM, and 64 GB of RAM. Other setups are not tested.

- Windows 64-bit. Windows 11 is the tested system.
- An NVIDIA GPU and a current NVIDIA driver. You do not need to install the CUDA Toolkit.
- The default profile expects at least 16 GB of VRAM. The backend also has an 8 GB profile (from 7 GB of VRAM) and a CPU-only profile. Neither has been run on matching hardware yet.
- Disk for the runtimes and models: about 12 GB for the default profile, which also fetches a fallback speech engine, and about 8 GB for the 8 GB profile. Add room for project folders.
- ffmpeg on `PATH`, or its folder in `VST_FFMPEG_DIR`.

## Install and run from source

**The app is not packaged yet.** There is no installer or download, so you build it yourself. These steps are for developers.

You need Python 3.11 or newer with [uv](https://docs.astral.sh/uv/), Node.js with npm, Rust with the MSVC toolchain (the Tauri 2 prerequisites), and ffmpeg.

```powershell
git clone https://github.com/ANONEKO777/speech-subtitle-ai.git
cd speech-subtitle-ai

uv sync                                   # backend environment, .venv
npm --prefix app ci                       # frontend dependencies
cd app; npx tauri build --no-bundle; cd ..   # builds app/src-tauri/target/release/video-subtitle-translator.exe
```

The speech and language models and their runtimes are not part of the repository. Start `app/src-tauri/target/release/video-subtitle-translator.exe`. When no model is installed, the setup wizard offers to download the ones your hardware needs from their public hosts. That takes a network connection and, for the default profile, about 12 GB of disk. You can skip it and download later from the settings page.

Files land in `%LOCALAPPDATA%\video-subtitle-translator` (set `VST_USER_DATA` to use another folder). The window starts the Python backend from `.venv` and stops it when you close the window.

## Usage

### In the window

1. Paste the full path of a video or press "Choose file", pick English, Japanese or the mixed choice in the "video language" menu beside it, then press "Import". When you pick the video, the app guesses the language once and preselects it (a choice you made yourself is never replaced). The progress screen shows the current step. To process many videos, press "Add", or drop several files on the window, and give each its own language.
2. When it finishes you land in the player. A talk you processed before opens straight in the player, where you left off, and the library tab lists the others.
3. Use the mode switch for the original only, the translation only or both. The size, color and line spacing of the subtitles are in the toolbar.
4. Double-click a subtitle to edit it. Open the summary tab and click a chapter time to jump, and save files from the export menu. Press `?` for every keyboard shortcut.
5. The gear button opens the settings page, for models, the hardware profile and the language model.

The window plays what the system's WebView2 can decode. H.264 with AAC in MP4 is the safe choice. If a video does not play, the window says so and asks for an H.264/AAC MP4 copy.

### From the command line

```powershell
uv run python -m backend.cli talk.mp4 --lang ja
```

This writes `talk.vst\` next to the video with `en.srt`, `ja.srt`, `bilingual.en-ja.ass`, `summary.ja.md` and `project.json`. Running the command again does nothing because every step is cached. `--lang` takes any code from [Target languages](#target-languages), and `--help` lists every option. A project keeps one translation per language.

For a Japanese video use `--source-lang ja`. It translates into Traditional Chinese by default, and `--lang en`, `--lang zh-CN` or `--lang ko` picks another target:

```powershell
uv run python -m backend.cli talk.mp4 --source-lang ja
```

In the project folder the Japanese original is `ja.srt` and the translation is `zh-TW.srt`.

For a talk that mixes Japanese and English use `--source-lang ja+en`. It also translates into Traditional Chinese only, and it needs the Qwen3 model files, which the 24 GB profile installs:

```powershell
uv run python -m backend.cli talk.mp4 --source-lang ja+en
```

In the project folder the original-language subtitles are `src.srt` and the translation is `zh-TW.srt`.

## Privacy

Speech recognition and translation run on your machine by default. The video, the audio and the transcript never leave it, and the local API listens on `127.0.0.1` only, behind a per-run token.

A cloud language model is optional and off by default. If you choose it, the backend refuses to save the setting until you explicitly agree, because the text of your video leaves your PC. The API key is encrypted with Windows DPAPI, can be written but not read back through the API, and does not appear in config files or logs. You choose it on the settings page, where the window asks for your agreement first.

Downloading the models and runtimes is the only time the app needs the network, apart from the optional cloud model.

## Target languages

| Code | Language | Note |
| --- | --- | --- |
| zh-TW | Traditional Chinese (Taiwan) | Default |
| zh-CN | Simplified Chinese | |
| ja | Japanese | |
| ko | Korean | Experimental |
| es | Spanish | |
| fr | French | |
| de | German | |
| pt | Portuguese | |
| it | Italian | |
| ru | Russian | |
| vi | Vietnamese | |
| th | Thai | Experimental |
| id | Indonesian | |

The video language (what the people in the video speak) decides which subtitle languages you can get:

| Video language | Subtitle languages | Note |
| --- | --- | --- |
| English | The thirteen above | Default |
| Japanese | Traditional Chinese (Taiwan), English, Simplified Chinese, Korean | See the table below |
| Japanese and English mixed | Traditional Chinese (Taiwan) | Needs the Qwen3 model files (installed with the 24 GB model set) and a GPU. Other languages are not supported yet |

A Japanese talk can be translated into these languages. A project holds several of them side by side, and adding another one translates the video again without recognizing the speech again.

| Subtitle language for a Japanese talk | Status |
| --- | --- |
| Traditional Chinese (Taiwan) | Supported, the default |
| English | Supported. Translated straight from the Japanese |
| Simplified Chinese | Supported. Translated straight from the Japanese, not through Traditional Chinese |
| Korean | Experimental |
| The other nine languages in the table above | Not in this version |

English and Simplified Chinese were checked automatically and by a blind rating of 12 sentences each. Korean and the other languages are not yet judged. A sentence that fails every check is left empty (English, Simplified Chinese) or shown in English (Korean), and the window marks it.

Quality differs by language. On the 38-minute talk, a back-translation check scored Spanish, Simplified Chinese and German on a par with Traditional Chinese, Japanese a little below, and Korean clearly lower, with wrong names and meanings in some lines. Korean and Thai are marked experimental for that reason. Of the thirteen, six were run end to end on a real talk (zh-TW, zh-CN, ja, ko, es, de). The others are covered by tests only.

## Media credits

The screenshots and the demo video were made with a clip of the NASA "State of NASA" address by NASA Administrator Bill Nelson, 9 March 2023 ([NASA Image and Video Library](https://images.nasa.gov/details/2023%20%E2%80%98State%20of%20NASA%E2%80%99%20Address%20from%20Administrator%20Bill%20Nelson)). The clip runs from 1:14 to 7:07 of the original. NASA media is generally not subject to copyright in the United States, [NASA's media usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/) apply, and NASA does not endorse this project. The clip itself is not in this repository. The subtitles and the summary in the images were produced by this app.

## License

[GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later). Third-party notices are in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
