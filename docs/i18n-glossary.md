# Interface glossary

The product terms the window uses in each language. Later waves and the W5 translator follow it, so one thing is called one name on every screen. It started in W1 from the words the shell and the settings pages use, and each wave adds the terms of its own screens.

The catalogs are in `app/src/i18n/catalog/`. See `docs/I18N-PLAN.md` for how they work.

## Terms

| Concept | zh-TW | zh-CN | ja | English | Note |
| --- | --- | --- | --- | --- | --- |
| project | 專案 | 项目 | プロジェクト | project | A video with its subtitles and edits. "project folder" is 專案資料夾. zh-CN: "project folder" is 项目文件夹. 项目 is kept for the video project only; the W2 item is 组件. ja: "project folder" is プロジェクトフォルダー. |
| subtitles | 字幕 | 字幕 | 字幕 | subtitles | The plural noun. Use "subtitle language" for 字幕語言. |
| video language | 影片語言 | 视频语言 | 動画の言語 | video language | The language spoken in the video. |
| subtitle language | 字幕語言 | 字幕语言 | 字幕の言語 | subtitle language | The language the subtitles are translated into. ja: Never 字幕言語. |
| original | 原文 | 原文 | 原文 | original | The source-language line of a cue. |
| bilingual | 雙語 | 双语 | 二言語 | bilingual, "Both" on the toolbar | Both lines shown together. The toolbar button says "Both" because "Bilingual" leaves the path field too short at 960 px. zh-CN: The toolbar button says 双语 too. ja: Toolbar "Both" is 二言語, export is "{format} 二言語", a bilingual file is 二言語の字幕ファイル. |
| transcript | 逐字稿 | 逐字稿 | 文字起こし | transcript | What speech recognition writes. zh-CN: Understood in mainland; kept from the machine pass. |
| speech recognition | 語音辨識 | 语音识别 | 音声認識 | speech recognition | The step is "Recognizing speech". |
| sentence splitting | 斷句 | 断句 | 文の分割 | splitting sentences |  |
| summary | 重點摘要 | 重点摘要 | 要約 | summary | The key points of a talk. zh-CN: The player tab says 摘要. |
| translate | 翻譯 | 翻译 | 翻訳 | translate, translation |  |
| import | 匯入 | 导入 | インポート | import | The button that starts a video. ja: Never 取り込む. |
| choose file | 選擇檔案 | 选择文件 | ファイルを選択 | choose file |  |
| library | 媒體庫 | 媒体库 | ライブラリ | library | The list of videos already processed. |
| queue | 佇列 | 队列 | バッチ | queue | zh-CN: The processing batch. The play queue is 播放队列. ja: The processing batch (W3b). The library's play queue is 再生キュー, so キュー alone is never used. |
| batch add | 批次加入 | 批量添加 | 一括追加 | batch add |  |
| settings | 設定 | 设置 | 設定 | settings |  |
| profile | 設定檔 | 配置方案 | プロファイル | profile | A hardware profile (which devices run speech recognition and the LLM). Not "configuration file". zh-CN: Not 配置文件, which means configuration file. |
| model | 模型 | 模型 | モデル | model | A downloaded model file. |
| runtime | 執行檔 | 可执行文件 | 実行ファイル | runtime | A downloaded executable the app runs (whisper-cli, llama-server). It matches the navigation "Models and runtimes". 執行環境 in the navigation is the same word. zh-CN: For 執行檔 (asset kind, CPU or GPU build). ja: 執行檔. One word for both runtime rows. |
| runtime | 執行環境 | 运行环境 | 実行ファイル | runtime | "Models and runtimes" is 模型與執行環境. zh-CN: "Models and runtimes" is 模型与运行环境. ja: 執行環境. "Models and runtimes" is モデルと実行ファイル. The runtimes folder is 実行ファイル用フォルダー. |
| graphics card, GPU | 顯示卡, GPU | 显卡, GPU | グラフィックスカード, GPU | graphics card, GPU | Say "graphics card" for the hardware and "GPU" for the work it does. |
| processor, CPU | 處理器, CPU | 处理器, CPU | プロセッサー, CPU | processor, CPU |  |
| chip | 晶片 | 芯片 | チップ | chip | Apple silicon. The profile names say "Apple silicon". zh-CN: Apple 芯片. ja: Apple silicon is Apple シリコン. |
| memory | 記憶體 | 内存 | メモリ（RAM） | memory (RAM) | 顯示記憶體 is "video memory (VRAM)", 統一記憶體 is "unified memory". zh-CN: 显存 for VRAM, 统一内存 for unified memory. ja: ビデオメモリ（VRAM）, ユニファイドメモリ. |
| driver | 驅動程式 | 驱动程序 | ドライバー | driver | zh-CN: 驱动 in the short wizard line. |
| backend | 後端 | 后端 | バックエンド | backend | The engine the window talks to. |
| self-test | 自檢 | 自检 | セルフテスト | self-test |  |
| LLM source | LLM 來源 | LLM 来源 | LLM ソース | LLM source | Built-in llama-server, Ollama or a cloud service. |
| cloud | 雲端 | 云端 | クラウド | cloud |  |
| this computer | 本機, 這台電腦 | 本机, 这台电脑 | このコンピューター | this computer | 本機 in short labels, 這台電腦 in sentences. Do not say "local machine". ja: In labels and sentences. Never パソコン. |
| built-in | 內建 | 内置 | 内蔵 | built-in |  |
| API key | API 金鑰 | API 密钥 | API キー | API key |  |
| URL | 網址 | 网址 | URL | URL |  |
| license | 授權 | 许可证 | ライセンス | license | "Third-party licenses" is 第三方授權. zh-CN: "Third-party licenses" is 第三方许可证. Not 授权, which reads as authorization. ja: "Third-party licenses" is サードパーティのライセンス. |
| update | 更新 | 更新 | 更新 | update | "Check for updates" is 檢查更新. ja: "Check for updates" is 更新を確認 (button), 更新の確認 (heading). |
| interface language | 介面語言 | 界面语言 | 表示言語 | interface language | The language of the window. 視窗 is "window". ja: The Windows word. The picker label is ウィンドウの言語. |
| window | 視窗 | 窗口 | ウィンドウ | window |  |
| apply | 套用 | 应用 | 適用 | apply | zh-CN: The verb on the settings pages. The app itself is 本软件, never 应用. ja: "Apply to all" is すべてに適用. The language page's "Applied." is 反映しました. |
| save | 儲存 | 保存 | 保存 | save |  |
| cancel | 取消 | 取消 | キャンセル | cancel |  |
| close | 關閉 | 关闭 | 閉じる | close |  |
| download, resume | 下載, 續傳 | 下载, 续传 | ダウンロード, 再開 | download, resume |  |
| recommended | 建議 | 推荐 | おすすめ | recommended | zh-CN: The wizard sentence says 建议使用. |
| experimental | 實驗性 | 实验性 | 試験的 | experimental | A subtitle language the backend has not rated. |
| machine translated | 機器翻譯 | 机器翻译 | 機械翻訳 | machine translated | Said in the picker for a catalog no native speaker has read. |

## How the English is written

- Short, plain product English. A button is a verb (`Import`, `Cancel`, `Save`). A heading is a noun phrase.
- Keep the proper nouns as they are: Whisper, Qwen3, llama-server, Ollama, CUDA, Metal, VRAM, GPU, CPU, SHA256, FFmpeg.
- Keep the nuance of the Chinese and do not shorten away information. A warning that something leaves the computer keeps saying so.
- Count nouns that change with a number are plural keys (`one` and `other`). A count next to a unit that has no plural (`4 s`, `12 min`) is one key.
- Sentence case for headings and buttons (`Check for updates`), no full stop after a button or a heading, a full stop after a sentence.

## Taiwan wording in zh-TW

zh-TW text uses Taiwan terms, never the mainland ones, so a Traditional Chinese reader does not meet words that are only Simplified Chinese ones in other characters. The terms the app already uses:

| Use (zh-TW) | Not (mainland) | zh-CN | ja |
| --- | --- | --- | --- |
| 影片 | 視頻 | 视频 | 動画 |
| 檔案 | 文件 | 文件 | ファイル |
| 資料夾 | 文件夾 | 文件夹 | フォルダー |
| 程式 | 程序 | 程序 | プログラム |
| 軟體, 硬體 | 軟件, 硬件 | 软件, 硬件 | ソフトウェア, ハードウェア |
| 記憶體 | 內存 | 内存 | メモリ |
| 顯示卡 | 顯卡 | 显卡 | グラフィックスカード |
| 滑鼠 | 鼠標 | 鼠标 | マウス |
| 視窗 | 窗口 | 窗口 | ウィンドウ |
| 介面 | 界面 | 界面 | 表示言語 |
| 設定 | 設置 | 设置 | 設定 |
| 儲存 | 保存 | 保存 | 保存 |
| 網址 | 網站地址, 鏈接 | 网址 | URL |
| 伺服器 | 服務器 | 服务器 | サーバー |
| 預設 | 默認 | 默认 | 既定 |
| 品質 | 質量 | 质量 | 品質 |
| 使用者 | 用戶 | 用户 | ユーザー |
| 資訊 | 信息 | 信息 | 情報 |
| 逐字稿 | 文字記錄 | 逐字稿 | 文字起こし |
| 連線 | 連接 | 连接 | 接続 |
| 重新啟動 | 重啟 | 重新启动 | 再起動 |

A change to a zh-TW string in a wave that only moves strings is a bug. A wording fix belongs in its own commit.

## zh-CN and ja (W5)

The machine translation of `zh-CN` follows the mainland column of the table above (视频, 文件, 程序, 内存, 显卡, 鼠标, 窗口, 界面, 设置, 保存, 服务器, 默认, 用户, 信息). `ja` uses the usual katakana terms (ファイル, フォルダー, ダウンロード, インストール, ウィンドウ, プロファイル, 設定). W5 reads both against this file and adds the terms of W2 to W4 that the table does not have yet.

W5 read every entry of both catalogs and added the `zh-CN` and `ja` columns to every table in this file. They are still machine translations that no native speaker has read, and the picker says so. The choices a later wave must keep:

- **Batch and play queue.** `zh-CN` 队列 and 播放队列, `ja` バッチ and 再生キュー. キュー alone is not used, so the two never read alike.
- **Item** (a model or runtime row). `zh-CN` 组件, because 项目 is the video project. Counts use 项.
- **Profile.** `zh-CN` 配置方案 everywhere. 配置文件 means a configuration file.
- **Runtime.** `ja` 実行ファイル on every screen. `zh-CN` 运行环境 in the navigation and 可执行文件 for one program.
- **Import and export.** `ja` インポート and エクスポート. Not 取り込む or 書き出し.
- **License.** `zh-CN` 许可证. 授权 reads as authorization.
- **The app.** `zh-CN` 本软件 or 软件. 应用 is the verb "apply" on the settings pages.
- **Buttons quoted in a sentence** use the button's own words: `zh-CN` “校验”, `ja` 「更新をダウンロード」.

## W1b: language names, product name, platform

| Concept | zh-TW | zh-CN | ja | English | Note |
| --- | --- | --- | --- | --- | --- |
| language names | the native name (繁體中文, 日本語, 한국어, Español) | 英语, 日语, 繁体中文 | 日本語, 英語, 繁体字中国語, 簡体字中国語 | the English name (Traditional Chinese, Japanese, Korean, Spanish) | A language is named in the language of the window, from `lang.<code>` in the catalog. Only the interface-language picker shows each language in its own script. zh-CN: lang.* names. The video-language picker keeps 英文, 日文 as zh-TW does. ja: Named in Japanese. |
| product name | 字幕翻譯 | 字幕翻译 | 字幕翻訳 | Video Subtitle Translator | The window title, the page title and the queue notification. |
| current profile | 使用中 | 使用中 | 使用中 | Current profile | The disabled button of the profile in use. The chip beside it says "In use" (目前使用). zh-CN: The chip beside it is 当前使用. ja: The disabled button and the chip both say 使用中. |

## W2: the first-run wizard and the models page

Terms the wizard and the models page added. The zh-TW column is the text those screens already used.

| Concept | zh-TW | zh-CN | ja | English | Note |
| --- | --- | --- | --- | --- | --- |
| first run | 第一次使用 | 首次使用 | 初回の設定 | First run | The small heading above the wizard title. |
| item | 項目 | 组件 | 項目 | item | One model or one runtime in the download table. zh-CN: A model or a runtime. Counted with 项 (还缺 {n} 项). ja: Counted with 件. |
| built on this computer | 自行建置 | 自行构建 | 自分でビルド | build on this computer | A runtime a Mac builds with a script. Never "compile". ja: "この Mac で自分でビルド". |
| resume (a download) | 續傳, 繼續下載 | 续传, 继续下载 | 再開, ダウンロードを再開 | Resume, Resume download | "Resume" in a table row, "Resume download" on the wizard button. |
| download again | 重新下載 | 重新下载 | 再ダウンロード | Download again | The button for a file that is already there. Not "re-download". |
| verify | 驗證 | 校验 | 検証 | Verify | Checks the SHA256 of a model file. zh-CN: The models page button and the backend sentences that name it. |
| repair | 修復 | 修复 | 修復 | Repair |  |
| listed version | 登錄版本 | 清单版本 | 一覧のバージョン | Listed version | The version the app's model list names, next to the version on disk. Not "registry", which is internal. zh-CN: Matches 远程清单 for the registry. ja: Not レジストリ, which reads as the Windows registry. |
| used by | 使用於 | 使用于 | 使用先 | Used by | The profiles that use the item. |
| needed by | 相依 | 被依赖 | 必要としている項目 | Needed by | The other items that need this one. |
| in use | 目前使用 | 当前使用 | 使用中 | In use | In the models table, an item the current profile uses. The same words as the hardware page's chip (W1b). |
| partly downloaded | 下載到一半 | 下载未完成 | ダウンロード途中 | Incomplete | A download that stopped before the end. The status chip has to stay short, so it does not say "Partly downloaded". |
| SHA256 matches | SHA256 相符, SHA256 不符 | SHA256 一致, SHA256 不一致 | SHA256 が一致, SHA256 が不一致 | SHA256 matches, SHA256 does not match |  |
| force delete | 強制刪除 | 强制删除 | 強制削除 | Force delete | Needs a written reason of at least 8 characters, which goes to the log. |
| models folder | 模型資料夾 | 模型文件夹 | モデルフォルダー | Models folder | Where the downloaded models live. |
| Visual C++ Redistributable | Visual C++ 可轉散發套件 | Visual C++ 可再发行程序包 | Microsoft Visual C++ 再頒布可能パッケージ | Visual C++ Redistributable | Microsoft's name in English. zh-CN: Microsoft's zh-CN name. ja: Microsoft's Japanese name. |

## W3a (the player)

The terms of the player, its side column, the library and the help overlay.

| Concept | zh-TW | zh-CN | ja | English | Note |
| --- | --- | --- | --- | --- | --- |
| one subtitle | 句, 則, 條 | 句, 条 | 字幕 | subtitle | One cue. "Previous subtitle", "Subtitle 12", "2 subtitles failed". Never "line" or "sentence", which the Chinese counters 句 and 則 hide. ja: Counted with 件. "Subtitle 12" is 12 番目の字幕. |
| subtitle timing | 字幕時間微調 | 字幕时间微调 | 字幕のタイミング調整 | subtitle timing | The offset of all subtitles against the picture. A positive value shows them later. ja: The on-screen line says 字幕のタイミング. |
| play queue | 播放佇列 | 播放队列 | 再生キュー | play queue | The videos to play next, in the library. It is not the processing batch (佇列, the Batch tab), which holds videos waiting to be translated. ja: The batch is バッチ. |
| screenshot | 截圖 | 截图 | スクリーンショット | screenshot |  |
| picture-in-picture | 子母畫面 | 画中画 | ピクチャーインピクチャー | picture-in-picture |  |
| full screen | 全螢幕 | 全屏 | 全画面 | full screen | Two words. "Exit full screen". zh-CN: "Exit full screen" is 退出全屏. ja: "Exit full screen" is 全画面を終了. |
| A-B loop | A-B 循環 | A-B 循环 | A-B リピート | A-B loop | "Point A" is the start, "Point B" the end. The on-screen line after the first press reads "Point A set at 0:12". zh-CN: "Point A" is A 点. ja: A 点, B 点. "Point A set at 0:12" is "A 点を 0:12 に設定". |
| frame | 格 | 帧 | フレーム | frame | "Next frame", "Previous frame". zh-CN: 上一帧, 下一帧. |
| burn in | 燒入 | 烧录 | 焼き込む | burn into | A verb on every menu entry: "Burn subtitles into screenshots", "Burn subtitles into MP4 (whole video)", "Burn subtitles into MP4 (next 30 s)". zh-CN: The same verb in the menus and in the backend sentences. |
| edited by hand | 手動修改 | 手动修改 | 手動で編集済み | edited by hand | A subtitle the person corrected. "{n} subtitles edited" in the footer. ja: The re-translate toast says 手動の修正. |
| left empty | 留空 | 留空 | 空欄 | left empty | A subtitle the translator could not do and left blank. |
| video file | 影片檔 | 视频文件 | 動画ファイル | video file |  |
| shortcuts | 鍵盤快捷鍵 | 键盘快捷键 | キーボードショートカット | keyboard shortcuts | Key names (Space, Ctrl, Shift, arrows) stay as they are in every language. |
| language name (player) | 繁體中文, 한국어 | backend native name | the backend's native name | Traditional Chinese, Korean | The window shows the backend's English name in English and the native name in the other languages. The UI language picker keeps native names. zh-CN: Comes from the backend, as in zh-TW. ja: As in zh-TW; the catalog has no text for it. |

## W3b: the batch, the editor, export and the summary

| Concept | zh-TW | zh-CN | ja | English | Note |
| --- | --- | --- | --- | --- | --- |
| batch (the processing queue) | 佇列 | 队列 | バッチ | batch | The videos waiting to be translated, on the home screen, in the player's tab and in the toolbar chip ("Batch 2/7"). From W3b the English says "batch", not "queue", so it never reads like the library's "play queue" (播放佇列, W3a). W1's toolbar and toast texts follow ("View batch", "3 items added to the batch"). The player's tab says "Batch" too. zh-CN: The player tab and the toolbar chip say 队列 too. ja: Chip "バッチ 2/7", tab バッチ. |
| add to batch | 加入佇列 | 加入队列 | バッチに追加 | add to batch | The dialog title and its button ("Add to batch (3)"). The toolbar button stays "Batch add" (批次加入). zh-CN: The toolbar button stays 批量添加. |
| item | 項 | 项 | 項目 | item | One video and one subtitle language in the batch. "2/7 processed". ja: Counted with 件: "2/7 件処理済み". |
| waiting, processing, paused, done, failed, cancelled | 等待中, 處理中, 已暫停, 完成, 失敗, 已取消 | 等待中, 处理中, 已暂停, 完成, 失败, 已取消 | 待機中, 処理中, 一時停止中, 完了, 失敗, キャンセル済み | Waiting, Processing, Paused, Done, Failed, Cancelled | The state of an item. |
| clear finished | 清除已完成 | 清除已完成 | 完了した項目を消去 | Clear finished |  |
| sleep, shut down | 睡眠, 關機 | 睡眠, 关机 | スリープ, シャットダウン | sleep, shut down | What the computer does when the batch finishes. "Put the computer to sleep", "Shut down". |
| countdown | 倒數 | 倒计时 | カウントダウン | countdown | The 60 seconds before sleep or shutdown, which "Cancel" stops. |
| original | 原文 | 原文 | 原文 | original | In the export menu: "SRT (original)". ja: "SRT 原文". |
| bilingual (export) | 雙語 | 双语 | 二言語 | bilingual | "SRT (bilingual)", "ASS (bilingual)", "VTT (bilingual)". The format names stay. ja: "SRT 二言語". |
| export | 匯出 | 导出 | エクスポート | export | "Exported to C:\...", "Export cancelled", "Export failed: ...". ja: Pairs with インポート. Never 書き出し. |
| start, end (of a subtitle) | 開始, 結束 | 开始, 结束 | 開始, 終了 | Start, End | The two times in the cue editor. |
| undo | 復原 | 撤销 | 元に戻す | undo | "Couldn't undo: ...". |
| jump to | 跳到 | 跳到 | 移動 | jump to | A chapter time in the summary: "Jump to 1:05:30". ja: "{time} に移動". |

## W4a: sentences from the backend and the shell

| Concept | zh-TW | zh-CN | ja | English | Note |
| --- | --- | --- | --- | --- | --- |
| burned-in subtitles | 燒錄出來的字幕 | 烧录出来的字幕 | 焼き込んだ字幕 | burned-in subtitles | The old backend sentences say 燒錄 and the window's menus say 燒入. Both are kept in Chinese. |
| empty boxes | 空白方塊 | 空白方块 | 空白の四角 | empty boxes | What a font with no glyph draws. |
| glyph | 字形 | 字形 | 字形 | glyph |  |
| Optional features | 選用功能 | 可选功能 | オプション機能 | Optional features | The Windows settings page, quoted with its path: "Settings > System > Optional features". zh-CN: Windows 11 zh-CN: 设置 > 系统 > 可选功能. ja: "設定 > システム > オプション機能". |
| Japanese supplemental fonts | 「日文」的補充字型 | 日语补充字体 | 日本語の補助フォント | Japanese supplemental fonts |  |
| Media Feature Pack | 媒體功能套件 | 媒体功能包 | メディア機能パック | Media Feature Pack | Microsoft's name. zh-CN: Microsoft's zh-CN name. |
| Font Book | 字體簿 | 字体册 | Font Book | Font Book | Apple's name. zh-CN: Apple's zh-CN name. ja: The macOS Japanese name is also Font Book. |
| runtimes folder | 執行檔資料夾 | 运行环境文件夹 | 実行ファイル用フォルダー | runtimes folder | "Runtime" is the glossary word for 執行環境 and 執行檔. |
| update source | 更新來源 | 更新来源 | 更新元 | update source |  |
| signature | 簽章 | 签名 | 署名 | signature |  |
| backend | 後端 | 后端 | バックエンド | backend |  |

## W4b part 1: backend messages in Traditional Chinese

Here the English came first and `zh-TW` is new text.

| Concept | zh-TW | zh-CN | ja | English | Note |
| --- | --- | --- | --- | --- | --- |
| remote registry, registry (update check) | 遠端清單, 清單 | 远程清单, 清单 | リモートの一覧, 一覧 | remote registry, registry | The app's list of models and runtimes. Not 登錄檔, which is the Windows registry. The table's "Listed version" stays 登錄版本. |
| speech engine | 辨識引擎 | 识别引擎 | 認識エンジン | ASR engine, engine |  |
| ASR, VAD, LLM | 語音辨識, VAD, LLM | 语音识别, VAD, LLM | 音声認識, VAD, LLM | ASR, VAD, LLM | VAD and LLM stay as they are. |
| fallback (speech recognition) | 備用 | 备用 | 予備 | fallback | 備用語音辨識. zh-CN: 备用语音识别. ja: 予備の音声認識. |
| audio track | 音訊軌 | 音轨 | 音声トラック | audio track |  |
| token | token | token | トークン | token | Not translated. |
| context (LLM) | 內容長度 | 上下文长度 | コンテキスト | context | ja: コンテキスト長 for context length. |
| archive | 壓縮檔 | 压缩包 | アーカイブ | archive |  |
| exit code | 結束代碼 | 退出代码 | 終了コード | exit code |  |
| redirect | 轉址 | 重定向 | リダイレクト | redirect |  |
| locked by another program | 被其他程式鎖定 | 被其他程序锁定 | 別のプログラムによってロック | locked by another program |  |
| File Explorer | 檔案總管 | 文件资源管理器 | エクスプローラー | File Explorer | Microsoft's name. zh-CN: Microsoft's zh-CN name. |
| command window | 命令列視窗 | 命令行窗口 | コマンドウィンドウ | command window |  |
