# 更新簽章金鑰：你要做的步驟

這份說明給操作者本人。照順序做就好，不需要寫程式。

App 會用「更新簽章」確認下載到的更新檔真的是你發布的。這把金鑰只有你能碰。我們（AI 助手）不會讀取、複製或經手私密金鑰和密碼。

> **狀態（2026-11-28）：** 第 1 到第 4 步你已經做完了。新金鑰有密碼，金鑰編號是 `501D2BFE8D7BD4B3`。GitHub 上已經有 `release` 環境：你是必要的核准人，可以核准自己推送的版本，只有 `v*` 標籤能用，兩個秘密值 `TAURI_SIGNING_PRIVATE_KEY` 和 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` 也貼好了。新的公開金鑰已經放進 `app/src-tauri/tauri.conf.json`。舊金鑰（編號 `6B4A3984C4140F4D`）照第 5 步留著，直到沒有任何已安裝的 App 還需要它。
>
> 下面的步驟留著，給之後換金鑰或重新設定時參考。

## 你要做的事，一覽

1. 產生一把有密碼的新金鑰。
2. 把金鑰和密碼各備份兩份。
3. 在 GitHub 建立 `release` 環境，設定成要你核准，再貼上金鑰和密碼。
4. 把「公開金鑰」傳給我們，我們放進 App 的設定檔。
5. 舊金鑰先留著，不要刪。

全部做完之前，不要推送任何 `v` 開頭的版本標籤。

## 1. 產生新金鑰

1. 打開 PowerShell。
2. 輸入下面兩行，每行輸入完按 Enter：

   ```powershell
   cd D:\WebProject\speech-subtitle-ai\app
   npx tauri signer generate -w "$HOME\.tauri\video-subtitle-translator-2026.key"
   ```

3. 它會請你輸入密碼兩次。畫面上不會顯示你打的字，這是正常的。
   - 密碼請用長一點的句子，至少 16 個字元。
   - 立刻把密碼存進你的密碼管理工具。
4. 完成後，資料夾 `C:\Users\<你的帳號>\.tauri` 裡會多兩個檔案：
   - `video-subtitle-translator-2026.key`：**私密金鑰**。絕對不能給別人。
   - `video-subtitle-translator-2026.key.pub`：**公開金鑰**。可以公開，第 4 步要用。

檔名用 `-2026`，是為了不要蓋掉舊金鑰 `video-subtitle-translator.key`。

## 2. 備份（兩份，放在不同地方）

私密金鑰檔案和密碼要分開放。只有金鑰檔或只有密碼，都不能用來簽章。

建議這樣放：

- **第一份：** 把 `video-subtitle-translator-2026.key` 複製到一支 USB 隨身碟或外接硬碟。放在家裡固定的地方，平常不插在電腦上。
- **第二份：** 把同一個檔案當成附件，存進你的密碼管理工具（和密碼放在不同的項目）。或者放在第二支隨身碟，收在另一個地點。
- **密碼：** 存在密碼管理工具。也可以手寫一份，和第一份隨身碟分開收好。

不要這樣做：

- 不要放進這個專案的資料夾，也不要上傳到 GitHub 的程式碼裡。
- 不要用 email、聊天軟體或雲端硬碟的公開連結傳送。
- 不要貼給 AI 助手。

金鑰或密碼弄丟，就再也不能推送更新給已經安裝的人。他們只能自己手動重新安裝。

## 3. 在 GitHub 建立 `release` 環境

這一步讓發布流程拿得到金鑰，而且每次都要你按核准才會用到它。

1. 用瀏覽器打開 https://github.com/ANONEKO777/speech-subtitle-ai/settings/environments 。
2. 按「New environment」。名稱輸入 `release`（全部小寫），按「Configure environment」。
3. **Deployment protection rules：**
   - 勾選「Required reviewers」，在框裡輸入你自己的 GitHub 帳號，選取它。
   - 「Prevent self-review」**不要勾**。版本標籤是你推送的，勾了你就不能核准自己的發布。
   - 按「Save protection rules」。
4. **Deployment branches and tags：**
   - 下拉選單選「Selected branches and tags」。
   - 按「Add deployment branch or tag rule」，類型選「Tag」，輸入 `v*`，按「Add rule」。
   - 這樣只有 `v` 開頭的版本標籤能用到金鑰。
5. **Environment secrets：** 按「Add environment secret」，新增兩個：
   - 名稱 `TAURI_SIGNING_PRIVATE_KEY`。內容是私密金鑰檔案的全部文字。複製的方法：在 PowerShell 輸入

     ```powershell
     (Get-Content "$HOME\.tauri\video-subtitle-translator-2026.key" -Raw).Trim() | Set-Clipboard
     ```

     然後在網頁的「Value」框裡按 Ctrl+V 貼上，按「Add secret」。
   - 名稱 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`。內容是第 1 步設的密碼。
6. 貼完之後，在 PowerShell 輸入下面這行，清掉剪貼簿裡的金鑰：

   ```powershell
   Set-Clipboard -Value " "
   ```

注意：GitHub 遇到流程用到一個還不存在的環境時，會自動建立一個**沒有核准設定**的同名環境。所以一定要先做完這一步，才能推送第一個版本標籤。

做完之後，貼進去的密碼和金鑰在 GitHub 上看不到內容，這是正常的。要換的話只能重新貼一次。

## 4. 把公開金鑰傳給我們

1. 在 PowerShell 輸入：

   ```powershell
   Get-Content "$HOME\.tauri\video-subtitle-translator-2026.key.pub"
   ```

2. 畫面會出現一長串英數字。把這一串完整複製，傳給我們。這是公開金鑰，給別人看沒有關係。
3. 我們會把它放進 `app/src-tauri/tauri.conf.json` 的 `pubkey`，開一個 PR 給你看。合併之後，新版 App 只接受新金鑰簽的更新。

如果你想自己改：打開 `app/src-tauri/tauri.conf.json`，找到 `"pubkey": "` 開頭那一行，把引號裡面的文字換成上面那一串。其他地方都不要動。

**只傳 `.key.pub` 的內容。** 檔名結尾是 `.key`、沒有 `.pub` 的那個檔案，永遠不要傳。

## 5. 舊金鑰為什麼先不要刪

舊金鑰是 `C:\Users\<你的帳號>\.tauri\video-subtitle-translator.key`，金鑰編號 `6B4A3984C4140F4D`。0.1.0 的安裝檔都是用它簽的。

- 你電腦上現在裝的 App，只認得舊金鑰。用新金鑰簽的版本，它不會自動更新，你要手動重新安裝一次新版。
- 留著舊金鑰，之後還有一條退路：可以用舊金鑰簽一個「過渡版」，讓舊版 App 自動更新一次，換成認得新金鑰的版本。刪掉就沒有這條路了。
- 新金鑰萬一出問題（例如密碼記錯），舊金鑰還能讓你回頭處理。

舊金鑰要留到沒有任何已安裝的 App 還需要它為止：還在用的 0.1.0 都已經換成新版，而且用新金鑰發布的版本，你已經實際更新成功過一次。不確定的話，留著也沒有壞處，只要一樣保管好。

## 之後每次發布時

1. 告訴我們要發布的版本號。我們改版本號、寫更新說明，開 PR 給你看。
2. 合併後，推送版本標籤（例如 `v0.2.0`）。
3. GitHub 會通知你有一個等待核准的部署。到該次流程的頁面按「Review deployments」，勾選 `release`，按「Approve and deploy」。
4. 流程跑完後，到 Releases 頁面看那個**草稿**，確認檔案和說明，再按「Publish release」。按之前，使用者看不到，App 也收不到更新。
