# 在 GitHub 發布安裝檔與 App 內自動更新：規劃

日期：2026-11-27。狀態：只是規劃，還沒有改任何程式。排在多國語系全部完成、通過實機驗證之後。

## 目標

1. 使用者到 GitHub 的 Releases 頁面，就能下載自己平台的安裝檔。
2. 已經安裝的人，App 會自己發現新版本，按一下就能下載並更新。

## 參考專案怎麼做（storytold/photocraft）

以下是我讀它 v0.23.1 的發布頁和工作流程檔看到的。它怎麼做 App 內更新我沒有讀。

- 發布流程是一個 GitHub Actions 工作流程。每個平台一個建置工作，各自在對應系統的機器上編譯。
- 所有建置完成後，最後一個工作把檔案收進同一個 Release。它先建成草稿，檢查檔案數量，再公開。
- 簽章金鑰放在名為 `release` 的 GitHub Environment 裡。你截圖裡的「Deployments → release」就是工作流程使用這個環境時留下的紀錄。
- macOS 版本要求簽章加 Apple 公證，Windows 版本要求程式碼簽章，Linux 版本用 GPG 簽章。缺金鑰時流程會直接失敗。
- 另外附 `SHA256SUMS.txt` 讓使用者核對檔案。
- 它有一個不簽章、不發布的演練模式，平常用來確認各平台還編得出來。

它支援 Windows、macOS、Linux、FreeBSD 和網頁版，因為它是一個純 Rust 程式。我們的情況不同，見下一節。

## 我們現在有什麼、缺什麼

### 已經有的

- **App 內更新的核心已經做好。** 設定頁有「檢查更新」。它會下載、核對簽章，再按「安裝並重新啟動」。
- 更新來源已經指向 `https://github.com/ANONEKO777/speech-subtitle-ai/releases/latest/download/latest.json`。
- 更新用的簽章金鑰在你的電腦上（`~/.tauri/video-subtitle-translator.key`），公開的那一半寫在設定檔裡。
- Windows 安裝檔腳本 `installer/build.ps1` 能產生安裝檔、簽章檔和 `latest.json`。
- macOS 有 `scripts/mac/build_app.sh`，能在 Mac 上做出 `.app` 和 `.dmg`。
- GitHub 上已經有一般測試用的 CI，包含 macOS 上的 Rust 編譯與測試。

### 缺的

| 缺什麼 | 說明 |
|---|---|
| 發布用的工作流程 | 目前沒有任何流程會建立 Release 或上傳檔案。GitHub 上也還沒有任何 Release 和金鑰設定。 |
| 啟動時自動檢查 | 現在只有按按鈕才檢查，說明文件也寫著啟動時不會檢查。 |
| **Windows 打包現在會失敗** | 腳本固定下載 2026-11-06 的 FFmpeg 版本。我查過，這個下載點已經不存在（404），目前主資料夾裡也沒有快取。FFmpeg 的提供者只長期保留月底版本。 |
| Mac 版還不能給一般人用 | 使用者要自己用指令編譯 `whisper-cli`，還要用 Homebrew 安裝 FFmpeg。下載 dmg 的人做不到這些。 |
| Mac 的 App 內更新 | 程式目前只允許 Windows 檢查更新。 |
| 版本號管理 | 版本號分散在三個地方（目前都是 0.1.0），沒有檢查它們是否一致。 |

## 能支援哪些平台

| 平台 | 判斷 | 原因 |
|---|---|---|
| Windows x64 | 第一批就做 | 只缺發布流程和 FFmpeg 修正 |
| macOS（Apple 晶片） | 第二批 | 要先把 `whisper-cli` 和 FFmpeg 的問題解決 |
| Linux | 這次不做 | App 目前明確不支援 Linux。要做等於新增一個平台，需要另外規劃，還需要有機器能測。 |
| Intel Mac、Windows ARM | 不做 | 目前不支援，也沒有機器能測 |

安裝檔不含模型，模型照舊由 App 下載，所以安裝檔不會很大。現在的上限是 150 MB。

## 兩種「簽章」是不同的東西

1. **更新簽章（已經有，免費）。** App 用它確認下載到的更新檔是你發布的。沒有它就不能更新。
2. **作業系統的程式碼簽章（目前沒有）。** 它決定使用者第一次安裝時，系統會不會跳警告。它和能不能自動更新無關。

### 沒有作業系統簽章時，使用者會看到什麼

- **Windows：** SmartScreen 藍色警告。使用者要按「其他資訊」，再按「仍要執行」。
- **macOS：** 系統會擋下 App。使用者要到「系統設定 → 隱私權與安全性」按「仍要打開」。從 macOS Sequoia 起，按右鍵打開的舊方法已經不能用。

### 要消除警告的選擇

- **macOS：** 加入 Apple Developer Program，每年 99 美元，加入後公證不另收費。
- **Windows，Azure Artifact Signing：** 查到的資料顯示，個人開發者目前只限美國和加拿大。如果你是以台灣個人身分申請，這條路走不通。公司身分的可用地區，查到的來源彼此不一致。
- **Windows，SignPath Foundation：** 對開源專案免費。條件包括開源授權、公開原始碼、全自動建置、帳號開啟多重驗證，且不能含專有元件。有來源提到要先有一個發布過的版本。憑證上的發行者名稱會是 SignPath Foundation。我們安裝檔內含微軟的 WebView2 啟動安裝程式，是否符合條件要在申請前確認。
- **Windows，向憑證商買憑證：** 可行，要年費。這次沒有查價格。

**我的建議：** 第一版兩個平台都先不做作業系統簽章，在下載頁寫清楚怎麼放行。第一版發布後申請 SignPath。要不要付 Apple 年費，等有外人要用 Mac 版時再決定。

## 分階段做法

### R0：發布前準備

- 修 FFmpeg 下載：改固定到月底版本，並在我們自己的 GitHub Release 放一份備份。重新核對授權檔案和雜湊值。
- 版本號改成只改一個地方。CI 檢查發布標籤和程式版本一致。
- **決定更新簽章金鑰。** 現在的金鑰沒有密碼。放到 GitHub 之前，建議換成有密碼的新金鑰。現在是最便宜的時機，因為還沒有公開發布過任何版本。之後再換，已安裝的人就收不到更新，只能手動重裝。換了之後，你自己用舊金鑰版本安裝的 App 也要手動重裝一次。
- 金鑰一定要另外備份。弄丟就無法再對已安裝的人推更新。
- 在 GitHub 建立 `release` 環境，設定「要你本人核准才能執行」。金鑰和密碼由你自己貼進 GitHub，我不經手。

### R1：Windows 自動發布

- 新增 `.github/workflows/release.yml`。推送 `v0.2.0` 這種標籤時啟動，也能手動執行演練模式。
- 步驟：跑測試 → 用 `build.ps1` 打包 → 簽更新簽章 → 產生 `latest.json` 和 `SHA256SUMS.txt` → 建立**草稿** Release。
- 草稿由你檢查後自己按「Publish」。在你按下之前，使用者看不到，App 也不會收到更新。
- Release 說明附上安裝步驟和放行 SmartScreen 的方法。

### R2：App 啟動時自動檢查更新

建議放在第一次公開發布**之前**做。否則第一批使用者的版本不會主動通知他們。

- 啟動後在背景檢查，不拖慢開啟速度。檢查失敗時不跳錯誤訊息。每天最多檢查一次。
- 有新版時顯示一條提示：版本號、更新內容，以及「下載並安裝」「稍後」「略過此版本」。
- **不會沒問過你就安裝。** 正在處理影片或佇列在跑時，不能安裝。現在的安裝流程會先停掉後端，直接安裝會中斷工作。
- 設定頁加「啟動時檢查更新」開關。README 和隱私說明要一起改，說明啟動時會連到 GitHub。
- 文字要走多國語系。

### R3：macOS 版

先解決讓一般人裝完就能用的兩件事：

1. **`whisper-cli`：** 改由 GitHub 的 Mac 機器編譯，直接放進 App。使用者就不用自己編譯。要附上它的授權聲明。
2. **FFmpeg：** 在 App 裡附一份不含 GPL 元件的版本。燒錄字幕需要它支援字幕繪製功能（libass）。**這是整個計畫裡最不確定的一項。** 找不到合適的現成版本時，就得在發布流程裡自己編譯。退路是第一版仍要求用 Homebrew 安裝 FFmpeg，並在 App 裡清楚提示。

之後再做：

- 發布流程加 Mac 工作，產出 `.dmg`，以及更新用的壓縮檔和簽章。
- `latest.json` 同時列出 Windows 和 Mac。
- 打開程式裡對 Mac 檢查更新的限制。
- 在你的 Mac 上實測安裝、處理影片，以及更新。沒有 Apple 公證時，App 內更新後系統會不會再次擋下，我不知道，只能實測。
- 之後若要做公證，App 裡附帶的每個執行檔都要簽章。後端打包出來的檔案很多，這一步可能要反覆除錯。

### R4：消除安裝警告（選做）

申請 SignPath，或付 Apple 年費做公證。這一步不影響前面的功能。

## 怎麼證明自動更新真的能用

只有真的更新一次才算數。目前的自動測試停在「安裝」之前。

1. 用演練模式確認打包成功。
2. 先發布一個測試版標成 pre-release。App 預設抓的「latest」不含 pre-release，一般使用者不會收到。測試時用現有的 `VST_UPDATE_URL` 指到它。
3. 在你的電腦安裝舊版，按更新，確認新版啟動、版本號正確、專案和模型都還在。
4. Mac 版做同樣的測試。
5. 通過後才公開第一個正式版。

## 發布一個新版本時，你要做的事（做完之後）

1. 跟我說要發布哪個版本號。我改版本號、寫更新說明。
2. 推送版本標籤。
3. 在 GitHub 按核准，讓流程使用簽章金鑰。
4. 流程做完後，看一下草稿 Release，按「Publish」。

## 需要你決定的事

你不回答的話，我照括號裡的預設做。

1. **啟動時自動檢查更新，要預設開啟嗎？**（預設開啟，設定頁可以關。）
2. **更新簽章金鑰要換成有密碼的嗎？**（建議換。換的指令和貼到 GitHub 的步驟由你自己執行，我會寫給你。）
3. **Mac 版要不要現在就付 Apple 年費做公證？**（先不付。）
4. **第一個公開版本號。**（0.2.0。）

## 順序

多國語系剩下的部分（收尾、後端文字、簡中和日文）→ 實機驗證 → 你驗收 → R0 → R1 和 R2 → 在 Windows 實測更新 → 公開第一版 → R3 → R4。

中文影片辨識原本排在多國語系之後。要先做發布，還是先做中文影片辨識，到時候由你決定。我的預設是先做發布的 R0 到 R2。

## 還沒確認的事

- 沒有試跑任何發布流程。
- Mac 的更新檔格式是依 Tauri 的一般做法寫的。這次搜尋沒有查到明確的官方說明，實作時要在 CI 上確認。
- GitHub Actions 對公開儲存庫的目前收費規定，這次沒有另外查。
- 簽章服務的資格和價格可能改變，申請前要看官方頁面。

## 參考來源

- [Azure Artifact Signing 快速入門](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart)
- [Windows 程式碼簽章的選擇](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [SignPath Foundation 條件](https://signpath.org/terms)
- [Apple Developer Program 註冊說明](https://developer.apple.com/help/account/membership/program-enrollment/)
- [Apple：打開來自未知開發者的 App](https://support.apple.com/ta-in/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/15.0/mac/15.0)
- [Gatekeeper 在 Sequoia 的改變](https://eclecticlight.co/2024/08/10/gatekeeper-and-notarization-in-sequoia/)
- [PhotoCraft v0.23.1 發布頁](https://github.com/storytold/photocraft/releases/tag/v0.23.1)
