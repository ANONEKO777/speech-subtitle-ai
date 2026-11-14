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
  → [6] 輸出：en.srt（日文影片是 ja.srt，日英混合是 src.srt）、<語言>.srt（繁中為 zh-TW.srt）、bilingual.ass/vtt、project.json
  → [7] 摘要（獨立步驟，可延後或重跑）→ summary.md
```

每一步結果要**快取到專案資料夾**，失敗或換模型時只重跑受影響的步驟。進度以 job 事件（SSE/WebSocket）推送給前端。

### 5.0 來源語言（P23a）
- 影片的語言是專案的一個設定：`en`（預設）、`ja` 或 `ja+en`（日英混合，見下）（`backend/core/source_langs.py` 的型別化表，每筆有檔名、斷句規則、翻譯與摘要提示詞、輸出檢查、燒錄字型）。CLI `--source-lang`、工作 body 的 `source_lang`、佇列項目的 `source_lang`（項目或資料夾可各自指定）都對照這張表，未知代碼回 422。日文目前只能翻成繁體中文（`zh-TW`），其他目標語言回 422，等 P25。表的設計讓之後加別的來源語言不必改流程。
- 來源語言屬於辨識（已有）、斷句、翻譯、摘要的設定與快取鍵。英文不加任何新欄位，所以舊專案的快取鍵、提示詞與輸出逐位元組不變，不必重跑。日文專案的快取鍵與輸出也不變，只有一處行為不同（P23b）：摘要的每則重點筆記含假名時現在會被拒絕並重問（`summarize.parse_map`），舊版會收下；快取鍵沒變，已摘要的日文專案保留舊摘要。英文專案不受影響。
- 檔名：英文是 `subs.en.json` 與 `en.srt`（不變），日文是 `subs.ja.json` 與 `ja.srt`。`project.json` 只在不是英文時才多一個 `source_lang`。一個專案資料夾只有一種來源語言，換語言會重跑辨識以後的步驟，舊語言的來源檔留在原處不刪（`en.srt` 與 `ja.srt` 一律不刪）。
- 字幕的來源文字欄位在程式裡叫 `src`，每則字幕有自己的 `lang`（日英混合的專案每則各有自己的語言，其他專案每則都是專案的語言）。`subs.*.json` 的英文字幕仍寫 `en`，其他語言寫 `src` 加 `lang`，兩種都讀得進來。HTTP API 的請求還用 `en` 這個名字（`lang=en` 取來源文字，PUT 內文也是 `en`，`mode` 的值 `en`），這是請求的格式，不是語言；介面上一律叫「原文」。`GET /subtitles?format=json` 對日文專案的每則字幕除了 `src` 與 `lang` 之外，另外附一個 `en` 欄位放同樣的來源文字，這是暫時的別名，只出現在 API 回覆，不寫進檔案。介面（P24a）已經不讀它：桌面程式讀 `src` 與 `lang`，英文專案的字幕沒有 `lang`，仍讀 `en`。別名在後續的 PR 刪除，英文專案的回覆不變。
- 日英混合（`ja+en`，P23b 是後端，P24b 是介面，見 §10）：第三個來源語言，給日文講者加英文口譯的演講。決定與證據見 `docs/P23b-mixed-source-decision.md`。
  - 檔名 `subs.src.json` 與 `src.srt`。每則字幕有自己的 `lang`（`ja` 或 `en`），日文字幕寫 `src` 加 `lang`，英文字幕仍寫 `en`。新專案，不遷移舊專案。`GET /api/projects` 與專案 JSON 的 `source_lang` 為 `ja+en`。
  - 辨識固定用 Qwen3-ASR（CrispASR）`-l auto`，不帶 `--strict-pipeline`，`--engine` 對 `ja+en` 不起作用。音訊在每個 300 ms 以上的停頓切開（`vad.plan_pauses`，前後各 150 ms，不到 0.5 秒的語音不送），逐段辨識。再做兩個修補（`backend/engines/mixed.py`）：輸出不是日文也不是英文的短段（韓文、簡體中文）用 `-l ja` 重辨；一段尾端有 1.5 秒以上沒有被任何字覆蓋的語音，把那一截另外辨識。之後每個字依文字種類標 `ja` 或 `en`。Qwen3 的檔案只由 `gpu-24gb` 設定檔安裝；沒有這些檔案，或工作在 CPU 上跑時，選 `ja+en` 回明確的錯誤，不降級成 Whisper（操作者 2026-11-12 決定 `ja+en` 只給 24 GB 設定檔；Whisper 逐段偵測把日文講者的話丟掉，見決定文件）。
  - 斷句依語言（各用自己的規則），相鄰不同語言的字永遠不併成一則字幕。
  - 翻譯：每一批只含同一種語言的句子，用該語言的提示詞與輸出檢查，上下文只取同語言的前後 5 則，兩種語言共用同一份詞彙表。英文口譯與日文重複的內容兩邊都保留、都翻譯、都標語言。
  - 摘要用 `prompts/summarize_map_ja_en.md`（日文版加上「英文段常是前一段日文的口譯，同一點只寫一次」）。視窗大小依字數與英文詞數混算。
  - 快取鍵：只有 `ja+en` 在 VAD、ASR、斷句、翻譯、摘要的鍵多出自己的欄位，`en` 與 `ja` 的鍵逐位元組不變（`tests/test_mixed.py::TestCacheKeys`、`tests/test_japanese.py::TestEnglishIsUnchanged`）。
  - 沒有選音軌：一個音軌，兩種語言混在一起。選音軌要改匯入、佇列與 API，不便宜，沒有做。
- 介面（P24a）：匯入框與佇列的加入對話框有「影片語言」（英文、日文，預設英文），送出時帶 `source_lang`。選日文時顯示一行說明（目前只輸出繁體中文）。P24b 在選單加上第三個選項，日文與英文混合，見 §10。播放器的工具列沒有多餘寬度，所以在播放器裡，影片語言改放在工具列下方那一條（只在選了日文時出現，和說明同一行），英文時播放器的工具列與以前相同。佇列的日文與日英混合項目只能選繁體中文。`GET /api/projects` 的每個項目帶 `source_lang`，媒體庫與佇列用它在日文影片上顯示小標籤。已處理完的專案匯入時直接播放，來源語言以專案為準。編輯字幕時原文那一行唯讀，輸入會顯示「原文不能修改」，後端回 422 `english_changed` 也顯示同一句。

- 自動偵測影片語言（P24c）：使用者選了影片（匯入框、加入對話框的每個檔案）後，視窗在背景呼叫 `POST /api/languages/detect`，把猜到的語言預選在「影片語言」。它只是猜測，會猜錯。方法在 `backend/core/language_detect.py`：
  - 從影片均勻取 `SAMPLE_COUNT = 24` 段各 `SAMPLE_S = 5` 秒的音訊（`audio.cut_clips`，ffmpeg 先 seek 再讀，耗時不隨影片長度增加），用 `whisper-cli -l auto -dl` 一次執行（模型只載入一次）請 Whisper large-v3 turbo 對每段說出語言與機率。每一段取 5 秒是刻意的：講者與口譯輪流說話的演講，30 秒的段裡兩種語言都有，Whisper 只說出一種（日英混合講座全片 30 秒的段幾乎全判英文，5 秒的段判出約 4 成日文）。機率不到 `MIN_PROBABILITY = 0.5` 的段與語言不是日文也不是英文的段不計。`MIN_PROBABILITY` 只擋得掉靜音（Whisper 對靜音說英文，機率 0.37）：Whisper 對任何聲音都會說出一種語言，和弦音樂 24 段全判英文（機率 0.7），粉紅雜訊 12 段有 7 段。所以每一段還要有人聲才算：用專案已有的 Silero VAD（`backend/core/vad.py` 的 `speech_seconds`，模型載入一次）量每段的語音秒數，不到 `MIN_SPEECH_S = 0.5` 秒的段不計。在 Whisper 判出語言且機率 0.5 以上的段裡量到：和弦音樂與粉紅雜訊 0 秒，提示音（鈴聲）最多 0.3 秒，真實演講裡停頓的段 0 秒，有人講話的段最少 0.4 秒。VAD 對 24 段約多花 0.4 到 0.5 秒（量過：15 段 0.23 到 0.34 秒，模型載入一次）。
  - 清楚的段少於 `MIN_PIECES = 3`（不到 15 秒的影片）就不下結論。較少的那種語言占清楚段的 `MIXED_SHARE = 0.15` 以上，且清楚的段至少 `MIN_MIXED_PIECES = 12`，判為 `ja+en`；否則是占多數的那一種。多數語言占 `SURE_SHARE = 0.9` 以上才算「肯定」（`sure`），混合一律算肯定。「信心」是占多數那種語言的段數比例。
  - 不是 `ja+en` 的猜測，若這台電腦不能處理混合（見 §10 的可用性），`suggested` 改成占多數的那種語言，`mixed_unavailable` 寫原因；`detected` 仍是聽到的。
  - 選這個方法是量出來的。在 RTX 4090 上（`scripts/p24c_detect_table.py` 重跑，含 `--repeat 2`）：日文 59 分鐘、英文 57 分鐘與 38 分鐘的演講各猜對（信心 1.00），日英混合講座 54 分鐘（原講者日文、口譯英文）判 `ja+en`（日文 0.50）；10 分鐘的日文或英文剪輯猜對；日文剪輯中間插 30 秒或 60 秒的英文（5% 與 9%）仍判日文（信心 0.92），插 75 秒（11%）仍是日文（0.92），插 90 秒（13%）就判 `ja+en`（日文 0.83），插 3 分鐘（23%）也是；英文剪輯插日文同理。所以多出來的那種語言約占 11% 到 13% 之間會從「一種語言」變成「混合」（24 段裡 2 段不算，4 段算，3 段是 12.5%，低於 15%）；只有一部真實的混合講座，這個界線主要由拼接的剪輯量出，沒有第二部真實講座驗證。時間：24 段含 ffmpeg 切段 2.8 到 3.8 秒（檔案與模型已在快取）；視窗從貼上路徑到出現結果 3.3 到 4.4 秒（含 0.5 秒的等待）；第一次（模型與影片都不在快取）10.7 秒。不到 24 段的短影片更快（45 秒的影片 2.1 秒）。5 秒、8 秒、15 秒、30 秒的段在日英混合講座上分別判出約 43%、32%、11%、1% 日文，所以用 5 秒。
  - 另一個候選是讓 Qwen3 替各段標語言：只有 24 GB 設定檔能用，24 段要 13 到 31 秒（含對齊模型），也會把一些日文判錯，所以不用。CPU 設定檔的 Whisper 每段約 10 秒（量過，`-ac` 也沒有變快），24 段要 4 分鐘，所以 CPU 設定檔不偵測（`POST` 回 503，視窗什麼都不做）。
  - 測過沒有猜測的：和弦音樂、粉紅雜訊、鈴聲、靜音、中文語音（都回 null，視窗什麼都不顯示）；英文演講疊上和弦音樂（一樣的大聲或小聲）仍判英文，日文疊上粉紅雜訊仍判日文。沒測過的：其他語言（P25、P26）、更多部影片（只有三部私人影片、兩部公開演講與它們的剪輯），真正的器樂曲或有人聲的歌曲（人聲會被 VAD 當成語音，可能被判成一種語言），英文腔很重的日文講者。
- 介面：選了影片 500 毫秒後才問（輸入中的路徑不會問，路徑一改，舊路徑的結果馬上消失），同一時間只問一部，問過的路徑不再問（失敗或逾時的路徑，換成別的路徑再輸入回來時會再問一次）。只在首頁與設定頁問，因為只有那裡有影片語言選單：按下匯入後匯入框雖然還留著路徑，已經匯入的路徑不再問，播放器裡也不會出現這一條。結果是一行 `detect-note`（「偵測到：日文（信心 100%）」，混合是「偵測到：日文與英文混合（日文 57%、英文 43%）」，不肯定時是「可能是日文（信心 75%），請確認影片語言」，不預選）。肯定的猜測預選在選單，但使用者自己動過選單（自上次開始匯入起）就不換；使用者的選擇和肯定的猜測不同時，顯示 `detect-hint` 與一鍵切換 `detect-switch`；使用者自己選了日文與英文混合時，偵測到日文或英文都不提示（混合已經涵蓋兩者）。失敗、被拒絕或逾時（25 秒）什麼都不顯示。把單一檔案拖到視窗上仍立刻匯入，沿用目前的選擇，不偵測。

### 5.1 字幕規則
- 取得時間戳的方式：
  - 引擎本身有字詞時間戳（whisper.cpp、Parakeet）→ 直接使用。
  - 引擎無時間戳（Qwen3-ASR）→ 用 Qwen3-ForcedAligner 對齊文字與音訊。
- 英文每行 ≤ 42 字元，最多 2 行；中文每行 ≤ 20 字，最多 2 行。
- 日文（原文）每行 ≤ 20 個全形字（40 欄，半形算 1 欄、全形算 2 欄），最多 2 行，每秒超過 7 個全形字會被扣分。日文沒有空格，也沒有詞的邊界：whisper 給的是 1 到 2 個字的子詞 token，所以每個 token 是一個單位，斷在哪裡由 `backend/core/unspaced.py` 依兩側字元的文字種類猜：「。！？」之後最好，「、」其次，ます、です、ので 這類句尾之後，助詞之後；漢字、片假名、平假名的連續字之間很貴，只有別處都放不下才會斷；行頭不放「、。！？」與小假名（ゃゅょっ）與長音「ー」，行尾不放開括號。沒有加形態素分析套件（安裝包不變）。這是推測：實測 CEDEC 沒有斷在「連續同種文字之間」的切點，但沒有人驗證每一個切點都是詞界。
- 日文的拉丁字詞之間才有空格（`Visual Studio Code`），其他地方連續書寫。
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
| `whispercpp` (large-v3-turbo) | **預設**（日文也是，`-l ja`，沿用 VAD 切段，P22 決定。日文 token 不併成詞） | M0 選定：速度、顯存、段落形狀最好，錯字數與 Qwen3 相當 |
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
- 台灣用語（P27）：回覆解析後，`zh_tw.taiwan_terms` 把大陸用語換成台灣用語（`zh_tw.py` 的 `_TERMS`，每條規則是帶保護的正規式）。`_TERMS` 對每個來源語言都套用：影片、軟體、資訊、設定、執行、原始碼（源碼）、營運（運營，不含運營商）、中繼資料（元數據、元資料）等。另有一份只給**英文來源**的 `_ENGLISH_TERMS`（`taiwan_terms_from_english`，經 `Language.terms_from(來源代碼, 文字)` 呼叫，只對目標語言是繁體中文且來源代碼是 `en` 時執行，摘要文字走同一條路）：訪問（存取，只限物件是資料庫、權限、檔案、API 等資源且詞組到此結束，所以訪問系統管理員、訪問了資料科學家不動）、創建（建立，不含創辦公司、樂團、宗教、流派或朝代）、可視化（視覺化）、存儲（儲存）、搜索（搜尋，不含警方搜索、搜索隊、搜索與救援）、接口（介面，不含 USB、HDMI、Type-C 等實體接口，英文字與接口之間有空格也一樣）、調用（呼叫，限工具、函式、API、模型等，兩邊有空格也算）、反饋（回饋）、導入（匯入，正向保護：只在後面接模組、套件、依賴、目錄、檔案，或「導入到」渲染執行緒、目錄、模組等，而且這個名詞要結束詞組（後面是標點、的、了、和、到等）時才換，所以導入依賴注入、導入檔案命名規則、導入函式式程式設計這類複合詞，以及導入新制度、導入 AI、導入了 Git 這類「採用」的意思一律不動）、優化（最佳化，限效能、程式、演算法等）、倉庫（儲存倉，只在**同一則字幕**有程式碼、Git、單一倉庫等語境且沒有貨物語境時，不看相鄰字幕）、儲存庫（儲存倉，同樣在貨物語境下不動，不看語境裡有沒有程式碼用語，所以資料儲存庫、金鑰儲存庫這類詞也會換成儲存倉，這是操作者「儲存庫都改為儲存倉」的決定）、單一倉庫與單一儲存庫（monorepo，寫成單一儲存倉，同樣在貨物語境下不動）。所有程式碼的儲存庫在繁體中文輸出一律寫成儲存倉（操作者 2026-11-13 的決定，取代 P27 的「單一儲存倉、其他儲存庫」）。日文來源不套用 `_ENGLISH_TERMS`（導入實績、導入事例、訪問都是日文的正常用法），但和英文共用 `_SHARED_TERMS`（可視化、存儲、搜索、接口、調用、反饋，守衛相同，這幾個詞在日文講稿裡沒有台灣也接受的讀法），另有日文自己的規則（儲存倉、流水線、訪問、創建，見 §8.2.1）。導入與優化日文來源不動。輸出檢查不看用語，這一步在解析時直接換，所以大陸用語不會造成重試。已快取的譯文不會自己更新：快取鍵不含 `zh_tw.py`，要新用語得重跑翻譯。
- 可選：先用 LLM 從全文抽取專有名詞再翻譯，以保持前後一致。

### 8.2.1 日文來源的翻譯
- 同一份 `prompts/translate.md`，來源語言填進去（`<<SRC>>`、每筆的欄位名 `ja`、範例、來源專屬規則）。日文規則：主語省略時從前後文補、不憑空捏造；丟掉「ええと、まあ、ですね」；不照字翻お、ご敬語；片假名外來語照意思譯，產品與公司名寫拉丁字母（パフォース、パーフォース 是 Perforce）；新字體改繁體；台灣用語（通關不是清關、儲存倉不是倉庫或儲存庫、管線、營運、中繼資料、原始碼、外掛（不是插件，也不是外掛程式）、儲存不是存儲、介面不是接口、搜尋不是搜索、視覺化不是可視化、回饋不是反饋、呼叫不是調用、建立不是創建、存取不是訪問、整理或準備不是整備）。前後各 5 則字幕的上下文照常帶。
- 預設詞彙表另加 Perforce、P4、P4 MCP、P4 DAM、Helix Swarm、東陽テクニカ（Toyo Corporation），以及語音辨識把 Perforce 聽錯的寫法 パフォース、パーフォース、パフォッシャ、パフォーシャ、パワーフォース、パワフォース、パワーホース（都是 Perforce；ビフォー 也可能是它，但平常是 before，所以不放）。
- 輸出檢查（不過就當作回覆被拒絕，走重試與降批次）：沒有殘留假名（中點「・」改成「·」）、沒有日文才用的漢字字形（`zh_tw.japanese_only_chars`：JIS 有、Big5 沒有、也不是簡體字）、沒有簡體字、繁中用語通過 `zh_tw.py`，長度不超過日文字數的 1.1 倍加 8，翻譯不能只有標點（只剩「。」的字幕會被重試）。一則字幕重試與拆批後仍只有標點時，取前一則字幕譯文最後一個子句接在它前面（時間戳與編號不變）。英文來源不做這項檢查。重試訊息裡的來源語言名稱（English 或 Japanese）取自來源語言表。日文來源另外套用 `zh_tw.taiwan_terms_from_japanese`：倉庫與儲存庫（儲存倉）、流水線（管線），在內容講貨物或工廠時保留。這兩條不在 `_TERMS`。源碼（原始碼）、運營（營運）、元數據（中繼資料）在 `_TERMS`，每個來源語言都套用。§8.2 的 `_ENGLISH_TERMS` 不對日文來源執行，但 §8.2 的 `_SHARED_TERMS`（P29）兩個來源都跑：存儲（儲存，不含存儲器）、接口（介面，不含 USB、HDMI、Type-C 等實體接口）、搜索（搜尋，不含警方搜索、搜索隊、搜索與救援）、可視化（視覺化）、反饋（回饋，不含反饋迴路）、調用（呼叫，限工具、函式、API、模型等）。日文另有兩條自己的規則（P29）。創建（建立）用英文那條的守衛，另外不動創建寺院、神社、城市、大學、世界這類創立或創造的意思。訪問（存取）只在三種情況：物件是資料庫、權限、檔案、API、資產、專案等資源且詞組到此結束（可接「的」）；後面接權限、控制、令牌、端點、日誌、介面、接口；前面是工具、使用者、代理、程式等而後面接英文名（從外部工具訪問 Perforce）。訪問方式、訪問資訊、訪問量、同時訪問這類較含糊的詞，只在同一則字幕有軟體用語（工具、伺服器、API、使用者、版本管理等）時才換，所以旅行講稿的訪問方式不動。訪問了京都的寺院、訪問系統管理員一律不動，單獨的「訪問的方式」、「進行訪問」和「同時進行訪問」在字幕沒有軟體用語時也不動（已知漏掉，寧可漏換也不換錯）。P31 再加：硬件（硬體）、演示（示範，演示文稿不動）、万（萬）、与（與）、触（觸），日文新字體表 `SHINJITAI` 因此多收三個 Big5 也有的字形（`VARIANTS_IN_BIG5`）；訪問（存取）另在軟體字幕裡換：進行訪問、同時訪問、後面接英文字的訪問（訪問P4伺服器），仍然要求同一則字幕有軟體用語。導入（導入實績、新人導入）與優化（台灣也用）日文來源不動，因為量測的日文語料裡每一筆都是「採用」或「改良」的意思。每則字幕或每個摘要欄位單獨判斷，所以一個 `ja+en` 專案的日文字幕走日文規則、英文字幕走英文規則，摘要整份走日文規則。規則由傳給翻譯的來源語言決定，所以一個來源語言只有一種結果。
- 單句重試用盡仍不過就保留日文原文當譯文（與英文同一條規則），所以輸出檢查要看有沒有這種字幕。
- 句子單位（P30）：日文語音辨識（whisper）幾乎不出句號，所以一個句子單位不能只靠「。」。日文另以**句尾形**判斷：字幕以ます、ました、ません、でした、です、ください、ましょう、でしょう（後面可接ね或よ）結尾，而且下一則字幕不是以接續開頭（`source_langs._JAPANESE_CONTINUES`：が、けど、けれど、ので、から、し、ね、または よ 加逗號或句點、で 加逗號或は、て、と、も、ば、ため、こと。例外是這幾個字其實是新句子的開頭：し 後面接か、ば、ま、っか（しかし、しばらく、します）；P32 起と 只在後面接漢字、片假名、英文字母、數字、標點、字幕結尾，或とおり、という、といった、とです 時才接續（とレビュー、と、、と幸い），後面接其他平假名（とりあえず、ところで、ときどき、とても、ともに）就是新句子；も 只在もの加の、で、を、が、は、に、と，或單獨的も、も、，も。 時接續（もう、もし、もちろん、ものすごく 是新句子）），所以ますと、とおり、と幸いです 這類接續不在這裡斷句；其餘就在這裡斷句（ですね單獨出現常是口頭禪，不算句尾；有「。」時照舊以「。」為準）。仍找不到句尾的語流照舊在 6 則字幕處截斷（`translate.MAX_UNIT_CUES`）。整句連同前後各 5 則的上下文一次翻譯，用 `[[編號]]` 標記讓模型把譯文切回各則字幕，時間戳記不動。這個規則由 `SourceLanguage.sentence_continues` 與日文的 `sentence_end` 提供，英文來源兩者不變。
- 數字不被字幕切開（P30）：日文的字幕與換行不會落在「數字、小數點或逗號、數字」中間（`unspaced._boundary`），所以 51.9% 不會被切成「51.」與「9%」。這是在斷字幕的地方處理，不是在翻譯後補救。
- 日文術語表（P30，P31 修正）：`backend/core/ja_terms.py` 一份表列出日文詞、台灣寫法與常見的錯誤寫法（ファイル 檔案，不是文件；ブランチを切る 建立分支，不是切換；デフォルトで無効 預設停用；コードレビュー 程式碼審查；リポジトリ 儲存倉；ストリーム 串流；チャットGPT ChatGPT，等）。每次請求只把「這一批文字有的詞」寫進 system prompt 的詞彙表，所以提示不會變長。日文詞只在自成一詞時才算：コード 前面不能是片假名或英文字母（レコード、バーコード、QRコード、エラーコード、ステータスコード、クロードコード 都不算；電源コード、コード進行、コードネーム 也不算），ブランチを切る 只認切る、切って、切った、切り出す、切ります 這類建立的說法，ブランチを切り替える（切換分支）不算，マージン、プロファイル、メタデータ 裡的データ、デッドロック、交通アクセス 也不點名。使用者在詞彙表寫的詞優先：請求文字裡與使用者詞條重疊的表內詞不再寫進提示，所以不會同時出現兩種譯法。表裡的「錯誤寫法」只放台灣不用的寫法：管理者、審閱、核對清單、原始程式碼、上鎖、素材、更改清單 台灣也用，所以管理者不列入表，其餘算對（`also`）；串流類型、串流功能 裡有正確的串流，不算錯。プラグイン 寫外掛（P32 的選擇：整個日文流程只寫外掛，提示、詞表、檢查與 `zh_tw.py` 的改寫都一致；iThome 寫外掛，微軟台灣的用語表寫外掛程式，我們沒有能判定誰才是台灣通用寫法的來源。取捨：這批講稿是給遊戲業界的，外掛在遊戲圈也指作弊程式，讀者可能讀成作弊；外掛程式沒有這個歧義，但比較長。要改回外掛程式，改三處：`ja_terms.py` 的プラグイン 詞條、`source_langs.py` 提示裡的 plug-in 那一句、`zh_tw.py` 的 `外掛程式` 改寫規則（以及 `p30_quality_check.py` 的 `PLUGIN_LONG_FORM`）。外掛程式碼、外掛程式庫、外掛程式設計、外掛程式架構、外掛程式介面、外掛程式語言、外掛程式開發 是 外掛 加 程式X 的詞，不改寫）。アクセス 寫存取，不是訪問。同一份表也是 `scripts/p30_quality_check.py` 的檢查依據。表在 `_translate_prompt_digest` 裡，改了表就重翻。日文提示另加兩條：只翻日文說的，不加原因、連接詞或子句；數字原樣保留，小數點與百分號不丟。
- 日文後續修正（P32）：(1) 產品名保留拉丁字母：詞表加クロードコード（Claude Code）、ビジュアルスタジオコード 與 Visual Studioコード（Visual Studio Code）、VSコード（VS Code）、GitHubコパイロット（GitHub Copilot），把程式碼、代碼、克勞德、副駕駛當成錯誤寫法；一般的コード 條不再點名這些產品。提示裡只列出這些產品名，不另加「不要翻譯コード」這句：消融實驗（一次一個變體，結果固定）顯示有那句話時 Perforce 少寫三則；ストリーム 的升降不能歸因於這句話（只多改一個中性字也會回到 13/19），句尾斷詞與數字完整數也隨任何提示改動浮動（59 到 71）。拿掉這句有風險：有一個變體裡 Visual Studio Code 仍在第 312 則被翻成中文，所以「詞表夠用」只在目前的提示成立；也有代價：クロード、チャットGPT、GitHubコパイロット 並列時（約一則字幕）仍可能被翻成中文。(2) 文件 與 檢查出 依日文改寫（`ja_terms.SourceFix`，由 `translate._clean` 呼叫，只有日文來源與 `ja+en` 的日文字幕會跑）：該句子單位的日文有ファイル 時，文件 改寫成檔案；有ドキュメント、ドキュメンテーション、書類、文書、資料、文章、仕様書、設計書、契約書、説明書、報告書、証明書、議事録、論文、マニュアル、レポート、規格、README、PDF 任何一個就整句不改寫；說明、相關、技術、設計、規格、契約、合約、申請、需求、使用者、API、公、證明、正式、官方、法律 加文件 與 文件夾 永遠不改。單位有チェックアウト 時，檢查出 改寫成簽出，但檢查出現、檢查出來、檢查出問題 這類「查到」的意思與被、能 加檢查出 不動。證據只有兩場講稿（一場 Perforce、一場遊戲），沒有文件很多的講稿可以量誤傷率。(3) 訪問 的軟體詞單用整字比對（Apple 不算 App），拜訪公司、地點、電視台（NHK、Apple、東京、總部、節目、辦公室等）不動；漏換比誤換好。(4) 使用者在詞彙表寫的詞會取代同一個詞的來源預設詞條（`translate.glossary_for`，例如使用者自己寫 PowerForce）。(5) 外掛程式 改寫成外掛 不動外掛程式碼 這類複合詞（見上）。`JAPANESE_UNITS` 是 finals-3，版本字串釘在句尾規則、接續規則、句號規則、字幕上限與一組固定字幕的斷句結果上，所以改動其中任何一項而沒有換版本，測試會失敗。
- 日文成語與句子改寫（P33）：操作者在 P30 的盲測頁面四段裡選了兩段舊版（第 120 段的「入口低」，第 49 段的 Shell 與流暢）、兩段新版，這三處在這裡處理。(1) 間口が広い：提示裡原有一句「間口が広い means the barrier to entry is low」，模型照抄成「入口低」，這句不在靜態提示裡了，改成詞表兩條：間口が広く奥深い（容易入門又深奧）與 間口が広い（容易入門），pattern 也收語音辨識常把間口聽成的マグチ，只收広い、広く、広かっ（間口が広がる、間口を広げる 不算），後面緊接店、敷地、土地、物件、住宅、ビル、建物、家、間取、道路 的也不算（那是店面或土地的寬度），間口が広くて奥深い 與間口が広く奥深い 一樣；也算對的寫法有入門簡單、入門容易、入門門檻低、門檻低、容易上手、好上手、易於入門；錯誤寫法是入口低、入口門檻、入口寬、入口廣、廣開入口、開闊的入口、寬廣的入口、廣泛且深。換成詞表的原因：詞表只在那一批文字有這個詞時才寫進提示，其餘請求不多一句，也不再把英文解釋寫在每個請求裡讓模型照抄。同樣用詞表處理的還有コースクリア型／ステージクリア型（關卡制，賽道清除、關卡清除是錯，證據只有一個句子）與シェルブ（Perforce 的 shelve，擱置；Shell、shelb 是錯。擱置是微軟台灣對 shelve 的寫法，操作者可改）。(2) 第 49 段憑空出現的 Shell：這個 Shell 不是語音辨識的錯（原文是正確的シェルブ），不是上下文漏進來（シェルブ 與接著的なく 在同一個句子單位裡，單位也沒有切開），不是提示詞裡的詞；模型不認得シェルブ，把它讀成 shell。詞表沒有這個詞，所以補上。另外用視窗重跑時，視窗若從句子中間開始，前半句只是上下文，模型會把前半句的詞抄進譯文；`scripts/p30_translate_run.py --windows` 因此把視窗擴到完整的句子單位。(3) 依日文改寫（`ja_terms.SourceFix`，與 P32 同一個機制，只有日文來源跑）。原則：改寫不能動已經對的中文，所以每條規則只改錯誤寫法出現的位置，`tests/test_japanese_source_fixes.py` 檢查每條規則的結果不會再被改寫，也檢查對的字後面接任何續字（串流動作、串流串接、稀疏串流功能、工作流程圖）都不動。P33 第一版沒有這道檢查，驗證者用執行找到三個誤傷（串流動作變成串串流作；workflow.yml 與 .github/workflows 變成工作流程.yml 與 .github/工作流程；同一句有ブランチを切る 與チェックアウト 時，對的切換分支變成建立分支），都在這一版改掉。(a) ストリーム：單位有ストリーム 時，流暢、流暢度、流動 只在當名詞用時改寫成串流：前一字是的、與、和、及、跟、或、之，或它在一則字幕開頭且後面接標點、或、與、和、及、跟（整則字幕只有「流暢」也算）；更流暢、很流暢、流暢地、流暢性、流動性、流動作、流動態、流動畫、流動向、流動量、流動速 不動。流串（前面不是串，也不是下面那些字，後面不是接、聯、連）改成串流。流 接在功能、類型、機制前面，且前一字不是串、主、上、下、分、合、對、逆、水、氣、電、暖、寒、潮、洪、河、溪、回、交、熱、激、金、物、人 時改成串流（主流功能、分流功能、現金流功能、物流機制 是別的詞；另外流功能、分支流功能 是ストリーム）。單位有スムーズ、スムース、流暢、滑らか、なめらか、流れ、フロー（ワークフロー 不算）、メインストリーム、ダウンストリーム、アップストリーム、ストリームライン 任何一個時整條不改；ストリーム 前後 12 個字內有円滑、快適、軽快、サクサク、使いやすい、安定（安定度、安定性 不算）、楽（音楽、娯楽、快楽、楽しい 這類不算）、流す、流し、流さ 時也整條不改。(b) スパースストリーム：稀疏流 改成稀疏串流（後面接程、動、暢、量、向、性、速、派、行、通、水、氓 的是別的詞，不動：稀疏流程、稀疏流動、稀疏流量）。(c) ワークフロー：單位有ワークフロー 時，單獨的英文 workflow、workflows（小寫，或在一則字幕開頭的 Workflow）改成工作流程。前後貼著英文字母、數字、底線、點、斜線、反斜線、連字號或反引號（workflow.yml、.github/workflows、GITHUB_WORKFLOW），旁邊隔一個空格就是別的英文字（Windows Workflow Foundation、GitHub Workflows），或在反引號包住的程式碼裡，都不動；全大寫的 WORKFLOWS 也不動。(d) ブランチを切る：單位有ブランチを切る（建立分支的說法）而且沒有任何一個「換到別的分支」的說法時（切り替え、切替、切り換え、切りかえ、乗り換え、スイッチ、チェックアウト、移動、移る、移す、移行、遷移、変更、変える、戻る、戻す、行く、入る、使い分け、入れ替え、そのブランチ、別のブランチ、他のブランチ、元のブランチ、ブランチ間；每個詞各有一條測試。沒列的說法只會讓改寫漏掉，不會改錯），接在一個、數字加個、新的 或直接接分支前的切換改成建立。同一句既建立又切換時整條不改（模型寫的切換分支可能是對的）。(e) 使用者詞彙表優先：使用者的詞彙表有ファイル、チェックアウト、ストリーム、スパースストリーム、ワークフロー、ブランチを切る 其中一個詞條時，對應的改寫關閉，保留使用者寫的譯法（包括保留原文的詞條）。只認整個詞條：ブランチ 這個詞條不關閉ブランチを切る 規則。證據：在已存的 38 個輸出檔（P30 到 P33，兩場講稿，P33 的是視窗重跑）上，ストリーム 規則改寫 35 個字幕輸出（7 個日文句子），守衛另外擋下 9 個單位輸出（單位有流れ，模型寫的流動是「流動情況」，不是 ストリーム）；稀疏流規則改寫 14 個（6 句）；workflow 規則 5 個（2 句）；ブランチを切る 規則 14 個（5 句）。這些改寫我都讀過，沒有改錯的；第二版的規則（名詞位置、守衛、邊界）在同一批輸出上改寫的字幕與第一版相同。證據來自兩場講稿，只有一場講稿有ストリーム，所以誤傷率沒有第二場可以驗證。已知缺口：模型有時乾脆漏掉整個詞（第 49 段的ストリーム 在一次重跑裡不見了），改寫修不了漏譯；模型寫成「流的運作」「導入流後」這種單獨的流不改（只改接在功能、類型、機制前面的）；在一則字幕開頭、後面接的字不在上面名單的流暢或流動不改；表示順或易的詞與ストリーム 在同一句、距離超過 12 個字時仍會改；述語式的間口が広い（この店は間口が広い）分不出是店面還是慣用語，仍然算慣用語。
- 快取（P30）：日文專案的切字幕金鑰與翻譯金鑰各加一個版本字串（`pipeline.UNSPACED_CUT`、`pipeline.JAPANESE_UNITS`），術語表也在翻譯金鑰裡，所以舊的日文專案下次執行時重新切字幕、重新翻譯一次。P31 把 `JAPANESE_UNITS` 改成 finals-2（連接詞表變了），日文專案再重翻一次。英文專案的所有金鑰不變。P33 起翻譯金鑰（`pipeline._translate_prompt_digest`）也讀 `SOURCE_FIXES`，所以只改一條改寫規則也會讓日文專案重翻一次；英文來源沒有改寫，英文的金鑰不變。P34 改了其中三條規則的守衛，日文與 `ja+en` 專案因此再重翻一次，英文專案的金鑰不變。
- 已知缺口（P30）：語音辨識的錯字（約 14% 字元錯誤）照樣流進翻譯，這個 PR 不動辨識引擎；標記切回時模型偶爾把一句話的後半放進下一則字幕（字幕順序不變但內容位移一則），自動檢查只能用長度比例看到它；詞彙表沒有用摘要 map 步驟抽出的專案專用名詞，因為摘要排在翻譯之後，要先重排步驟；沒有人或獨立評審看過譯文，只有自動檢查與盲測檔。

### 8.3 摘要（map-reduce）
1. 依時間將逐字稿切成章節片段（約 2,000–4,000 tokens，片段間少量重疊）。
2. Map：每段產出要點與時間範圍。
3. Reduce：合併成 `summary.md`，包含：一句話總結、主題章節（約每 3 分鐘一章，半章進位，最多 7 章，且每章至少要有 2 條筆記支撐；章數依筆記實際涵蓋的長度算，所以短講只有 1–3 章）（附起始時間戳，可點擊跳轉）、關鍵觀點條列、可行動的結論/金句（若有）。
   - 最後一章必須落在整場演講的最後四分之一（章數上限只有 2 章時改為後半）；只有筆記沒有涵蓋到那裡時，才改為「筆記涵蓋範圍」的最後四分之一。筆記到得了末段的長講維持原規則。
   - Map 請求會列出該片段內均分的取筆記時間點（每個要點一個），讓筆記分布到整個片段而不是集中在前幾分鐘。
   - Map 回傳的要點多於上限時不重試，均勻挑出上限數量（保留頭尾）。
   - Reduce 重試用完仍失敗時依序退讓：先把最後一次回覆的最後一章移到第一個夠晚的筆記（只在僅差位置時成立，語言檢查照做）；再失敗改要求 1 章；再失敗則採用最後一次回覆並略過語言檢查，同樣套用語言後處理（台灣用語等），並標為 degraded：寫入 `summary.parts.json`、`project.json` 的 summarize 步驟（`degraded: true`，只在為真時寫入，`GET /api/projects/{id}` 的各步驟也帶 `degraded`），以及工作報告（`summary_degraded`），讓 UI 可以提示，絕不當成一般摘要。1 章這一步仍做語言檢查。只有回覆不是可解析的 JSON 或結構不合時才不產生 `summary.md`。
4. 輸出語言為目標語言（預設繁體中文）；可選同時輸出英文版。
5. 日文逐字稿：Map 用 `prompts/summarize_map_ja.md`，筆記直接寫成繁體中文（台灣用語），要點數與視窗大小依字數算（日文約 1.2 字一個 token、2 字一個詞），所以 59 分鐘的演講切成約 7 個視窗，Reduce 的章節長度、章數與最後一章位置規則不變，輸出的語言檢查另外擋假名與日文漢字。
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
- 日文來源的專案同樣用這些檔名（來源檔是 `subs.ja.json`、`ja.srt`，所以目標語言和來源語言不能同為 `ja`）。
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
POST /api/languages/detect                # 內文 `{video_path}`（絕對路徑的媒體檔，否則 422）。回 `{detected, suggested, mixed_unavailable, confidence, sure, shares:{ja,en}, clear, samples:[{start_s, code, probability, speech_s}]}`，`detected` 與 `suggested` 是 `en`、`ja`、`ja+en` 或 null（聲音太少）。Whisper 或 VAD 模型沒裝、CPU 設定檔、讀不了音訊或 Whisper 失敗回 503（只代表沒有猜測，不代表影片有問題）。見 §5.0
GET  /api/languages                      # 可用的目標語言、品質標籤（stable|experimental）與各自的輸出檔名；另有 `sources`，影片語言清單 [{code, name, native_name, available, reason}]，`reason` 是 null、`missing_files`（沒有 Qwen3 檔案）或 `cpu`（工作在 CPU 上跑），視窗用它把這台電腦跑不了的選項停用（見 §10）
POST /api/projects/{id}/jobs             # body: {engine, llm, llm_model, cpu, glossary, summary_en, batch_size, target_lang, source_lang}（source_lang 預設 en，見 §5.0）；target_lang 對照登錄表，未知代碼回 422，預設 zh-TW；步驟一律全跑，輸入沒變的自動跳過；同專案已有未完成 job 回 409
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
POST   /api/queue/items                    # body: {items:[{path,target_lang?,source_lang?}], folders:[{path,target_lang?,source_lang?,recursive?}], options:{…同 job body}}；回 {added, skipped:[{path,reason}]}。只收影片副檔名；遞迴掃描不跟隨符號連結或 junction；資料夾 10 秒內沒回應就略過；影片長度超過 5 秒探測預算的部分改在背景補上
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
- 全部完成時一律送 `done` 事件（UI 負責通知）。`on_done` 為 `sleep` 或 `shutdown` 必須同時 `allow_power: true`，否則 422。完成後先送 `countdown`（60 秒，可用 `power/cancel` 取消，或加入新項目也會取消），倒數結束才送 `power` 並呼叫系統。倒數期間任何讓佇列不再閒置的變動（加入、重試、恢復項目、取消暫停）或任何設定變更（含撤回 `allow_power`）都會取消倒數；手動啟動任何工作（`POST /api/projects/{pid}/jobs`）也會取消倒數。「閒置」指沒有排隊或執行中的佇列項目，且沒有進行中的工作。呼叫系統前還會在與 `power/cancel`、設定變更相同的鎖內再檢查一次閒置（含手動工作）且 `on_done` 與 `allow_power` 仍然成立，否則不執行；檢查通過的同一步就決定執行，之後取消不再生效，且呼叫系統時不持有該鎖。佇列、CLI 與 `POST /api/projects` 共用同一份媒體副檔名清單（影片 mp4 mkv mov avi webm m4v flv wmv ts mpg mpeg 3gp mts m2ts ogv，音訊 wav mp3 m4a flac ogg aac opus wma aiff aif）；CLI 與 `POST /api/projects` 拒絕其他副檔名時，訊息會列出全部可接受的副檔名。倒數只在佇列閒置且沒有任何進行中的工作時才開始：最後一個項目結束時若手動工作仍在跑，不送 `done` 也不開始倒數，等最後一個工作結束後才送 `done` 並開始倒數。後端預設 `notify`。
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
- 執行環境資料夾的替換：重新下載時舊資料夾先改名為 `<名稱>.old`，新資料夾就位後才刪除。若在兩次改名之間被中止，後端啟動時與每次使用該執行環境前，發現 `.old` 而沒有正式資料夾就改回並寫入日誌；正式資料夾完整（含執行檔）時則刪除殘留的 `.old`。刪除執行環境同時刪除 `.old`：先把資料夾改名為 `<名稱>.trash-<亂數>`（任何檔案被鎖住時改名會失敗，執行環境原封不動並回 409），再刪除改名後的資料夾；刪到一半失敗的殘留在下次啟動時清除。CLI、佇列與應用程式在解析任何執行環境之前都先做同樣的 `.old` 還原。任何路由遇到被鎖住的檔案（含 verify、repair）一律由 API 邊界統一轉成 409 並指出路徑。Windows 的權限或檔案被占用錯誤（WinError 5/32/33）在替換、搬移與刪除時回報被鎖住的路徑並建議關閉占用它的程式，原始錯誤寫入日誌。
- LLM 來源：`cloud` 必須 `cloud_consent: true`（內容會離開本機，文字見 `cloud_consent_text`），缺少回 422。API 金鑰用 Windows DPAPI 加密存到使用者資料夾 `secrets/`，不進 `settings.json`、日誌或回應；`api_key` 省略表示保留，空字串表示刪除。金鑰屬於它當初輸入時的雲端網址：存成 `cloud` 且網址與已存的不同時，body 必須帶新的 `api_key`，否則 422，舊金鑰與舊網址維持原樣（不會悄悄刪除金鑰，也不會把舊金鑰綁到新網址）。job 沒指定 LLM 時才用設定頁的來源。
- `registry.json` 每個資產有 `license` 與 `license_url`（授權全文或模型卡），授權頁由它產生。

## 10. 前端 / 播放器

- 影片區 + **其下方**的字幕區（不疊在畫面上）；可切換：僅原文 / 僅中文 / 雙語（中文在上、原文在下，或相反，可設定）。
- 字幕大小、顏色、行距可調。
- 影片語言（P24b）：匯入框、加入對話框（預設與每個項目）與批次佇列的「影片語言」選單有三個選項，英文、日文、日文與英文混合，送出時帶 `source_lang`（`en`、`ja`、`ja+en`）。選混合時顯示一行說明「日英混合影片目前只輸出繁體中文字幕，需要 Qwen3 模型檔（24 GB 的模型組會安裝）。」，目標語言只能選繁體中文。
- 混合語言的可用性：混合需要 Qwen3 的引擎檔案（只有 24 GB 設定檔會安裝）與顯示卡，沒有 CPU 模式。視窗讀 `GET /api/languages` 的 `sources`，這台電腦跑不了時，該選項停用，選項文字寫原因，`missing_files` 是「這台電腦沒有安裝混合語言所需的模型」，`cpu` 是「混合語言需要顯示卡，這台電腦目前以 CPU 執行」。選項被略過而工作還是送出時，後端拒絕並回明確的訊息，視窗照原樣顯示，不降級成 Whisper。
- 自動偵測（P24c）：見 §5.0。匯入框下方（工具列之外，工具列寬度不變）的一條出現 `detect-note`，有不同時再出現 `detect-hint` 與 `detect-switch`；加入對話框每個檔案列有 `add-row-detect`、`add-row-hint`、`add-row-switch`，一次只問一個檔案，使用者改過的列不會被換掉。
- 標籤：媒體庫與佇列在日文影片上顯示「日文影片」，在日英混合影片上顯示「日英混合」，英文影片不顯示。
- 每則字幕的語言標記：只在日英混合的專案，字幕清單與編輯器在每則原文旁顯示小標記「日」或「英」（`data-testid="lang-mark"`，帶 `data-cue-lang`）。原文那一行用該則字幕自己的語言設定字型（`lang` 屬性）。編輯時，相鄰但語言不同的字幕不會被合併。
- 播放器的雙語模式用每則字幕自己的語言顯示它的原文行。字幕的每一行 `p` 帶 `data-lang`（`src` 是原文，`zh` 是翻譯）；原文那一行另帶 `data-cue-lang`（`ja` 或 `en`）與 `lang`。字幕清單與編輯器的原文那一行（`.src`、`edit-source`）也帶 `data-cue-lang`。
- 字幕清單面板：點擊條目跳轉；播放時自動捲動；可雙擊編輯文字與時間（編輯後寫回 `project.json`）。
- 摘要頁：章節時間戳可跳轉到影片位置。
- 格式相容：HTML5 video 播不動（如 MKV、HEVC）時，背景用 ffmpeg 產生 H.264/AAC 的 proxy mp4；或改用 libmpv。
- 燒錄字幕：英文來源的專案一律用 Arial，不查字型（彎引號、破折號、刪節號等一般標點 Arial 畫得出來）。日文來源的字幕，若含假名、漢字、全形字元或日文標點，要先在系統已安裝的字型裡找一個有全部字形的日文字型（Yu Gothic、Meiryo、MS Gothic，讀 Windows 字型登錄與字型檔的 cmap），找不到或缺字時燒錄回 422，訊息說明缺哪個字型或哪些字，不會燒出空白方塊。匯出的 bilingual.ass 仍寫 Arial，交給播放器補字型。
- 匯出：SRT（原文、中、雙語）、ASS（雙語）、VTT、`summary.md`；可選「燒錄成新影片」（非預設）。原文 SRT 的檔名是 `<影片名>.<來源語言>.srt`，來源語言裡的 `+` 換成 `-`，所以英文是 `.en.srt`，日文是 `.ja.srt`，日英混合是 `.ja-en.srt`。日英混合的燒錄與日文影片相同，需要日文字型。

## 11. 專案資料格式

每個專案一個資料夾，內含：
```
project.json        # 影片路徑、引擎/模型版本、設定、各步驟狀態與時間
audio.wav           # 快取
segments.json       # ASR 原始結果（含字詞時間戳）
subs.en.json / subs.zh-TW.json   # 內部字幕表示（其他語言 subs.<代碼>.json）；日文影片的原文是 subs.ja.json，日英混合是 subs.src.json
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
- 不提交大型模型與版權影片到儲存倉。

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
