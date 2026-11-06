<div align="center">

**繁體中文** | [English](README.en.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

# Video Subtitle Translator（字幕翻譯）

**在自己的電腦與顯示卡上，把英文長演講變成時間準確的雙語字幕與重點整理。**

![license](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)
![platform](https://img.shields.io/badge/platform-Windows-0078D6)
![runs](https://img.shields.io/badge/runs-locally%20on%20your%20GPU-f0b23e)
![status](https://img.shields.io/badge/status-build%20from%20source-lightgrey)

<img src="docs/media/hero.png" alt="播放器在影片下方顯示英文與繁體中文字幕，右側是字幕清單" width="900">

</div>

選一部沒有字幕的英文演講影片。程式會辨識語音、切成字幕、翻譯、寫出附章節的摘要，再讓你在影片下方看著字幕播放。每一個步驟都在你的電腦上執行。在 RTX 4090 上，一場 38 分鐘的演講約 5 到 6 分鐘就能處理完。

## 特色

### 整條流程都在本機執行

匯入影片後，視窗會即時顯示七個步驟：擷取音訊、偵測語音、語音辨識、斷句、翻譯、輸出字幕、重點摘要。每一步的結果都存在專案資料夾裡。再跑一次，做完的步驟會直接略過。中途停掉，下次從停下的那一步接著做。換翻譯模型時，只會重跑翻譯、輸出與摘要。

<img src="docs/media/import-progress.png" alt="匯入畫面，進度 61%，目前在翻譯步驟，下方是七個步驟的進度列" width="760">

### 影片下方的雙語字幕

字幕放在影片下方，不蓋住畫面，也不燒進影片檔。你可以切換成只看英文、只看翻譯，或兩個一起看。切換時影片大小不會變，右側的字幕清單會跟著播放進度捲動，點一條字幕就能跳到那裡。

| 只看英文 | 只看翻譯 | 雙語 |
| --- | --- | --- |
| <img src="docs/media/mode-en.png" alt="只顯示英文字幕" width="290"> | <img src="docs/media/mode-zh.png" alt="只顯示中文字幕" width="290"> | <img src="docs/media/mode-both.png" alt="中英雙語字幕" width="290"> |

### 直接在清單裡改字幕

在字幕上按兩下，或選取後按 F2，就能修改時間與文字。Enter 儲存，Esc 取消，Ctrl+Z 復原。不合理的修改會被擋下，原因直接顯示在那一列：和下一條重疊、結束時間早於開始、超過 7 秒、內容是空的、時間格式錯誤。英文那一行是辨識結果，只能讀不能改，因為各語言的翻譯與摘要都是從它產生的。

手動修改過的字幕不會被無聲覆蓋。如果你從命令列或 API 對同一個專案重新翻譯，你的修改會疊回新的翻譯上，執行報告會說明保留了幾條、有幾條已對不上。

| 被擋下的修改 | 已儲存的修改 |
| --- | --- |
| <img src="docs/media/edit-error.png" alt="時間重疊被拒絕，原因顯示在那一列" width="440"> | <img src="docs/media/edit-saved.png" alt="儲存後的字幕，旁邊有鉛筆記號" width="440"> |

### 附章節的重點整理

摘要分頁會列出一句話總結、帶時間的章節、關鍵觀點與結論。點章節的時間，影片就跳到那一秒。

<img src="docs/media/summary.png" alt="摘要分頁，有章節卡片與關鍵觀點" width="760">

### 匯出

可以匯出 SRT（英文、翻譯、雙語）、ASS、VTT，以及 Markdown 格式的摘要。字幕檔是純 UTF-8 文字，任何播放器都能開。

<img src="docs/media/export-menu.png" alt="匯出選單，列出 SRT、ASS、VTT 與摘要" width="760">

### 十三種目標語言

預設翻成繁體中文（台灣）。同一個專案可以同時放多個語言，字幕清單上方的選單可以切換。每個語言都有自己的提示詞與文字系統檢查，回覆用錯文字會被退回重問。清單見[支援的目標語言](#支援的目標語言)。

<img src="docs/media/languages.png" alt="同一場演講顯示成日文，字幕清單上方有語言選單" width="760">

### 其他

- 翻譯使用固定的隨機種子。同一場演講從頭跑兩次，產生的字幕檔逐位元組相同。
- 關閉視窗時，後端與它底下所有語音、語言模型的程序都會一起結束。
- 視窗能做的事，命令列與有權杖保護的本機 API 也都能做。

## 示範影片

![demo](docs/media/demo.mp4)

[下載影片](docs/media/demo.mp4)。約一分鐘，依序是匯入、進度、播放、切換模式、修改字幕、跳到摘要章節、匯出，最後換成第二個語言。進度的部分經過加速。

## 開發中

以下功能還沒有放進程式，有些已經有後端、只是還沒有畫面。

- **批次佇列。** 一次排入很多部影片，夜裡慢慢跑，附預估時間，結束後可選擇睡眠或關機。後端與 API 已經完成，還沒有畫面。
- **設定與模型管理。** 刪除、重新下載或更新模型與執行環境，切換 GPU 或 CPU 設定檔，選擇本機或雲端語言模型，並對 GPU 做自我檢測。後端與 API 已經完成，還沒有設定畫面。
- **首次設定精靈與安裝程式。** 目前沒有設定精靈，也沒有安裝程式。請看[從原始碼安裝與執行](#從原始碼安裝與執行)。
- **更多播放器功能。** 目前的播放器是系統內建的影片控制列，加上字幕區與字幕清單。更完整的播放控制還在製作。
- **在視窗裡選目標語言。** 視窗匯入時固定翻成繁體中文（台灣），其他語言目前要從命令列指定。

## 系統需求

這個專案只在一台機器上開發與量測：Windows 11、NVIDIA RTX 4090（24 GB 顯存）、64 GB 記憶體。其他組合沒有測過。

- 64 位元 Windows，已測試的系統是 Windows 11。
- NVIDIA 顯示卡與新版驅動程式，不需要另外安裝 CUDA Toolkit。
- 預設設定檔要求至少 16 GB 顯存。後端另有 8 GB 設定檔（顯存 7 GB 以上）與純 CPU 設定檔，這兩個還沒有在對應的硬體上實際跑過。
- 執行環境與模型的磁碟空間：預設設定檔約 12 GB（會多下載一個備援語音引擎），8 GB 設定檔約 8 GB。另外要預留專案資料夾的空間。
- `PATH` 裡要有 ffmpeg，或把它的資料夾設在 `VST_FFMPEG_DIR`。

## 從原始碼安裝與執行

**程式還沒有打包。** 目前沒有安裝程式，也沒有下載連結，必須自己建置。以下步驟寫給開發者。

需要 Python 3.11 以上與 [uv](https://docs.astral.sh/uv/)、Node.js 與 npm、Rust 與 MSVC 工具鏈（Tauri 2 的前置需求），以及 ffmpeg。

```powershell
git clone https://cggitlab.chinesegamer.net/abcd1997/speech-subtitle-ai.git
cd speech-subtitle-ai

uv sync                                   # 後端環境，建立 .venv
npm --prefix app ci                       # 前端相依套件
cd app; npx tauri build --no-bundle; cd ..   # 產生 app/src-tauri/target/release/video-subtitle-translator.exe
```

語音與語言模型及其執行環境不在儲存庫裡，視窗也還沒有設定畫面。請透過下載 API 為你的硬體下載，它以一個小型本機伺服器的形式執行：

```powershell
uv run python scripts/serve_downloads.py --port 8765    # 會印出 READY port=8765 data=...
# 在第二個終端機：
curl.exe -X POST http://127.0.0.1:8765/api/profile/download
curl.exe http://127.0.0.1:8765/api/downloads             # 每個檔案的進度
```

檔案會放在 `%LOCALAPPDATA%\video-subtitle-translator`，要換資料夾就設定 `VST_USER_DATA`。同一個伺服器的 `GET /api/profile` 會列出還缺什麼。這個伺服器沒有身分驗證，只在下載時開著就好。

接著執行 `app/src-tauri/target/release/video-subtitle-translator.exe`。視窗會用 `.venv` 啟動 Python 後端，關閉視窗時一併結束。

## 使用方式

### 在視窗裡

1. 貼上影片的完整路徑，或按「選擇檔案」。
2. 按「匯入」。進度畫面會顯示目前的步驟。
3. 完成後會進入播放器。處理過的影片會直接開在播放器。
4. 用上方的模式切換選擇只看英文、只看翻譯或雙語。字幕的大小、顏色與行距可以在工具列調整。
5. 在字幕上按兩下就能修改。開啟摘要分頁、點章節時間可以跳轉，用匯出選單存檔。

視窗能播放系統 WebView2 解得開的格式，最保險的是 MP4 裝 H.264 與 AAC。影片播不出來時，視窗會說明，並請你提供 H.264/AAC 的 MP4 副本。

### 在命令列

```powershell
uv run python -m backend.cli talk.mp4 --lang ja
```

這會在影片旁邊建立 `talk.vst\`，裡面有 `en.srt`、`ja.srt`、`bilingual.en-ja.ass`、`summary.ja.md` 與 `project.json`。同樣的指令再跑一次不會做任何事，因為每一步都有快取。`--lang` 可以填[支援的目標語言](#支援的目標語言)裡的任何代碼，`--help` 會列出全部選項。一個專案對每個語言各保留一份翻譯。

## 隱私

語音辨識與翻譯預設都在你的電腦上執行。影片、音訊與逐字稿不會離開本機，本機 API 只監聽 `127.0.0.1`，並且需要權杖。

雲端語言模型是選用功能，預設關閉。若你選用，後端在你明確同意之前拒絕儲存設定，因為影片的文字內容會離開你的電腦。API 金鑰以 Windows DPAPI 加密，只能寫入、無法透過 API 讀回，也不會出現在設定檔與日誌裡。這個選項目前透過後端 API 使用，對應的設定畫面還在開發中。

除了選用的雲端模型，只有下載模型與執行環境時才需要網路。

## 支援的目標語言

| 代碼 | 語言 | 備註 |
| --- | --- | --- |
| zh-TW | 繁體中文（台灣） | 預設 |
| zh-CN | 簡體中文 | |
| ja | 日文 | |
| ko | 韓文 | 實驗性 |
| es | 西班牙文 | |
| fr | 法文 | |
| de | 德文 | |
| pt | 葡萄牙文 | |
| it | 義大利文 | |
| ru | 俄文 | |
| vi | 越南文 | |
| th | 泰文 | 實驗性 |
| id | 印尼文 | |

各語言的品質不同。在 38 分鐘的演講上，用回譯檢查打分數：西班牙文、簡體中文與德文和繁體中文相當，日文略低，韓文明顯較低，有些句子的人名與語意是錯的。韓文與泰文因此標為實驗性。十三種語言裡，有六種在真實演講上完整跑過（zh-TW、zh-CN、ja、ko、es、de），其餘只有測試覆蓋。

## 素材來源

截圖與示範影片使用 NASA 局長 Bill Nelson 的「State of NASA」演說片段，演說日期是 2023 年 3 月 9 日（[NASA Image and Video Library](https://images.nasa.gov/details/2023%20%E2%80%98State%20of%20NASA%E2%80%99%20Address%20from%20Administrator%20Bill%20Nelson)）。片段取自原片的 1:14 到 7:07。NASA 的媒體在美國一般不受著作權保護，仍請參考 [NASA 的媒體使用規範](https://www.nasa.gov/nasa-brand-center/images-and-media/)，NASA 不為本專案背書。影片本身不在這個儲存庫裡。圖中的字幕與摘要由本程式產生。

## 授權

[GNU Affero General Public License v3.0 or later](LICENSE)（AGPL-3.0-or-later）。第三方聲明在 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
