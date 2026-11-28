# Third-party components

Video Subtitle Translator is free software under the GNU Affero General Public License, version 3 or later (AGPL-3.0-or-later). The full text is in `LICENSE` in the install folder.

**Source code of this application:** https://github.com/ANONEKO777/speech-subtitle-ai

If you use a modified copy of this program over a network, AGPL section 13 requires you to offer its users the source of your modified version.

The installer holds the app shell, the front end, the backend (a PyInstaller build of the Python code), and FFmpeg. It holds no model files and no NVIDIA files. The app downloads models and speech and language runtimes after install, from the sources listed below, into the folder shown on its settings page.

## FFmpeg (LGPL-3.0-or-later), bundled

The `ffmpeg` folder in the install folder holds FFmpeg 8.1.3 as separate programs and shared libraries (`ffmpeg.exe`, `ffprobe.exe`, `avcodec-62.dll`, `avdevice-62.dll`, `avfilter-11.dll`, `avformat-62.dll`, `avutil-60.dll`, `swresample-6.dll`, `swscale-9.dll`). The app starts them as separate processes and does not link them.

- Copyright (c) the FFmpeg developers. Licensed under the GNU Lesser General Public License, version 3 or later. The text is in `ffmpeg/LICENSE-FFmpeg-LGPL-3.0.txt`.
- This is the LGPL build. Its configure line has `--enable-version3` and `--disable-libx264 --disable-libx265`, and has neither `--enable-gpl` nor `--enable-nonfree`. `installer/build.ps1` refuses to build if that changes. Because x264 is not in it, burned-in video uses the H.264 encoder that comes with Windows.
- Build: BtbN/FFmpeg-Builds, release `autobuild-2026-10-31-12-59`, file `ffmpeg-n8.1.3-27-g8dca1586f4-win64-lgpl-shared-8.1.zip`, SHA-256 `5cef7bc48e513f3cee7c881e8b2999d835541edb1846c3e89443a67f8f8556ab` (the same hash GitHub shows for that release asset). The FFmpeg commit is `8dca1586f468bfcbb78ae3ed618af1361d9f140a`, on FFmpeg's `release/8.1` branch, 27 commits after the tag n8.1.3. BtbN keeps its month-end builds and removes most daily ones after a few weeks. `installer/ffmpeg.json` holds the pin, `installer/build.ps1` checks the hash, and a copy can be kept in this repository's releases (`installer/mirror_ffmpeg.ps1`).
- **Source offer.** The FFmpeg source for this build is the commit `8dca1586f468bfcbb78ae3ed618af1361d9f140a`, at https://github.com/FFmpeg/FFmpeg/tree/8dca1586f468bfcbb78ae3ed618af1361d9f140a, built with the scripts at https://github.com/BtbN/FFmpeg-Builds (tag `autobuild-2026-10-31-12-59`). The libraries it was built with, and their licenses, are listed in the BtbN repository. On request to the project address above we will send the corresponding source for three years after the version's release.
- The build links many external libraries (libass, FreeType, HarfBuzz, dav1d, libvpx, Opus, LAME and others). Their license texts are in `ffmpeg/FFmpeg-external-libraries.txt`, collected by `installer/fetch_ffmpeg_licenses.py` from each project's upstream.
- You may replace the files in `ffmpeg` with your own build of FFmpeg that has the same names. Set `VST_FFMPEG_DIR` to use a copy elsewhere.

## Python backend (inside `backend/`)

Python 3.11 (PSF License), FastAPI and Starlette (MIT, BSD-3-Clause), Uvicorn (BSD-3-Clause), Pydantic (MIT), NumPy (BSD-3-Clause, with its bundled libraries), ONNX Runtime CPU (MIT), PyInstaller bootloader (GPL-2.0-or-later with the PyInstaller bootloader exception, which permits this use). No PyTorch and no CUDA files are in it.

## App shell and front end

Tauri 2 and its plugins (MIT or Apache-2.0), WebView2 bootstrapper (Microsoft, runs only if WebView2 is missing), React (MIT), Lucide icons (ISC, Feather part MIT). The icon notices are in `THIRD-PARTY-NOTICES.md`.

## Downloaded after install (not in the installer)

Each row is in `backend/manager/registry.json` with its pinned address, size and SHA-256. The settings page lists the same.

| Item | Version | License | Source |
|---|---|---|---|
| Whisper large-v3-turbo (ggml) | whisper.cpp model repo commit `5359861c739e955e79d9a303bcbc70fb988958b1` | MIT | https://huggingface.co/ggerganov/whisper.cpp |
| Qwen3-ASR 1.7B, GGUF q8_0 (cstr) | commit `674df5d44b50a63e7102a18895ed20e3f91de301`, SHA-256 `9851ab996591a2d0cb0efb216002764b509c86bd40c95e613d7b65b8e69c8a6e` | Apache-2.0 | https://huggingface.co/cstr/qwen3-asr-1.7b-GGUF |
| Qwen3-ForcedAligner 0.6B, GGUF q8_0 (cstr) | commit `1ec5110602ccab18c878ddebedab0891e290a95c`, SHA-256 `539df5dd0fe1721e378ac13bfac9a26b1260dafb62d892c518c1f21244762636` | Apache-2.0 | https://huggingface.co/cstr/qwen3-forced-aligner-0.6b-GGUF |
| Silero VAD (ggml and ONNX) | v6.2.0 and v6.2.3 | MIT | https://github.com/snakers4/silero-vad |
| Qwen3-8B, GGUF Q4_K_M | commit `7c41481f57cb95916b40956ab2f0b139b296d974` | Apache-2.0 | https://huggingface.co/Qwen/Qwen3-8B-GGUF |
| whisper.cpp runtimes (CPU and CUDA 12.4) | b5454 | MIT, Zlib; CUDA build also NVIDIA CUDA EULA | https://github.com/ggml-org/whisper.cpp |
| llama.cpp runtimes (CPU and CUDA 12.4) | b12068 | MIT, Apache-2.0 with LLVM exception | https://github.com/ggml-org/llama.cpp |
| CrispASR runtime (CUDA) | v0.8.49 | MIT, BSD-3-Clause, Apache-2.0, MIT-0; also NVIDIA CUDA EULA | https://github.com/CrispStrobe/CrispASR |
| NVIDIA CUDA runtime DLLs for llama.cpp | cudart-llama b12068 | NVIDIA CUDA EULA | https://github.com/ggml-org/llama.cpp |

**The cstr GGUF files.** The two GGUF files are quantized conversions of Qwen's Qwen3-ASR-1.7B and Qwen3-ForcedAligner-0.6B (Apache-2.0). The conversions carry no license file of their own. Their Hugging Face model cards declare `license: apache-2.0` at the commit above, which matches the base models. We record the source by that commit and by file SHA-256, so a later change to the repository cannot change what the app downloads.

**whisper.cpp.** The b5454 release zip has no LICENSE file. The project's MIT license, from tag b5454, is `licenses/LICENSE-whisper.cpp.txt` in the install folder (Copyright (c) 2023-2026 The ggml authors). The CrispASR zip carries its own `LICENSE` and `THIRD_PARTY_NOTICES.txt`.

## NVIDIA CUDA files in the runtime zips

Three runtime zips (whisper.cpp CUDA, CrispASR CUDA, and the llama.cpp cudart zip) contain NVIDIA CUDA DLLs. The installer does not contain them, and this project does not host them. The app downloads each zip from the upstream release, checks its SHA-256, and unpacks it on the user's machine. The files below were audited against Attachment A of the NVIDIA CUDA EULA ("CUDA Toolkit Supplement to Software License Agreement for NVIDIA Software Development Kits", https://docs.nvidia.com/cuda/eula/index.html, the version published 2026-01-26, and the CUDA 12.4 archive page https://docs.nvidia.com/cuda/archive/12.4.0/eula/index.html, whose Attachment A lists the same files). Attachment A lists redistributable files and says variants with version or architecture in the file name are covered.

| File | Zips | Version | Attachment A entry | Redistributable |
|---|---|---|---|---|
| `cudart64_12.dll` | whisper.cpp, llama.cpp cudart | CUDA 12.4.127 | CUDA Runtime: `cudart.dll` | Yes |
| `cudart64_12.dll` | CrispASR | CUDA 12.8.57 | CUDA Runtime: `cudart.dll` | Yes |
| `cublas64_12.dll` | whisper.cpp, llama.cpp cudart | 12.4 (6.14.11.1245) | cuBLAS: `cublas.dll` | Yes |
| `cublas64_12.dll` | CrispASR | 12.8 (6.14.11.1283) | cuBLAS: `cublas.dll` | Yes |
| `cublasLt64_12.dll` | whisper.cpp, llama.cpp cudart | 12.4 | cuBLAS: `cublasLt.dll` | Yes |
| `cublasLt64_12.dll` | CrispASR | 12.8 | cuBLAS: `cublasLt.dll` | Yes |
| `nvblas64_12.dll` | whisper.cpp | 12.4 | nvBLAS: `nvblas.dll` | Yes |
| `nvrtc64_120_0.dll` | whisper.cpp | 12.4.127 | NVRTC: `nvrtc.dll` | Yes |
| `nvrtc-builtins64_124.dll` | whisper.cpp | 12.4 | NVRTC: `nvrtc-builtins.dll` | Yes |

SHA-256 of each file, from zips whose hashes match `registry.json`:

- whisper.cpp b5454 CUDA zip: `cudart64_12.dll` d28e42265da7462162a54da6b7a99ea4fa2caf8139d862bb500db875d0b32dfc, `cublas64_12.dll` e40202fe4223c1cd2d2dce7beec59e1ed61c7801bd827309183be9b50e358f4c, `cublasLt64_12.dll` 2a896460bef60ed57ef32b0875812f355a6984e671d638bb632f5e8c1d7a831f, `nvblas64_12.dll` e42a77405e6e4b1cc661dcfcddead35ec62dcf59c6f9be1a3b5fab73d1f4c616, `nvrtc64_120_0.dll` 3aa3cd8aa10437e212760c0e1ed730807811ec3bc330216dbfde4b26211d2243, `nvrtc-builtins64_124.dll` 79888dba26c51475ea21fc7b47d2b9dd5b1ffaecc8e5ea22a49fa5f5a722eb43.
- CrispASR v0.8.49 CUDA zip: `cudart64_12.dll` 9d9b868955149875ac4ef43442aaaa8913d4a7b3e4d6dd60ee871626aa045768, `cublas64_12.dll` 0a60a7ecbf906f7f3842826fecaf412f1587ff6269729339245a1ec224364161, `cublasLt64_12.dll` a21ddfc1c9cd090ab07d2c6aad235aa4f15fe60fe896d5db28adf7a279c09ef3.
- llama.cpp b12068 cudart zip: the same three 12.4 files as the whisper.cpp zip (`cublas64_12.dll`, `cublasLt64_12.dll`, `cudart64_12.dll`, same sizes). The llama.cpp CUDA zip itself holds only `ggml-cuda.dll` (MIT) and no NVIDIA runtime.

Every NVIDIA file found is on the Attachment A list. The upstream projects ship them inside an application with its own functionality, and the files are used only by that application, as section 1.1.2 requires. These files stay under the NVIDIA license, not MIT. They run only on systems with an NVIDIA GPU. Do not extract them from the runtimes folder for use in another program. The audit was of the zips as published. If a runtime is updated in `registry.json`, audit its zip again.
