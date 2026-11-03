# M0 報告：ASR 引擎實測

日期 2026-11-03。目的是在寫 pipeline 之前，用兩支真實演講影片比較 whisper.cpp large-v3-turbo 與 CrispASR 的 Qwen3-ASR-1.7B（加 Qwen3-ForcedAligner），依證據選出預設引擎與備援引擎。

## 測試環境

- GPU：RTX 4090，24,564 MiB，驅動 596.36。Windows 11。
- 測試時機器沒有閒置：Unity、瀏覽器等程式常駐，約占 3.4 GB 顯存、CPU 約 35%。所以兩個引擎交錯執行，讓兩邊承受相同的背景負載。
- 素材只放在本機，不進 repo：

| 代號 | 影片 | 長度 |
|---|---|---|
| talk38 | `上個月向生產環境提交 2500 個 PR 的方法-lauren @poteto X.mp4` | 2,282.0 s |
| talk57 | `一個人指揮50多個Agent-lauren @poteto X.mp4` | 3,423.8 s |

兩支影片先用 ffmpeg 轉成 16 kHz 單聲道 WAV，再交給兩個引擎。

## 下載的檔案

全部放在主 checkout 的 `runtimes/` 與 `models/`，兩者都在 `.gitignore` 裡。每個檔案的 SHA256 都已和來源公布的雜湊比對過。

| 檔案 | 版本 | 來源 | 大小（bytes） | SHA256 | 授權 |
|---|---|---|---|---|---|
| `runtimes/_archives/whisper-bin-win-cuda-12.4.0-x64.zip` | whisper.cpp v1.9.5（release b5454） | https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-win-cuda-12.4.0-x64.zip | 684,913,404 | `afef0b881c500958921c3f5523b50e59ee2ec9b6f5cbd25b324c51ed308a957a` | 程式 MIT，但 zip 裡沒有 LICENSE 檔。附帶的 CUDA DLL 屬 NVIDIA CUDA EULA |
| `runtimes/_archives/crispasr-windows-x86_64-cuda.zip` | CrispASR v0.8.49（git d9426437） | https://github.com/CrispStrobe/CrispASR/releases/download/v0.8.49/crispasr-windows-x86_64-cuda.zip | 786,801,567 | `c627c46b51e2b2f21a55c55a71f19fab954fc40089e8ded852005fc1a196637c` | 程式 MIT。附帶的 CUDA DLL 屬 NVIDIA CUDA EULA |
| `models/whisper/ggml-large-v3-turbo.bin` | HF `ggerganov/whisper.cpp` @ `5359861` | https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/ggml-large-v3-turbo.bin | 1,624,555,275 | `1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69` | MIT |
| `models/qwen3-asr/qwen3-asr-1.7b-q8_0.gguf` | HF `cstr/qwen3-asr-1.7b-GGUF` @ `674df5d` | https://huggingface.co/cstr/qwen3-asr-1.7b-GGUF/resolve/674df5d44b50a63e7102a18895ed20e3f91de301/qwen3-asr-1.7b-q8_0.gguf | 2,506,723,200 | `9851ab996591a2d0cb0efb216002764b509c86bd40c95e613d7b65b8e69c8a6e` | Apache-2.0 |
| `models/qwen3-forced-aligner/qwen3-forced-aligner-0.6b-q8_0.gguf` | HF `cstr/qwen3-forced-aligner-0.6b-GGUF` @ `1ec5110` | https://huggingface.co/cstr/qwen3-forced-aligner-0.6b-GGUF/resolve/1ec5110602ccab18c878ddebedab0891e290a95c/qwen3-forced-aligner-0.6b-q8_0.gguf | 985,594,624 | `539df5dd0fe1721e378ac13bfac9a26b1260dafb62d892c518c1f21244762636` | Apache-2.0 |
| `models/silero-vad/ggml-silero-v6.2.0.bin` | HF `ggml-org/whisper-vad` @ `9ffd54a` | https://huggingface.co/ggml-org/whisper-vad/resolve/9ffd54a1e1ee413ddf265af9913beaf518d1639b/ggml-silero-v6.2.0.bin | 885,098 | `2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987` | MIT |

說明如下。

- whisper.cpp 的 `v1.9.5` tag 沒有附執行檔。同一天的 `b5454` 自動 release 才有 Windows CUDA 版，`whisper-cli --version` 印出 `1.9.5`。
- Qwen 官方沒有發布 GGUF。`cstr/*` 是 CrispASR 作者轉換的版本，也是 CrispASR 內建 registry（`src/crispasr_model_registry.cpp`）指向的來源。原始權重 `Qwen/Qwen3-ASR-1.7B` 與 `Qwen/Qwen3-ForcedAligner-0.6B` 都是 Apache-2.0，不需要同意條款。
- 兩個 Qwen 模型都用 q8_0。registry 預設的 q4_k 精度較低，和全精度的 whisper 比較不公平。f16 沒有測。
- CrispASR 的 zip 已附 CUDA 12 的 DLL，不需要安裝 CUDA Toolkit。whisper.cpp 的 zip 也一樣。
- 兩個 zip 都不是全部 MIT。兩者都附 `cudart64_12`、`cublas64_12`、`cublasLt64_12`，whisper.cpp 另附 `nvblas64_12`、`nvrtc64_120_0`、`nvrtc-builtins64_124`，這些 DLL 屬 NVIDIA CUDA EULA。程式以子行程呼叫它們，AGPL 不會延伸到這些檔案，但打包時要逐一對照 EULA 的可再散布清單並附上聲明。whisper.cpp 的 zip 沒有 LICENSE 檔，再散布時要自己附上 MIT 全文。
- `cstr/*` 的 GGUF 檔頭沒有授權、來源或 basename 的 metadata，只有架構與量化資訊。來源只能靠 HF commit 與 SHA256 確認。這能確認檔案沒被換過，但無法確認轉換忠於官方權重。
- audio.cpp 沒有測。CrispASR 已經有官方 Windows CUDA 版且能跑完兩支影片，M0 只需要一個可用的 Qwen3 方案。

## 怎麼跑

腳本在 `scripts/m0/`。執行檔與模型路徑都由參數傳入。

CrispASR v0.8.49 打不開含非 ASCII 字元的輸入檔路徑，例如這兩支影片的中文檔名（`error: input file not found`），whisper-cli 則可以。只有輸入檔路徑實測會失敗；執行檔、模型、輸出目錄的路徑沒有試過，是推廣出來的保險，守門仍保留。所以 harness 一律把輸入轉成 `<檔名中的 ASCII 部分>-<來源完整路徑 SHA256 的前 8 碼>.wav`，輸出檔也用這個名字。`run_crispasr.py` 在轉檔前就檢查這些參數，遇到非 ASCII 的執行檔、模型、輸出目錄會直接停下並說明原因。P04 的 CrispASR 包裝必須同樣處理。

```
uv run python scripts/m0/run_whispercpp.py <wav 或影片> --bin <whisper-cli.exe> --model <ggml-large-v3-turbo.bin> --out-dir <dir> --run-id r1
uv run python scripts/m0/run_crispasr.py <wav 或影片> --bin <crispasr.exe> --model <qwen3-asr-1.7b-q8_0.gguf> --aligner <qwen3-forced-aligner-0.6b-q8_0.gguf> --vad-model <ggml-silero-v6.2.0.bin> --out-dir <dir> --run-id r1
uv run python scripts/m0/compare.py <dir> --audio-dir <wav 目錄> --out comparison.md
```

- whisper.cpp 用官方預設：beam 5、best-of 5、flash attention 開啟，輸出 `-osrt -ojf`，不開 VAD。
- CrispASR 用 `--backend qwen3 -am <aligner> --vad -vm <silero> --strict-pipeline -osrt -ojf`。加 `--strict-pipeline`，VAD 或對齊失敗時程式會回傳非零結束碼，不會只印警告。
- 每次執行都寫一個 `<engine>-<wav 名稱>-<run>.run.json`。內容是指令、結束碼、牆鐘時間、RTF、顯存基準與峰值，以及統一格式的段落和字詞時間。原始的 SRT、JSON、log 與每 500 ms 的顯存取樣（`.vram.csv`）放在同一個目錄。
- 顯存用 `nvidia-smi --query-gpu=memory.used` 取整張卡的用量。Windows WDDM 下每個行程的用量顯示 N/A，所以表格同時列出執行前的基準值。
- 執行順序是 W38、C38、W38、C38、W38、C38、W57、C57。

## 結果

| 影片 | 引擎 | RTF（中位數，範圍） | 顯存峰值 MiB（基準） | 抽樣錯字數 | VAD 段尾斷句錯誤 | 時間軸違規 | 最後一段結束 / 長度 s |
|---|---|---|---|---|---|---|---|
| talk38 | whisper.cpp large-v3-turbo | 0.0180（0.0161 到 0.0183，3 次） | 5,750（3,463） | 3 | 0（整檔執行，見下文） | 0 | 2,281.8 / 2,282.0 |
| talk38 | CrispASR Qwen3-ASR-1.7B + aligner | 0.0419（0.0395 到 0.0449，3 次） | 10,738（3,496） | 3 | 9 | 0 | 2,280.8 / 2,282.0 |
| talk57 | whisper.cpp large-v3-turbo | 0.0170（1 次） | 5,728（3,432） | 7 | 0（整檔執行，見下文） | 0 | 3,423.5 / 3,423.8 |
| talk57 | CrispASR Qwen3-ASR-1.7B + aligner | 0.0439（1 次） | 10,747（3,460） | 5 | 9 | 0 | 3,423.5 / 3,423.8 |

- 顯存峰值取 3 次中的中位數。三次的峰值是 whisper.cpp 5,750、5,782、5,718，CrispASR 12,946、10,738、10,706。CrispASR 第一次在第 24 秒多出約 2.2 GB，後兩次沒有重現，推測是背景程式造成，但沒有證明。扣掉基準後，whisper.cpp 自己約用 2.3 GB，CrispASR 約用 7.3 GB。
- 兩個引擎都跑完 57 分鐘，沒有中斷，結束碼都是 0。沒有連續重複三次以上的段落。最長的無字幕空檔是 7.0 s（whisper.cpp，talk57 第 415 s），CrispASR 在同一段也只辨識出一個字，是講者在操作畫面。
- 同一引擎三次執行的逐字稿完全相同。
- 段落形狀不同。whisper.cpp 的段落中位數 7.0 s（talk38）與 4.3 s（talk57），最長 120 與 354 個字元，比較接近字幕長度。CrispASR 的段落就是 VAD 切塊，中位數 27.5 s 與 27.9 s，最長 504 與 621 個字元。兩者都要靠字詞時間重新斷行才能當字幕。

### 抽樣錯字

`compare.py` 依影片名稱當亂數種子，在每支影片的前、中、後三分之一各抽一段 2 分鐘，共 6 段。它把兩個引擎在這段時間內的字詞做 diff，列出每一處不一致，共 106 處。

沒有人工逐字稿，代理也聽不到音訊。所以錯字數是讀上下文判定的結果，不是聽過的結果。判定規則如下。

- 不算錯：語助詞（um、uh）、重複的口吃、`code base` 與 `codebase` 這類空格差異、`20` 與 `Twenty`、大小寫、視窗邊緣的截斷。
- 算錯：上下文明顯不對的字。兩邊都錯就各算一次。
- 判不出來的另外列，不算進表格。
- 每一處判定（對應 `comparison.md` 的表格編號）記在本機的 `D:/WebProject/m0-work/adjudication.md`，不進 repo，因為裡面有大段逐字稿。

| 影片 | whisper.cpp 的錯 | CrispASR 的錯 |
|---|---|---|
| talk38 | `Grogbot`（前後都是 Grokbot）、`kickoff` 當動詞（只是拼法）、`Grokbot's`（複數 Grokbots，只是拼法） | `Encurser`（within Cursor）、`would just Guessing`（was just guessing）、`Expiration`（that exploration） |
| talk57 | `AI sloth`、`human sloth`（slop）、`big tech info`（infra）、`make CI read`（red）、`the agent can just write crappy code`（can't，意思相反）、`rank Go`、`report's`（只是拼法） | `and chipping code`（shipping）、`Uh, sound that sounds`（this sounds）、`rankle`、`bogbot` 兩次（Bugbot） |

判不出來的有 4 處：CrispASR 的 `in Skill itself`（漏 the？）、`combined` 對 `combine`、`can and do`，以及 `like they're not` 對 `that they're not`。

CrispASR 另有一種整檔執行的 whisper.cpp 沒有的錯。它在每個 VAD 切塊的邊界加句號或大寫，把一句話切斷，例如 `use that to make. Really good decisions`、`there were like. Twenty PRs`。6 段裡共 18 處。這會直接影響後面的斷句與翻譯。

但這不是同條件比較。whisper.cpp 是整檔執行，CrispASR 是跑在 VAD 切塊上，而 P03 會把 20 到 30 秒的切塊交給引擎。獨立稽核拿 CrispASR 的同一批切塊，挑其中 5 處斷句讓 whisper.cpp 重跑（CPU）。whisper.cpp 在 2 處切塊邊界加了句號（`of that.`、`if you want.`，後者還漏了 `and`），但都沒有加大寫。CrispASR 5 處都斷。所以在相同切塊上 whisper.cpp 仍然較少斷句，但差距沒有 18 比 0 那麼大。兩個引擎都需要在 P03 或 P04 修補切塊邊界的標點：下一個字是小寫，或兩段間隔不到約 0.5 s 時，不要相信邊界上的句號。

### 時間軸

`compare.py` 用兩種方法檢查時間。第一種比較兩個引擎都聽到的同一個字的開始時間。第二種不靠任何 ASR，從音量找出「至少 0.6 s 安靜之後開始說話」的時間點，再看每個引擎最近的字差多少。

| 影片 | 檢查 | whisper.cpp | CrispASR |
|---|---|---|---|
| talk38 | 說話起點，誤差中位數 / p90 / 0.5 s 內 | 0.12 s / 0.49 s / 90% | 0.04 s / 0.60 s / 82% |
| talk57 | 說話起點，誤差中位數 / p90 / 0.5 s 內 | 0.14 s / 0.56 s / 87% | 0.04 s / 0.48 s / 91% |
| talk38 | 同一個字，CrispASR 減 whisper.cpp | 中位數 +0.20 s，p90 0.87 s，70% 在 0.5 s 內 | |
| talk57 | 同一個字，CrispASR 減 whisper.cpp | 中位數 +0.35 s，p90 1.16 s，59% 在 0.5 s 內 | |

- 在說話起點，兩者大多落在 0.5 s 內。CrispASR 的中位數比較準（0.04 s 對 0.12 到 0.14 s）。尾端則各有勝負：talk38 是 whisper.cpp 較好（p90 0.49 s 對 0.60 s），talk57 是 CrispASR 較好。
- 在連續說話中，whisper.cpp 預設的 token 時間和 aligner 差很多。用 `-nfa -dtw large.v3.turbo` 再跑一次 talk38（只跑 1 次），whisper.cpp 的字詞時間和 CrispASR 有 97% 在 0.5 s 內，p90 0.37 s，但整體比說話起點晚約 0.21 s。DTW 和 flash attention 不能同時開，關掉後 RTF 是 0.0188。這是給 P04 的資料，不在上面的效能表裡。
- CrispASR 的中位數優勢來自切塊內的字，也就是 aligner。把說話起點依「最近的字是不是切塊第一個字」分開看（talk38），CrispASR 切塊第一個字的誤差中位數 0.36 s（n=52），切塊中間的字 0.03 s（n=73）。whisper.cpp 兩者都是 0.12 s。也就是 CrispASR 每個切塊的第一個字約晚 0.36 s 出現，P04 要處理。
- 15 秒測試音檔上，whisper.cpp 漏掉第一句和最後一句，CrispASR 三句都有。這個音檔整段都是 LibriVox 的固定開場白，推測是 whisper 的訓練逐字稿常略掉這類句子，所以漏字可能只發生在這類內容。獨立稽核用 3 段任意的 25 秒演講片段，和 10 個 5 到 30 秒的真實 VAD 切塊重跑 whisper.cpp，每次都保留了第一個和最後一個字，只掉了一個句尾的 `and`。兩支長影片上兩者的覆蓋率相同（對得上的字約 95%）。P04 要用演講切塊（不是這個 15 秒音檔）測頭尾漏字。另外，whisper.cpp 在短切塊上會少寫語助詞，逐字稿和整檔執行不會完全相同。

### 效能檢查（benchmark-checklist）

- 限制因素：兩個引擎都沒有用滿 GPU。whisper.cpp 執行中 GPU 使用率在 16% 到 50% 之間。CrispASR 中位數 37%，另有約 10 s 花在 CPU 上的 VAD。兩者都受逐字解碼（一次一個 token）限制，不是受算力限制。whisper.cpp 的 beam search 取樣在 CPU 上跑（4 個執行緒），所以 CPU 忙的時候會明顯變慢。
- RTF 是整個引擎行程的牆鐘時間除以音訊長度，包含載入模型的時間。
- RTF 受機器負載影響。驗證者在 CPU 負載 63% 到 67% 時重跑 talk38 三次，以引擎行程存活時間計算，whisper.cpp 是 0.0356、0.0377、0.0185（範圍 0.0185 到 0.0377），CrispASR 約 0.041（0.0413 到 0.0481）。whisper.cpp 三次的工作量完全相同，慢的兩次約有 50 s 花在 GPU 計時階段以外，也就是 CPU 端的取樣。順序不變：每一組交錯執行都是 whisper.cpp 較快，最差的 0.0377 也還在 0.2 門檻的五分之一以下。
- 調校：兩邊都用官方預設參數。沒有試 whisper.cpp 的 greedy 解碼或 CrispASR 的批次設定。兩者都遠低於 0.2 的門檻，所以這不影響選擇。
- 合理性：38 分鐘音訊在 37 到 41 秒內處理完，也就是 55 倍即時。4090 跑 0.8B 參數的 turbo 模型，這個速度合理。
- 錯誤：8 次正式執行的結束碼都是 0，都涵蓋到最後一分鐘，時間軸都單調遞增。
- 重現：38 分鐘影片每個引擎交錯跑 3 次。兩個引擎的差距約 2.3 倍，遠大於各自的範圍（whisper.cpp 0.0161 到 0.0183，CrispASR 0.0395 到 0.0449）。在較忙的機器上差距在 1.1 到 2.2 倍之間，見上一項。
- 確實執行：三次的逐字稿完全相同，每次約 5,500 到 5,800 個字。
- 基準：whisper.cpp 在 talk38 的 RTF 中位數 0.0180，作為後續 PR 的效能基準。比較時要記錄當下的 CPU 負載，否則差兩倍也可能只是負載不同。

## 結論

- 兩支演講的錯字數幾乎一樣：whisper.cpp 10 個（其中 3 個只是拼法），CrispASR 8 個。會改變內容的錯是 whisper.cpp 7 個、CrispASR 8 個。最嚴重的一個是 whisper.cpp 把 `can't` 聽成 `can`，意思完全相反，翻譯時會直接傳下去。樣本小，又是讀上下文判定的，不能說哪一個比較準。排行榜上 Qwen3-ASR 比較好，在這兩支影片上看不出差異。
- 在相同的 VAD 切塊上，whisper.cpp 的斷句錯誤仍然較少（5 處邊界中 2 處加句號、不加大寫，CrispASR 5 處都斷），段落也比較接近字幕長度。這是選 whisper.cpp 的主要原因，但整檔的 18 比 0 高估了差距，兩個引擎都需要修補切塊邊界的標點。whisper.cpp 也快 1.1 到 2.4 倍（看機器負載），顯存少用約 5 GB，但兩者都遠低於門檻，速度和顯存只是次要理由，主要影響 8 GB 設定。
- CrispASR 跑完 57 分鐘也很穩定，切塊內的字詞時間更準（切塊第一個字約晚 0.36 s），所以列為備援。顯存需求約 7.3 GB，8 GB 顯卡能不能跑留給 P11 實測。
- 兩者都能以子行程方式執行，並穩定輸出 JSON 與 SRT。

## 仍未證明

- 錯字數沒有人工聽寫的逐字稿做對照。Lane 7 的目測只檢查時間，不檢查用字。
- Qwen3-ASR 的 f16 與 q4_k、audio.cpp、whisper.cpp 開 VAD 的設定都沒有測。
- 57 分鐘影片每個引擎只跑 1 次。
- CrispASR 第一次執行多出的 2.2 GB 顯存原因不明。
- whisper.cpp 在 20 到 30 秒短段落上是否會漏掉頭尾的句子，要在 P04 用演講切塊驗證。15 秒音檔的漏字只在 LibriVox 開場白上出現，真實演講片段沒有重現，所以不太可能改變預設的選擇。
- 斷句的同條件比較只看了 5 處切塊邊界。P04 應該在 P03 的切塊上，對兩個引擎統計每個切塊邊界的斷句率。
- whisper.cpp 沒開 VAD，長時間靜音時是否會產生幻覺字幕沒有專門測。兩支影片都沒有重複段落，最長的空檔 7.0 s 只有一個字，原因（講者在操作畫面）是推測。
- whisper.cpp 的 GPU 使用率（16% 到 50%）只在主控台看過 10 秒，沒有存檔。CrispASR 的使用率存在 `D:/WebProject/m0-work/profile/crisp-util.txt`。

預設引擎：whisper.cpp large-v3-turbo（`whispercpp-large-v3-turbo`）。備援引擎：CrispASR Qwen3-ASR-1.7B 加 Qwen3-ForcedAligner-0.6B（`crispasr-qwen3-asr-1.7b`）。
