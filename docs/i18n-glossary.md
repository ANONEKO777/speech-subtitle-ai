# Interface glossary

The product terms the window uses in each language. Later waves and the W5 translator follow it, so one thing is called one name on every screen. It started in W1 from the words the shell and the settings pages use, and each wave adds the terms of its own screens.

The catalogs are in `app/src/i18n/catalog/`. See `docs/I18N-PLAN.md` for how they work.

## Terms

| Concept | zh-TW | English | Note |
|---|---|---|---|
| project | 專案 | project | A video with its subtitles and edits. "project folder" is 專案資料夾. |
| subtitles | 字幕 | subtitles | The plural noun. Use "subtitle language" for 字幕語言. |
| video language | 影片語言 | video language | The language spoken in the video. |
| subtitle language | 字幕語言 | subtitle language | The language the subtitles are translated into. |
| original | 原文 | original | The source-language line of a cue. |
| bilingual | 雙語 | bilingual, "Both" on the toolbar | Both lines shown together. The toolbar button says "Both" because "Bilingual" leaves the path field too short at 960 px. |
| transcript | 逐字稿 | transcript | What speech recognition writes. |
| speech recognition | 語音辨識 | speech recognition | The step is "Recognizing speech". |
| sentence splitting | 斷句 | splitting sentences | |
| summary | 重點摘要 | summary | The key points of a talk. |
| translate | 翻譯 | translate, translation | |
| import | 匯入 | import | The button that starts a video. |
| choose file | 選擇檔案 | choose file | |
| library | 媒體庫 | library | The list of videos already processed. |
| queue | 佇列 | queue | |
| batch add | 批次加入 | batch add | |
| settings | 設定 | settings | |
| profile | 設定檔 | profile | A hardware profile (which devices run speech recognition and the LLM). Not "configuration file". |
| model | 模型 | model | A downloaded model file. |
| runtime | 執行檔 | runtime | A downloaded executable the app runs (whisper-cli, llama-server). It matches the navigation "Models and runtimes". 執行環境 in the navigation is the same word. |
| runtime | 執行環境 | runtime | "Models and runtimes" is 模型與執行環境. |
| graphics card, GPU | 顯示卡, GPU | graphics card, GPU | Say "graphics card" for the hardware and "GPU" for the work it does. |
| processor, CPU | 處理器, CPU | processor, CPU | |
| chip | 晶片 | chip | Apple silicon. The profile names say "Apple silicon". |
| memory | 記憶體 | memory (RAM) | 顯示記憶體 is "video memory (VRAM)", 統一記憶體 is "unified memory". |
| driver | 驅動程式 | driver | |
| backend | 後端 | backend | The engine the window talks to. |
| self-test | 自檢 | self-test | |
| LLM source | LLM 來源 | LLM source | Built-in llama-server, Ollama or a cloud service. |
| cloud | 雲端 | cloud | |
| this computer | 本機, 這台電腦 | this computer | 本機 in short labels, 這台電腦 in sentences. Do not say "local machine". |
| built-in | 內建 | built-in | |
| API key | API 金鑰 | API key | |
| URL | 網址 | URL | |
| license | 授權 | license | "Third-party licenses" is 第三方授權. |
| update | 更新 | update | "Check for updates" is 檢查更新. |
| interface language | 介面語言 | interface language | The language of the window. 視窗 is "window". |
| window | 視窗 | window | |
| apply | 套用 | apply | |
| save | 儲存 | save | |
| cancel | 取消 | cancel | |
| close | 關閉 | close | |
| download, resume | 下載, 續傳 | download, resume | |
| recommended | 建議 | recommended | |
| experimental | 實驗性 | experimental | A subtitle language the backend has not rated. |
| machine translated | 機器翻譯 | machine translated | Said in the picker for a catalog no native speaker has read. |

## How the English is written

- Short, plain product English. A button is a verb (`Import`, `Cancel`, `Save`). A heading is a noun phrase.
- Keep the proper nouns as they are: Whisper, Qwen3, llama-server, Ollama, CUDA, Metal, VRAM, GPU, CPU, SHA256, FFmpeg.
- Keep the nuance of the Chinese and do not shorten away information. A warning that something leaves the computer keeps saying so.
- Count nouns that change with a number are plural keys (`one` and `other`). A count next to a unit that has no plural (`4 s`, `12 min`) is one key.
- Sentence case for headings and buttons (`Check for updates`), no full stop after a button or a heading, a full stop after a sentence.

## Taiwan wording in zh-TW

zh-TW text uses Taiwan terms, never the mainland ones, so a Traditional Chinese reader does not meet words that are only Simplified Chinese ones in other characters. The terms the app already uses:

| Use (zh-TW) | Not (mainland) |
|---|---|
| 影片 | 視頻 |
| 檔案 | 文件 |
| 資料夾 | 文件夾 |
| 程式 | 程序 |
| 軟體, 硬體 | 軟件, 硬件 |
| 記憶體 | 內存 |
| 顯示卡 | 顯卡 |
| 滑鼠 | 鼠標 |
| 視窗 | 窗口 |
| 介面 | 界面 |
| 設定 | 設置 |
| 儲存 | 保存 |
| 網址 | 網站地址, 鏈接 |
| 伺服器 | 服務器 |
| 預設 | 默認 |
| 品質 | 質量 |
| 使用者 | 用戶 |
| 資訊 | 信息 |
| 逐字稿 | 文字記錄 |
| 連線 | 連接 |
| 重新啟動 | 重啟 |

A change to a zh-TW string in a wave that only moves strings is a bug. A wording fix belongs in its own commit.

## zh-CN and ja (W5)

The machine translation of `zh-CN` follows the mainland column of the table above (视频, 文件, 程序, 内存, 显卡, 鼠标, 窗口, 界面, 设置, 保存, 服务器, 默认, 用户, 信息). `ja` uses the usual katakana terms (ファイル, フォルダー, ダウンロード, インストール, ウィンドウ, プロファイル, 設定). W5 reads both against this file and adds the terms of W2 to W4 that the table does not have yet.
