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

## W1b: language names, product name, platform

| Concept | zh-TW | English | Note |
|---|---|---|---|
| language names | the native name (繁體中文, 日本語, 한국어, Español) | the English name (Traditional Chinese, Japanese, Korean, Spanish) | A language is named in the language of the window, from `lang.<code>` in the catalog. Only the interface-language picker shows each language in its own script. |
| product name | 字幕翻譯 | Video Subtitle Translator | The window title, the page title and the queue notification. |
| current profile | 使用中 | Current profile | The disabled button of the profile in use. The chip beside it says "In use" (目前使用). |

## W2: the first-run wizard and the models page

Terms the wizard and the models page added. The zh-TW column is the text those screens already used.

| Concept | zh-TW | English | Note |
|---|---|---|---|
| first run | 第一次使用 | First run | The small heading above the wizard title. |
| item | 項目 | item | One model or one runtime in the download table. |
| built on this computer | 自行建置 | build on this computer | A runtime a Mac builds with a script. Never "compile". |
| resume (a download) | 續傳, 繼續下載 | Resume, Resume download | "Resume" in a table row, "Resume download" on the wizard button. |
| download again | 重新下載 | Download again | The button for a file that is already there. Not "re-download". |
| verify | 驗證 | Verify | Checks the SHA256 of a model file. |
| repair | 修復 | Repair | |
| listed version | 登錄版本 | Listed version | The version the app's model list names, next to the version on disk. Not "registry", which is internal. |
| used by | 使用於 | Used by | The profiles that use the item. |
| needed by | 相依 | Needed by | The other items that need this one. |
| in use | 目前使用 | In use | In the models table, an item the current profile uses. The same words as the hardware page's chip (W1b). |
| partly downloaded | 下載到一半 | Incomplete | A download that stopped before the end. The status chip has to stay short, so it does not say "Partly downloaded". |
| SHA256 matches | SHA256 相符, SHA256 不符 | SHA256 matches, SHA256 does not match | |
| force delete | 強制刪除 | Force delete | Needs a written reason of at least 8 characters, which goes to the log. |
| models folder | 模型資料夾 | Models folder | Where the downloaded models live. |
| Visual C++ Redistributable | Visual C++ 可轉散發套件 | Visual C++ Redistributable | Microsoft's name in English. |

## W3a (the player)

The terms of the player, its side column, the library and the help overlay.

| Concept | zh-TW | English | Note |
|---|---|---|---|
| one subtitle | 句, 則, 條 | subtitle | One cue. "Previous subtitle", "Subtitle 12", "2 subtitles failed". Never "line" or "sentence", which the Chinese counters 句 and 則 hide. |
| subtitle timing | 字幕時間微調 | subtitle timing | The offset of all subtitles against the picture. A positive value shows them later. |
| play queue | 播放佇列 | play queue | The videos to play next, in the library. It is not the processing batch (佇列, the Batch tab), which holds videos waiting to be translated. |
| screenshot | 截圖 | screenshot | |
| picture-in-picture | 子母畫面 | picture-in-picture | |
| full screen | 全螢幕 | full screen | Two words. "Exit full screen". |
| A-B loop | A-B 循環 | A-B loop | "Point A" is the start, "Point B" the end. The on-screen line after the first press reads "Point A set at 0:12". |
| frame | 格 | frame | "Next frame", "Previous frame". |
| burn in | 燒入 | burn into | A verb on every menu entry: "Burn subtitles into screenshots", "Burn subtitles into MP4 (whole video)", "Burn subtitles into MP4 (next 30 s)". |
| edited by hand | 手動修改 | edited by hand | A subtitle the person corrected. "{n} subtitles edited" in the footer. |
| left empty | 留空 | left empty | A subtitle the translator could not do and left blank. |
| video file | 影片檔 | video file | |
| shortcuts | 鍵盤快捷鍵 | keyboard shortcuts | Key names (Space, Ctrl, Shift, arrows) stay as they are in every language. |
| language name (player) | 繁體中文, 한국어 | Traditional Chinese, Korean | The window shows the backend's English name in English and the native name in the other languages. The UI language picker keeps native names. |

## W3b: the batch, the editor, export and the summary

| Concept | zh-TW | English | Note |
|---|---|---|---|
| batch (the processing queue) | 佇列 | batch | The videos waiting to be translated, on the home screen, in the player's tab and in the toolbar chip ("Batch 2/7"). From W3b the English says "batch", not "queue", so it never reads like the library's "play queue" (播放佇列, W3a). W1's toolbar and toast texts follow ("View batch", "3 items added to the batch"). The player's tab says "Batch" too. |
| add to batch | 加入佇列 | add to batch | The dialog title and its button ("Add to batch (3)"). The toolbar button stays "Batch add" (批次加入). |
| item | 項 | item | One video and one subtitle language in the batch. "2/7 processed". |
| waiting, processing, paused, done, failed, cancelled | 等待中, 處理中, 已暫停, 完成, 失敗, 已取消 | Waiting, Processing, Paused, Done, Failed, Cancelled | The state of an item. |
| clear finished | 清除已完成 | Clear finished | |
| sleep, shut down | 睡眠, 關機 | sleep, shut down | What the computer does when the batch finishes. "Put the computer to sleep", "Shut down". |
| countdown | 倒數 | countdown | The 60 seconds before sleep or shutdown, which "Cancel" stops. |
| original | 原文 | original | In the export menu: "SRT (original)". |
| bilingual (export) | 雙語 | bilingual | "SRT (bilingual)", "ASS (bilingual)", "VTT (bilingual)". The format names stay. |
| export | 匯出 | export | "Exported to C:\...", "Export cancelled", "Export failed: ...". |
| start, end (of a subtitle) | 開始, 結束 | Start, End | The two times in the cue editor. |
| undo | 復原 | undo | "Couldn't undo: ...". |
| jump to | 跳到 | jump to | A chapter time in the summary: "Jump to 1:05:30". |

## W4a: sentences from the backend and the shell

| Concept | zh-TW | English | Note |
|---|---|---|---|
| burned-in subtitles | 燒錄出來的字幕 | burned-in subtitles | The old backend sentences say 燒錄 and the window's menus say 燒入. Both are kept in Chinese. |
| empty boxes | 空白方塊 | empty boxes | What a font with no glyph draws. |
| glyph | 字形 | glyph | |
| Optional features | 選用功能 | Optional features | The Windows settings page, quoted with its path: "Settings > System > Optional features". |
| Japanese supplemental fonts | 「日文」的補充字型 | Japanese supplemental fonts | |
| Media Feature Pack | 媒體功能套件 | Media Feature Pack | Microsoft's name. |
| Font Book | 字體簿 | Font Book | Apple's name. |
| runtimes folder | 執行檔資料夾 | runtimes folder | "Runtime" is the glossary word for 執行環境 and 執行檔. |
| update source | 更新來源 | update source | |
| signature | 簽章 | signature | |
| backend | 後端 | backend | |

## W4b part 1: backend messages in Traditional Chinese

Here the English came first and `zh-TW` is new text.

| Concept | zh-TW | English | Note |
|---|---|---|---|
| remote registry, registry (update check) | 遠端清單, 清單 | remote registry, registry | The app's list of models and runtimes. Not 登錄檔, which is the Windows registry. The table's "Listed version" stays 登錄版本. |
| speech engine | 辨識引擎 | ASR engine, engine | |
| ASR, VAD, LLM | 語音辨識, VAD, LLM | ASR, VAD, LLM | VAD and LLM stay as they are. |
| fallback (speech recognition) | 備用 | fallback | 備用語音辨識. |
| audio track | 音訊軌 | audio track | |
| token | token | token | Not translated. |
| context (LLM) | 內容長度 | context | |
| archive | 壓縮檔 | archive | |
| exit code | 結束代碼 | exit code | |
| redirect | 轉址 | redirect | |
| locked by another program | 被其他程式鎖定 | locked by another program | |
| File Explorer | 檔案總管 | File Explorer | Microsoft's name. |
| command window | 命令列視窗 | command window | |

## W4b part 2: the remaining backend and shell messages

| Term | zh-TW | en | Notes |
|---|---|---|---|
| queued, running, paused, done, failed, cancelled (a batch item) | 等待中, 處理中, 已暫停, 完成, 失敗, 已取消 | queued, running, paused, done, failed, cancelled | `noticeWord.*`, as the batch list labels a state. |
| API key | API 金鑰 | API key | |
| registry URL | 遠端清單網址 | registry_url | The backend sends the setting's name; the window names it. |
| absolute path | 完整路徑 | absolute path | Said with an example: 例如 E:\vst-models. |
| move (models) | 搬移 | move | As the storage card's button: 搬移現有模型並切換. |
| VRAM | 顯示卡記憶體 | VRAM | |
| self-test | 自檢 | self-test | As in W2. |
| segment step | 斷句步驟 | segment step | As the progress screen names the step. |
| burn in (an export) | 燒入 | burn-in | As the menus say. |
| verify | 驗證 | verify | As in W2. |
| job | 工作 | job | 匯出工作 for a burn-in export. |
| a profile's id (gpu-24gb) | the profile's name (24 GB 顯示卡) | the id | `noticeWord.<id>`. English keeps the id the backend sent. |
