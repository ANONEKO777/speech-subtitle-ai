# P23b 標註工具

目標：用人耳標註 Kirby 影片的 120 個短段，量出語言標記的正確率，作為 P23b 在候選 X（Qwen3 `-l auto`）與候選 Y（Whisper 逐段偵測）之間做決定的驗收資料。這個 PR 只有工具，沒有引擎。

## 流程

在專案根目錄（或 worktree）執行，產出放在 `.work/p23b-labels/`（被 `.gitignore` 擋住，不進版本庫）。

1. `uv run python scripts/p23b_sample.py` 取樣 120 段，寫 `manifest.json`。
2. `uv run python scripts/p23b_cut_clips.py "The Many Dimensions of Kirby_1080p.mp4"` 用 ffmpeg 切成 mono 16 kHz mp3，前後各 0.3 秒。影片只讀。
3. `uv run python scripts/p23b_make_page.py` 產生 `label.html`。操作者雙擊開啟，標完匯出 `labels.json`。
4. `uv run python scripts/p23b_score.py manifest.json labels.json tags.json` 對 P23b 引擎輸出的語言標記評分。

## 取樣

單位是 P22 的 300 ms 暫停切段（777 段）。理由：候選 X 逐段標記的就是這個切法，700 ms 切段把 60 段「日文後接英文」包在同一段裡，標註者拿到的是有兩個答案的段落。

| 層 | 段數 | 規則 |
|---|---|---|
| `disagree` | 14 | Whisper 語言偵測與 Qwen3 `-l auto` 文字種類（日或英）不同，全取 |
| `fragment` | 14 | 0.8 到 1.7 s 的短碎片：Whisper 偵測為韓文或中文，或 Qwen3 在日文偵測上寫成韓文字，全取 |
| `ja_then_en` | 32 | 60 段「日文後接英文」（700 ms 切段）裡的 300 ms 片段，每組取一個，沒被切開的組先取，其餘取 Whisper 聽成英文的最長片段 |
| `en_as_ja` | 20 | Whisper 偵測為英文、Qwen3 `-l ja` 寫成日文，2 s 以上，隨機 |
| `ordinary_ja` / `ordinary_en` | 20 / 20 | 不屬於上面任何一層、1.5 s 以上，隨機（種子 23） |

一段只算在第一個符合的層。層的總和是 120。長度範圍 0.81 到 15.2 s，沒有超過 30 s 的段，所以 `split_at_largest_pause` 在這份取樣沒有被用到，用合成資料測過。

標註頁只收到段落 id 和聲音檔路徑，看不到層、模型猜測與時間戳。這些放在 manifest 的 `guesses` 與 `stratum`，只有評分用。呈現順序是固定種子的洗牌。

## 評分

`p23b_score.py` 輸出每層正確率、2 s 以上的英文被寫成日文或丟掉的段落，以及所有不一致。`unclear` 的段落不計分。取樣刻意偏向難例，所以整體正確率不等於全片的正確率，要看各層的數字。評分腳本最後一行列出計畫的驗收門檻（98% 且 0 段英文遺失），只是對這 120 段的判定。

## 測試

- `scripts/p23b_page/page.test.js` 用 jsdom 載入產生的頁面，不開瀏覽器、不播放聲音。執行：`JSDOM_DIR=<jsdom 目錄> LABEL_HTML=<label.html 路徑> node --test scripts/p23b_page/page.test.js`。
- 評分腳本用假標註測過：假標註取自 Whisper 語言偵測，假標記取自 Qwen3 `-l auto`，只用來測腳本，不是真人標註。
