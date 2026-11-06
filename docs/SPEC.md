# video-subtitle-translator — 技術規格（給開發 Agent）

> 文件日期：2026-11-03。ASR 排行榜與各專案狀態變動很快。M0 的實測結論在 §2 與 `docs/m0-report.md`，標明「仍未證明」的項目不要直接假設可用。

## 1. 專案目標

桌面應用程式，讓使用者對**沒有字幕的英文演講影片**：

1. 自動語音辨識（STT），產生帶時間軸的英文字幕。
2. 翻譯成使用者選的目標語言（預設**繁體中文（台灣用語）**，另支援 12 種，見 §8.4），產生雙語字幕。
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
  → [5] 翻譯成目標語言（見 §8）
  → [6] 輸出：en.srt、<語言>.srt（繁中為 zh-TW.srt）、bilingual.ass/vtt、project.json
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
- 要求輸出：**嚴格 JSON**（`[{"id": n, "zh": "..."}]`；`zh` 是中文目標語言的欄位名，其他語言用 `text`），條目數必須與輸入一致；解析失敗或條數不符 → 自動重試，最多 3 次，仍失敗則該批降為較小批次。
- System prompt 要點：翻成目標語言（預設**繁體中文（台灣慣用語）**）；口語化但準確；保留專有名詞（可附原文）；不增刪資訊；不合併/拆分條目。
- 支援**術語表**（使用者可預填人名、產品名、專有名詞）並注入 prompt。「保留英文」的術語對所有目標語言一律生效。
- **可重現**：每個請求都帶固定的 `seed`，第一次嘗試溫度為 0，重試才用 0.3。
- 口頭禪：英文那一條是被逗號隔開、不是問句的 "you know" 時，譯文中單獨成句的「你知道」「你知」「你知不知道」會被刪除，真正的 "do you know" 保留。
- 可選：先用 LLM 從全文抽取專有名詞再翻譯，以保持前後一致。

### 8.3 摘要（map-reduce）
1. 依時間將逐字稿切成章節片段（約 2,000–4,000 tokens，片段間少量重疊）。
2. Map：每段產出要點與時間範圍。
3. Reduce：合併成 `summary.md`，包含：一句話總結、3–7 個主題章節（附起始時間戳，可點擊跳轉）、關鍵觀點條列、可行動的結論/金句（若有）。
4. 輸出語言為目標語言（預設繁體中文）；可選同時輸出英文版。
- 長影片不可整份塞入單次請求（小模型會遺漏前段）。

### 8.4 目標語言（多國語系）
- 目標語言是型別化的登錄表（`backend/core/languages.py`），每筆有：代碼、英文名、母語名、檔名代碼、文字系統檢查、提示詞片段、後處理、摘要標題、ASS 折行規則（`wrap`）與品質標籤（`quality`）。支援 13 種：`zh-TW`（預設）、`zh-CN`、`ja`、`ko`、`es`、`fr`、`de`、`pt`、`it`、`ru`、`vi`、`th`、`id`。
- 後處理：台灣用語替換（`zh_tw.py`）只套用在 `zh-TW`。`zh-CN` 檢查不含只在繁體出現的字元。`ja` 檢查假名或漢字（超過 5 個英文字的句子必須有假名），`ko` 檢查韓文字母，`th` 檢查泰文，`ru` 檢查西里爾字母，其餘拉丁語系檢查沒有其他文字系統的字元，且回覆不是英文。檢查不過就當作回覆被拒絕，走重試與降批次。
- 後處理另含：所有目標語言都丟掉獨立的 uh、um、hmm 贅詞。葡語與德語的 um 是一般單字，只有在英文句子含贅詞 um/uh/hmm 且該 um 前後是標點或句首句尾時才丟。
- ASS 折行（40 欄，欄寬用顯示寬度，組合符號不佔欄）依語言：`cjk`（中日文，可在字間斷，不拆拉丁字或數字，韓文用 `spaces`）；`spaces`（拉丁、西里爾、越南、印尼、韓文，只在空白後斷，沒有空白就不斷）；`thai`（泰文，不拆字元叢集，不讓一行以母音符號或聲調符號開頭，優先在空白斷）。泰文沒有使用分詞套件：PyThaiNLP（Apache-2.0）約 17 MB 且依賴多，不符合輕量；因此泰文可能在詞中斷行，但不會拆壞字元。
- `quality`：`ko`、`th` 標為 `experimental`（Qwen3-8B 的韓文、泰文品質較差，常有漏譯或誤譯），其餘為 `stable`；`GET /api/languages` 的每筆都帶 `quality`，UI 可據此標示。
- 換語言時 `en.srt` 永遠不刪；`summary.en.md` 在新語言第一次執行時不刪。
- 詞彙表檢查不放寬。保留英文的專有名詞必須以原文出現在譯文中；日文與韓文另可用該語言文字的寫法（`Language.spellings`，例如 Cursor 的カーソル、커서，Slack 的スラック、슬랙）。單句重試用盡仍不過就保留英文。繁中與簡中沒有別名，所以永遠不會把產品名譯掉。
- 目標語言屬於翻譯、輸出、摘要三步的設定與快取鍵；換語言只重跑這三步，音訊、VAD、ASR、斷句與英文檔都不動。預設語言不改變快取鍵，所以舊專案不必重翻。
- 一個專案可同時保有多個語言：每個語言各自的步驟狀態停放在 `project.json` 的 `parked`，目前使用中的語言是 `active_lang`；兩者只在離開預設語言後才寫入。
- 檔名：`subs.<代碼>.json`、`<代碼>.srt`、`bilingual.en-<代碼>.ass/.vtt`、`summary.<代碼>.md`。繁中保留 `subs.zh-TW.json`、`zh-TW.srt`、`bilingual.ass/.vtt`、`summary.md`。英文摘要一律是 `summary.en.md`。

## 9. 後端 API（草案）

```
GET  /api/health
GET  /api/hardware
GET  /api/registry                       # 可用模型與環境
POST /api/runtimes/{id}/install          # 觸發下載（job）
POST /api/models/{id}/download
DELETE /api/models/{id}
POST /api/projects                       # body: {video_path}
GET  /api/projects/{id}                  # 狀態、檔案路徑、設定；steps 是 active_lang 的各步驟，languages 是每個語言的 translate/export/summarize 狀態
GET  /api/languages                      # 可用的目標語言、品質標籤（stable|experimental）與各自的輸出檔名
POST /api/projects/{id}/jobs             # body: {engine, llm, llm_model, cpu, glossary, summary_en, batch_size, target_lang}；target_lang 對照登錄表，未知代碼回 422，預設 zh-TW；步驟一律全跑，輸入沒變的自動跳過；同專案已有未完成 job 回 409
GET  /api/jobs/{id}/events               # SSE 進度
GET  /api/jobs/{id}                       # job 狀態與總進度
POST /api/jobs/{id}/cancel
GET  /api/projects/{id}/subtitles?lang=en|zh|bilingual&format=srt|vtt|ass|json&target_lang=<代碼>   # zh 指目標語言的文字；target_lang 預設為最近處理的語言
PUT  /api/projects/{id}/subtitles?target_lang=<代碼>   # 使用者手動校對後存回該語言
GET  /api/projects/{id}/summary?lang=<代碼>|en          # 預設為最近處理的語言
```
### 9.1 工作佇列（批次處理）

佇列存在使用者資料夾的 `queue.db`（SQLite，WAL）。項目有影片路徑、`target_lang` 與其他 job 設定、狀態（`queued`、`running`、`paused`、`done`、`failed`、`cancelled`）、時間戳、`attempts` 與 `last_error`。後端啟動時，上次沒跑完的 `running` 項目回到 `queued`，靠管線快取續跑。佇列一次只跑一個項目（GPU 單工），一個項目失敗只影響自己。

```
GET    /api/queue                          # paused、settings、running、eta_s、counts、items（state、step、progress、eta_s、job_id、last_error…）
POST   /api/queue/items                    # body: {items:[{path,target_lang?}], folders:[{path,target_lang?,recursive?}], options:{…同 job body}}；回 {added, skipped:[{path,reason}]}。只收影片副檔名；遞迴掃描不跟隨符號連結或 junction；資料夾 10 秒內沒回應就略過；影片長度超過 5 秒探測預算的部分改在背景補上
PUT    /api/queue/order                    # body: {ids:[…]}，列出的項目排到最前面
POST   /api/queue/pause                    # body 可選 {interrupt:true}：中斷執行中的項目並放回原位
POST   /api/queue/resume
POST   /api/queue/items/{id}/pause|resume|cancel|retry   # retry 把失敗或已取消的項目排到最後
DELETE /api/queue/items/{id}               # 只能刪已結束的項目
DELETE /api/queue/finished
GET    /api/queue/settings                 # PUT 設定 {on_done: notify|sleep|shutdown, allow_power}
POST   /api/queue/power/cancel             # 取消睡眠或關機倒數
GET    /api/queue/events                   # SSE，不會結束；item、removed、order、queue、done、countdown、countdown_cancelled、power
```
- 資料夾依副檔名（`.mp4 .mkv .mov .avi .webm .m4v .flv .wmv .ts .mpg .mpeg`）掃描。同一支影片同一語言在未結束前不能重複加入，會列在 `skipped`。壞檔照常入列，執行時只讓自己失敗。
- ETA 用最近 10 次實際執行過的步驟的「每秒音訊花幾秒」估算，加上影片長度（ffprobe）。第一個項目完成前沒有 ETA（`null`）。翻譯速度因語言而異，所以只是估計。
- 全部完成時一律送 `done` 事件（UI 負責通知）。`on_done` 為 `sleep` 或 `shutdown` 必須同時 `allow_power: true`，否則 422。完成後先送 `countdown`（60 秒，可用 `power/cancel` 取消，或加入新項目也會取消），倒數結束才送 `power` 並呼叫系統。倒數期間任何讓佇列不再閒置的變動（加入、重試、恢復項目、取消暫停）或任何設定變更（含撤回 `allow_power`）都會取消倒數；手動啟動任何工作（`POST /api/projects/{pid}/jobs`）也會取消倒數。「閒置」指沒有排隊或執行中的佇列項目，且沒有進行中的工作。呼叫系統前還會在與 `power/cancel`、設定變更相同的鎖內再檢查一次閒置（含手動工作）且 `on_done` 與 `allow_power` 仍然成立，否則不執行；檢查通過的同一步就決定執行，之後取消不再生效，且呼叫系統時不持有該鎖。佇列、CLI 與 `POST /api/projects` 共用同一份媒體副檔名清單（影片 mp4 mkv mov avi webm m4v flv wmv ts mpg mpeg，音訊 wav mp3 m4a flac ogg aac opus）。後端預設 `notify`。
- 抽音訊預先處理下一個項目沒有做：抽 38 分鐘音訊只要數秒，相對整個項目幾分鐘到十幾分鐘，不值得多一條並行路徑。

後端只監聽 `127.0.0.1`，啟動時隨機連接埠並以一次性 token 驗證，避免被其他本機程序或網頁呼叫。啟動後 stdout 印出 `READY port=<n> token=<t>`；每個請求（含下載路由）都要 `Authorization: Bearer <token>`，並檢查 `Host` 與 `Origin`；SSE 可改用 `?token=`。事件為 `status`、`progress`，最後一則是 `done`、`failed` 或 `cancelled`。

### 9.2 設定、模型管理、硬體設定檔與自檢

使用者設定是一個有型別的檔案 `settings.json`（使用者資料夾，原子寫入，進入點驗證；壞檔不會被採用，`GET /api/settings` 的 `problem` 說明原因）。模型資料夾與鏡像仍在 `storage.json`。已安裝紀錄在 `installed.json`（版本、SHA256、檔案大小與修改時間），最近一次自檢在 `selftest.json`。以上全部在 token 之後。

```
GET    /api/inventory                      # 每個 registry 資產：installed、state、version、installed_version、size_on_disk、path、sha256_state、used_by_profiles、in_active_profile、dependents、blockers；另有 vad_model_path
GET    /api/inventory/{id}
POST   /api/inventory/{id}/verify          # 只限模型：現在雜湊檔案並對照 registry
POST   /api/inventory/{id}/repair          # 檔案不見、未完成或 SHA256 不符就重新下載；正常則 {action:"none"}
POST   /api/inventory/{id}/redownload      # 先下載到旁邊並驗 SHA256，成功才換掉舊檔；失敗舊檔原樣保留，仍是已安裝
POST   /api/updates/check                  # 對照 registry；設了 registry_url 才讀遠端
POST   /api/inventory/{id}/update          # 只在有可安裝的更新時重新下載
DELETE /api/models/{id}?force=&reason=     # 同 /api/runtimes/{id}；被使用中的設定檔或已安裝的資產需要時 409
GET    /api/licenses                       # 每個資產的授權名稱、授權網址與拆開的各條授權
GET    /api/hardware                       # 偵測到的硬體（原欄位）+ recommended_profile
GET    /api/profile   PUT /api/profile {profile: "gpu-24gb"|"gpu-8gb"|"cpu"|null}   # null 跟隨建議
POST   /api/profile/download               # 下載使用中設定檔缺的資產
GET    /api/runtimes/selftest   POST /api/runtimes/selftest
GET    /api/settings   PUT /api/settings   # {llm:{source:builtin|ollama|cloud,…,cloud_consent,api_key?}, registry_url?}
POST   /api/llm/test                       # 失敗是 200 {ok:false, url, detail}。存好的金鑰只送給存好且已同意的雲端網址；改了網址要在 body 帶 api_key，否則不送任何請求
PUT    /api/storage {models_dir}           # 回 warnings：既有模型不會被搬走
POST   /api/storage/move {target, source?} # 唯一會搬模型檔的呼叫；GET 同路徑看進度。崩潰後可重試：目標裡內容相同的檔沿用、殘留 .part 覆寫，只有內容不同的外來檔才拒絕且不動它
```
- 刪除規則：資產在使用中設定檔的需求（含 `needs`）內，或另一個已安裝的資產 `needs` 它（例如 `silero-vad-ggml-v6.2.0` 被 `qwen3-asr-1.7b-q8_0` 需要），回 409 與 `blockers`。`force=true` 必須附 8 個字元以上的 `reason`（記進日誌），否則 422。有 job 在跑時，刪除、修復、重新下載、搬移、自檢一律 409。
- SHA256 狀態：模型檔下載時邊寫邊雜湊，成功時記錄。`verified` 表示記錄與目前檔案的大小與修改時間相符；檔案被改動後變 `unchecked`，`verify` 後可能是 `corrupt`。執行環境是 zip，只能說「下載時已驗證壓縮檔」（`sha256_scope: archive_at_install`）。
- 更新檢查：已安裝版本是 `installed.json` 記錄的版本。沒設遠端時只對照隨 app 附的 registry，訊息為「registry version X installed, no remote configured」。設了 `registry_url`（https）才讀遠端；遠端比內建新的項目 `installable: false`，要更新 app 才能安裝。不會假設任何遠端網址。
- 設定檔：`PUT /api/profile` 隨時可用，不下載也不刪除，回應列出缺的資產與警告（例如 VRAM 不足）；pipeline 的 ASR 後端與 LLM 依使用中設定檔。切換設定檔會清掉先前的自檢回退紀錄。
- 自檢約 5 秒：ASR 用真模型轉 1 秒靜音並確認用到 CUDA；LLM 用 `llama-server --list-devices`（不載入 5 GB 模型）。GPU 失敗就改試 CPU 執行環境，`fallback.reason` 是人看得懂的原因，並存起來，之後的 job 用 CPU。CPU 執行環境沒裝時不存回退（它跑不起來），回報「GPU failed and the CPU runtime is not installed」與要下載的資產，`ok: false`。`VST_SIMULATE_CUDA_FAILURE=1` 讓每個 CUDA 檢查失敗，用來測試回退。缺少的資產回報 `installed: false`，不算 GPU 失敗。
- LLM 來源：`cloud` 必須 `cloud_consent: true`（內容會離開本機，文字見 `cloud_consent_text`），缺少回 422。API 金鑰用 Windows DPAPI 加密存到使用者資料夾 `secrets/`，不進 `settings.json`、日誌或回應；`api_key` 省略表示保留，空字串表示刪除。job 沒指定 LLM 時才用設定頁的來源。
- `registry.json` 每個資產有 `license` 與 `license_url`（授權全文或模型卡），授權頁由它產生。

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
subs.en.json / subs.zh-TW.json   # 內部字幕表示（其他語言 subs.<代碼>.json）
en.srt / zh-TW.srt / bilingual.ass / bilingual.vtt   # 其他語言 <代碼>.srt、bilingual.en-<代碼>.ass/.vtt
summary.md                       # 其他語言 summary.<代碼>.md；英文版 summary.en.md
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
- `python -m backend.cli input.mp4 --engine ... --llm ... [--lang ja]` 可產出 en.srt、zh-TW.srt（或 ja.srt 等）、bilingual.ass、summary.md。
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
