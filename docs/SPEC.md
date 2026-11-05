# video-subtitle-translator — 技術規格（給開發 Agent）

> 文件日期：2026-11-03。ASR 排行榜與各專案狀態變動很快。M0 的實測結論在 §2 與 `docs/m0-report.md`，標明「仍未證明」的項目不要直接假設可用。

## 1. 專案目標

桌面應用程式，讓使用者對**沒有字幕的英文演講影片**：

1. 自動語音辨識（STT），產生帶時間軸的英文字幕。
2. 翻譯成**繁體中文（台灣用語）**，產生中英雙語字幕。
3. 內建播放器，在影片**下方**顯示中英字幕（不燒進影片，字幕為獨立檔案）。
4. 用本地 LLM（或可選的雲端 API）產生重點整理。
5. 可打包成安裝程式給他人安裝。CUDA 執行環境與模型**不放進安裝包**，由程式內介面另外下載。

### 非目標（第一版不做）
- 即時（直播）字幕。
- 影片剪輯、配音（TTS）。
- 多人帳號、雲端同步。

## 2. 已確認的事實與 M0 實測結論

### 已由資料確認
- Whisper 已非榜首。Hugging Face Open ASR Leaderboard（2026-10）上，Qwen3-ASR-1.7B 為開源英文平均 WER 約 5.40%，Apache 2.0；Whisper large-v3 約 7.1–7.6%。
- **Qwen3-ASR 本身不輸出字詞時間戳**，需另用 `Qwen3-ForcedAligner-0.6B` 對齊。
- **Parakeet TDT 0.6B v3 只支援 25 種歐洲語言，不含中文**；v2 為英文專用。兩者有字詞/段落時間戳。本專案輸入是英文，所以可用。授權 CC-BY-4.0（需標註）。
- **Cohere Transcribe 無時間戳**，不適合做字幕。
- **Nemotron 3.5 Transcribe**（NVIDIA，2026-10-28）有字詞時間戳與翻譯，但為 34B 參數 MoE，官方 FP8 部署建議 96 GB 顯存級顯卡，一般使用者跑不動，列為「選配/未來」。
- **whisper.cpp 官方不支援 Qwen3-ASR**（架構不同）。Qwen3-ASR 有社群 C++/ggml 方案：CrispASR、audio.cpp（皆有 GGUF、CUDA/Metal/Vulkan）。
- 使用者**不需要安裝 CUDA Toolkit**，只需 NVIDIA 驅動；PyTorch / ONNX Runtime GPU 版自帶所需 CUDA 函式庫。

### M0 實測結論（2026-11-03，詳見 `docs/m0-report.md`）
- **CrispASR 對 Qwen3-ASR-1.7B 可用。** CrispASR v0.8.49 有官方 Windows CUDA 版，搭配 `cstr/qwen3-asr-1.7b-GGUF` 與 `cstr/qwen3-forced-aligner-0.6b-GGUF`（q8_0），兩支演講（38 與 57 分鐘）都跑完，沒有中斷，時間軸單調遞增。RTF 約 0.042，顯存約 7.3 GB（扣除其他程式）。
- **對齊準確度。** 以「安靜後開始說話」的時間點為準，CrispASR 加 ForcedAligner 的字詞起點誤差中位數 0.04 s，82% 到 91% 在 0.5 s 內。whisper.cpp 預設 token 時間中位數 0.12 到 0.14 s，87% 到 90% 在 0.5 s 內。中位數 CrispASR 較準，但這來自切塊內的字（aligner），每個 VAD 切塊的第一個字約晚 0.36 s。尾端兩者互有勝負。whisper.cpp 開 `-nfa -dtw large.v3.turbo` 後字詞時間和 aligner 有 97% 在 0.5 s 內，但整體晚約 0.2 s。
- **授權與維護。** CrispASR 與 whisper.cpp 的程式都是 MIT，Qwen3 權重是 Apache-2.0。兩個 Windows zip 都附 NVIDIA CUDA DLL，屬 NVIDIA CUDA EULA，打包時要另外確認可否再散布。CrispASR 有 GitHub release。CrispASR v0.8.49 打不開含非 ASCII 字元（例如中文檔名）的輸入檔路徑，這點有實測證明；執行檔、模型、輸出目錄的路徑沒有試過，但保險起見也只傳 ASCII。傳給它的輸入檔必須先轉成 ASCII 路徑。兩者都能以子行程執行，輸出 JSON 與 SRT；CrispASR 加 `--strict-pipeline` 時，VAD 或對齊失敗會回傳非零結束碼。
- **whisper.cpp large-v3-turbo 對照。** 6 段抽樣共 12 分鐘，讀上下文判定的錯字 whisper.cpp 10 個（3 個只是拼法）、CrispASR 8 個，會改變內容的錯 7 比 8，差異不明顯。whisper.cpp 有一處把 `can't` 聽成 `can`，意思相反。whisper.cpp RTF 約 0.018（CPU 忙時到 0.038），快 1.1 到 2.4 倍，顯存約 2.3 GB。CrispASR 會在每個 VAD 切塊邊界把句子切斷（6 段共 18 處）。整檔執行的 whisper.cpp 沒有，但跑在相同切塊上時 5 處邊界有 2 處加句號（不加大寫）。兩者都需要修補切塊邊界的標點。
- **仍未證明。** 錯字數沒有人工聽寫對照。audio.cpp、Qwen3-ASR 的 f16 與 q4_k 沒有測。whisper.cpp 在 15 秒的 LibriVox 測試音檔上漏了頭尾兩句，但在 25 秒演講片段與真實 VAD 切塊上沒有重現。P04 用演講切塊測頭尾漏字。8 GB 顯卡能否跑 CrispASR 由 P11 驗證。

## 3. 技術選型（已決定：Tauri 2 + Python）

| 層 | 選擇 | 已否決/備援 |
|---|---|---|
| 桌面外殼 | Tauri 2 | Electron（已否決，僅作備援） |
| 前端 | TypeScript + React（或 Svelte），HTML5 video | libmpv（HTML5 播不動的格式） |
| 後端 | Python 3.11+ / FastAPI，本機 127.0.0.1 服務，以 sidecar 啟動 | — |
| ASR 引擎 | 抽象介面 + 多實作（見 §6） | — |
| 翻譯/摘要 LLM | OpenAI 相容 API；本地用 llama.cpp `llama-server` 或使用者的 Ollama；可選雲端金鑰 | — |
| 媒體處理 | FFmpeg（LGPL 版，隨安裝包附上） | — |
| VAD | silero-vad（ONNX） | webrtcvad |
| 後端打包 | PyInstaller 或 Nuitka | — |

> 已決定（2026-11-03）：主要開發目標為 **Windows + NVIDIA**，保留 macOS（Metal）路徑。技術棧為 Tauri 2 + Python。詳見 §17。

## 4. 目錄結構

```
video-subtitle-translator/
├─ app/                    # Tauri 外殼 + 前端
│  ├─ src/                 # UI：匯入、進度、播放器、摘要頁、設定、模型管理
│  └─ src-tauri/
├─ backend/
│  ├─ main.py              # FastAPI 入口
│  ├─ api/                 # 路由：projects, jobs, models, runtimes, settings
│  ├─ core/
│  │  ├─ pipeline.py       # 流程編排
│  │  ├─ audio.py          # ffmpeg 抽音訊、重採樣 16 kHz mono
│  │  ├─ vad.py            # 語音分段
│  │  ├─ segmenter.py      # 斷句與字幕行切分
│  │  ├─ translate.py      # LLM 翻譯
│  │  ├─ summarize.py      # LLM 摘要（map-reduce）
│  │  └─ subtitle_io.py    # SRT / VTT / ASS / project.json 讀寫
│  ├─ engines/
│  │  ├─ base.py           # ASREngine 抽象類別
│  │  ├─ whispercpp.py
│  │  ├─ crispasr.py       # Qwen3-ASR 等（M0 實測可用，備援引擎）
│  │  └─ nemo_parakeet.py  # 選配
│  ├─ llm/
│  │  ├─ client.py         # OpenAI 相容客戶端
│  │  └─ local_server.py   # 啟動/停止 llama-server
│  └─ manager/
│     ├─ hardware.py       # GPU/CPU/RAM 偵測
│     ├─ runtimes.py       # 執行環境包下載與安裝
│     ├─ models.py         # 模型下載、校驗、刪除
│     └─ registry.json     # 模型與執行環境清單
├─ installer/              # 打包、簽章、更新設定
├─ tests/
│  ├─ fixtures/            # 短測試音檔（自製或公有領域）
│  └─ ...
└─ docs/
   └─ SPEC.md              # 本文件
```

## 5. 處理流程（Pipeline）

```
影片/音訊
  → [1] ffmpeg 抽音訊 (16 kHz, mono, wav)
  → [2] VAD 分段（約 20–30 秒，邊界落在靜音處，段間重疊 0.5 s 以內）
  → [3] ASR 辨識 → 原文文字 + 時間戳
  → [4] 斷句 / 字幕行切分（見 §5.1）
  → [5] 翻譯成繁體中文（見 §8）
  → [6] 輸出：en.srt、zh-TW.srt、bilingual.ass/vtt、project.json
  → [7] 摘要（獨立步驟，可延後或重跑）→ summary.md
```

每一步結果要**快取到專案資料夾**，失敗或換模型時只重跑受影響的步驟。進度以 job 事件（SSE/WebSocket）推送給前端。

### 5.1 字幕規則
- 取得時間戳的方式：
  - 引擎本身有字詞時間戳（whisper.cpp、Parakeet）→ 直接使用。
  - 引擎無時間戳（Qwen3-ASR）→ 用 Qwen3-ForcedAligner 對齊文字與音訊。
- 英文每行 ≤ 42 字元，最多 2 行；中文每行 ≤ 20 字，最多 2 行。
- 單條字幕長度 1–7 秒；優先在標點、停頓處斷開。
- 相鄰字幕不重疊；最小間隔 ≥ 80 ms。
- 翻譯後的中文沿用原英文條目的時間軸（一對一），不要自行重切時間。

## 6. ASR 引擎抽象

```python
class ASREngine(Protocol):
    id: str                        # "whispercpp-large-v3-turbo", "crispasr-qwen3-asr-1.7b"
    supports_word_timestamps: bool
    def is_available(self) -> bool: ...
    def transcribe(self, wav_path: str, language: str = "en",
                   progress_cb=None) -> list[Segment]: ...

@dataclass
class Word:    text: str; start: float; end: float
@dataclass
class Segment: text: str; start: float; end: float; words: list[Word] | None
```

引擎以**子行程**方式呼叫（whisper.cpp / CrispASR 的 CLI 或本機 server），用 JSON 或 SRT 輸出解析，避免把原生函式庫載進主程序。

| 引擎 | 角色 | 狀態 |
|---|---|---|
| `whispercpp` (large-v3-turbo) | **預設** | M0 選定：速度、顯存、段落形狀最好，錯字數與 Qwen3 相當 |
| `crispasr` (Qwen3-ASR-1.7B + ForcedAligner) | **備援** | M0 實測可用：57 分鐘不中斷，切塊內的字詞起點誤差中位數較小（尾端互有勝負，切塊第一個字約晚 0.36 s），但較慢、較耗顯存，會在 VAD 切塊處斷句，且路徑必須是 ASCII |
| `nemo_parakeet` (TDT 0.6B v2/v3) | 英文高速選項（需 PyTorch/NeMo 或 ONNX 版） | 選配 |
| Nemotron 3.5 Transcribe | 高階顯卡選項 | 未來 |

## 7. 執行環境與模型管理（不放進安裝包）

### 7.1 安裝包內容（盡量小）
Tauri 外殼、前端、後端 sidecar（不含 PyTorch/CUDA）、FFmpeg、`registry.json`。

### 7.2 首次啟動精靈
1. `hardware.py` 偵測：NVIDIA GPU（pynvml / nvidia-smi：型號、顯存、驅動版本）、Apple Silicon、RAM、磁碟空間。
2. 若 NVIDIA 驅動版本過舊，提示更新驅動（**不要**要求安裝 CUDA Toolkit）。
3. 依硬體建議「執行環境包」與「模型」，使用者確認後下載。
4. 下載後做自檢（跑一段 5 秒測試音檔），失敗要有可讀的錯誤與重試/回退（例如 GPU 失敗 → CPU）。

### 7.3 執行環境包
- 以 ggml/C++ 引擎為主時：下載對應平台與後端（CUDA / Vulkan / Metal / CPU）的預編譯執行檔包，解壓到使用者資料夾。
- 若使用 Python/PyTorch 引擎（選配）：在使用者資料夾建立獨立 venv，依硬體安裝對應 wheel。
- 執行檔與模型皆需**版本號 + SHA256**，記錄在 `registry.json`。

### 7.4 `registry.json` 欄位範例
```json
{
  "models": [{
    "id": "qwen3-asr-1.7b-q8_0",
    "kind": "asr",
    "engine": "crispasr",
    "source": "huggingface",
    "repo": "<repo_id>", "file": "<filename>.gguf",
    "sha256": "<hash>", "size_bytes": 0,
    "min_vram_gb": 4, "languages": ["en", "zh"],
    "license": "Apache-2.0", "needs": ["qwen3-forced-aligner-0.6b"]
  }],
  "runtimes": [{
    "id": "crispasr-win-cuda12", "platform": "win-x64", "backend": "cuda",
    "url": "<url>", "sha256": "<hash>", "version": "<ver>"
  }]
}
```
實際 repo、檔名、雜湊在 M0 / M4 取得後填入，**不要憑記憶填**。

### 7.5 下載器需求
斷點續傳、進度與速度顯示、SHA256 驗證、可取消、磁碟空間預檢、可自訂模型存放路徑、可設定鏡像來源。

## 8. LLM：翻譯與摘要

### 8.1 連線
一律走 OpenAI 相容介面（`base_url`, `api_key`, `model`）。三種來源：內建管理的 `llama-server`（使用者下載 GGUF）、使用者既有的 Ollama、雲端 API 金鑰。設定頁允許填寫並測試連線。

### 8.2 翻譯
- 輸入：字幕條目批次（建議 20–40 條）+ 前後各 5 條上下文。
- 要求輸出：**嚴格 JSON**（`[{"id": n, "zh": "..."}]`），條目數必須與輸入一致；解析失敗或條數不符 → 自動重試，最多 3 次，仍失敗則該批降為較小批次。
- System prompt 要點：翻成**繁體中文（台灣慣用語）**；口語化但準確；保留專有名詞（可附原文）；不增刪資訊；不合併/拆分條目。
- 支援**術語表**（使用者可預填人名、產品名、專有名詞）並注入 prompt。
- 可選：先用 LLM 從全文抽取專有名詞再翻譯，以保持前後一致。

### 8.3 摘要（map-reduce）
1. 依時間將逐字稿切成章節片段（約 2,000–4,000 tokens，片段間少量重疊）。
2. Map：每段產出要點與時間範圍。
3. Reduce：合併成 `summary.md`，包含：一句話總結、3–7 個主題章節（附起始時間戳，可點擊跳轉）、關鍵觀點條列、可行動的結論/金句（若有）。
4. 輸出語言預設繁體中文；可選同時輸出英文版。
- 長影片不可整份塞入單次請求（小模型會遺漏前段）。

## 9. 後端 API（草案）

```
GET  /api/health
GET  /api/hardware
GET  /api/registry                       # 可用模型與環境
POST /api/runtimes/{id}/install          # 觸發下載（job）
POST /api/models/{id}/download
DELETE /api/models/{id}
POST /api/projects                       # body: {video_path}
GET  /api/projects/{id}                  # 狀態、檔案路徑、設定
POST /api/projects/{id}/jobs             # body: {engine, llm, llm_model, cpu, glossary, summary_en, batch_size}；步驟一律全跑，輸入沒變的自動跳過；同專案已有未完成 job 回 409
GET  /api/jobs/{id}/events               # SSE 進度
GET  /api/jobs/{id}                       # job 狀態與總進度
POST /api/jobs/{id}/cancel
GET  /api/projects/{id}/subtitles?lang=en|zh|bilingual&format=srt|vtt|ass|json
PUT  /api/projects/{id}/subtitles        # 使用者手動校對後存回
GET  /api/projects/{id}/summary?lang=zh-TW|en
```
後端只監聽 `127.0.0.1`，啟動時隨機連接埠並以一次性 token 驗證，避免被其他本機程序或網頁呼叫。啟動後 stdout 印出 `READY port=<n> token=<t>`；每個請求（含下載路由）都要 `Authorization: Bearer <token>`，並檢查 `Host` 與 `Origin`；SSE 可改用 `?token=`。事件為 `status`、`progress`，最後一則是 `done`、`failed` 或 `cancelled`。

## 10. 前端 / 播放器

- 影片區 + **其下方**的字幕區（不疊在畫面上）；可切換：僅英文 / 僅中文 / 雙語（中上英下或相反，可設定）。
- 字幕大小、顏色、行距可調。
- 字幕清單面板：點擊條目跳轉；播放時自動捲動；可雙擊編輯文字與時間（編輯後寫回 `project.json`）。
- 摘要頁：章節時間戳可跳轉到影片位置。
- 格式相容：HTML5 video 播不動（如 MKV、HEVC）時，背景用 ffmpeg 產生 H.264/AAC 的 proxy mp4；或改用 libmpv。
- 匯出：SRT（英、中、雙語）、ASS（雙語）、VTT、`summary.md`；可選「燒錄成新影片」（非預設）。

## 11. 專案資料格式

每個專案一個資料夾，內含：
```
project.json        # 影片路徑、引擎/模型版本、設定、各步驟狀態與時間
audio.wav           # 快取
segments.json       # ASR 原始結果（含字詞時間戳）
subs.en.json / subs.zh-TW.json   # 內部字幕表示
en.srt / zh-TW.srt / bilingual.ass / bilingual.vtt
summary.md
```
`project.json` 要有 `schema_version`，之後升級可遷移。

## 12. 打包與發佈

- Windows：Tauri 產生 NSIS/MSI；建議程式碼簽章（否則 SmartScreen 警告）。
- macOS：.dmg；需 Apple Developer 帳號做簽章與公證。
- Linux：AppImage。
- 後端 sidecar 用 PyInstaller/Nuitka 打包成單一執行檔，隨 Tauri 一起封裝。
- 自動更新：Tauri updater。**模型與執行環境版本與應用程式版本分離**，由 `registry.json` 控制，可獨立更新。
- 測試必須在**乾淨的虛擬機/新使用者帳號**上跑完整安裝 → 首次啟動 → 下載 → 處理一支影片。

## 13. 授權與合規

- 本專案採用 **AGPL-3.0-or-later**（與 `pyproject.toml` 一致；完整授權文字在 repo 根目錄的 `LICENSE`）。
- GPLv3 專案（如 VideoCaptioner、KrillinAI/OpenCreator）的程式碼可以併入本專案：GPLv3 與 AGPLv3 的第 13 條允許兩者結合。被複製的 GPLv3 部分仍維持 GPLv3，結合後的整體只多適用 AGPLv3 第 13 條（網路互動時須向網路使用者提供原始碼）。複製的檔案必須同時保留原作者的版權聲明與 GPLv3 授權聲明。複製前必須先查證該專案確切的授權：授權為 GPLv2-only 者不相容，不得複製；帶有額外條款或例外者也不得複製；GPLv3-only 可以。
- 授權不明或與 AGPL-3.0 不相容的程式碼不得複製，只能參考設計。
- FFmpeg 使用 LGPL 建置，並遵守其散佈條款（附授權聲明、提供對應原始碼取得方式）。
- 模型授權記錄在 `registry.json` 的 `license` 欄位；介面提供「第三方授權」頁。Parakeet（CC-BY-4.0）需標註出處。
- 使用者下載模型時，顯示授權名稱與連結。若模型需同意條款（gated），要引導使用者到來源頁處理。

## 14. 里程碑與驗收標準

**M0 — 技術驗證（必做，先於其他）**
- 以一支真實英文演講（20–40 分鐘）分別跑 whisper.cpp large-v3-turbo 與 CrispASR/audio.cpp 的 Qwen3-ASR-1.7B（含 ForcedAligner）。
- 產出比較報告：錯字（人工抽樣 3 個 2 分鐘片段）、處理速度、顯存/記憶體、時間軸誤差、長音訊是否穩定。
- 驗收：確定預設引擎與備援引擎；更新本文件 §2、§6。

**M1 — 命令列版核心流程**
- `python -m backend.cli input.mp4 --engine ... --llm ...` 可產出 en.srt、zh-TW.srt、bilingual.ass、summary.md。
- 驗收：測試影片的字幕可被 VLC/mpv 正常載入；條目數一致；無時間重疊。

**M2 — 後端服務 + 簡易播放器**
- FastAPI + 進度事件；前端可匯入影片、看進度、在影片下方顯示雙語字幕、點擊跳轉。

**M3 — 摘要與字幕編輯**
- map-reduce 摘要、章節時間戳跳轉；字幕手動編輯並存檔。

**M4 — 硬體偵測、執行環境與模型管理**
- 首次啟動精靈、下載器（續傳/校驗）、GPU 失敗回退 CPU。

**M5 — 打包與乾淨機測試**
- 三平台（至少 Windows）安裝程式；安裝包不含 CUDA 與模型；乾淨機端到端通過。

## 15. 測試要求

- 單元測試：`segmenter`（斷句規則）、`subtitle_io`（SRT/ASS 往返）、翻譯 JSON 解析與重試、下載器校驗。
- 整合測試：用 10–20 秒的測試音檔跑完整 pipeline（可用最小模型）。
- 回歸：保留一組「黃金樣本」的字幕輸出，改動引擎或斷句後比對差異。
- 不提交大型模型與版權影片到儲存庫。

## 16. 風險與注意事項

- **ASR 時間軸漂移**：長音訊分段要有重疊與去重邏輯；對齊後做單調性檢查。
- **LLM 翻譯輸出不穩**：務必驗證 JSON 與條數，不可信任單次輸出。
- **小模型摘要品質有限**：提供雲端 API 選項，並在介面說明差異。
- **榜單不等於實際效果**：以自有樣本驗證為準。
- **第三方社群專案可能停止維護**：引擎走抽象介面，且至少保留一個成熟備援（whisper.cpp）。
- **安全**：本機服務只綁 127.0.0.1 並驗證 token；不要把使用者影片路徑或內容傳到外部（除非使用者啟用雲端 LLM，並在介面明確告知）。

## 17. 已決定事項

操作者於 2026-11-03 決定：

1. 目標平台：先以 **Windows + NVIDIA** 為主，保留 macOS（Metal）路徑。
2. 技術棧：**Tauri 2 + Python**（FastAPI 後端以 sidecar 啟動）。
3. 硬體設定：預設以 **24 GB 顯存（RTX 4090）** 為準。程式內另外提供兩組設定：8 GB 顯卡，以及只有 CPU 加內顯。
4. 授權：**AGPL-3.0-or-later**，本專案開源。GPLv3 程式碼可依兩份授權的第 13 條結合：被複製的部分仍屬 GPLv3，整體只多適用 AGPLv3 第 13 條，且須保留原版權聲明與 GPLv3 授權聲明。複製前要逐一查證來源專案的確切授權：GPLv2-only 不相容，有額外條款或例外者不得複製，GPLv3-only 可以。
