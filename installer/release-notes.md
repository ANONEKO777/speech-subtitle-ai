${NOTES}

## Install on Windows

1. Download `${INSTALLER}` below.
2. Open it. It installs for your Windows account only and needs no administrator rights.
3. The first time you use a feature, the app downloads the speech and language models it needs.

The installer is not code-signed yet, so Windows may warn you:

- **Microsoft Edge** may say the file "isn't commonly downloaded". Open the downloads list, select **...** on the file, select **Keep**, then **Show more** and **Keep anyway**.
- **SmartScreen** may show "Windows protected your PC". Select **More info**, then **Run anyway**.

To check the download, run `Get-FileHash <file name>` in PowerShell and compare the result with the line for that file in `SHA256SUMS.txt`.

Already installed? Open **Settings** in the app and check for updates. The update is checked against its signature before it installs.

Source code: https://github.com/ANONEKO777/speech-subtitle-ai (AGPL-3.0-or-later). Third-party licenses are in `THIRD_PARTY.md` in the install folder.

## 在 Windows 上安裝（繁體中文）

1. 下載下方的 `${INSTALLER}`。
2. 打開它。程式只安裝在你自己的 Windows 帳號下，不需要系統管理員權限。
3. 第一次使用某個功能時，App 會下載需要的語音和語言模型。

安裝檔目前還沒有程式碼簽章，所以 Windows 可能會跳出警告：

- **Microsoft Edge** 可能顯示「不常下載」。打開下載清單，在檔案上按「**...**」，按「**保留**」，再按「**顯示更多**」和「**仍要保留**」。
- **SmartScreen** 可能顯示「Windows 已保護您的電腦」。按「**其他資訊**」，再按「**仍要執行**」。

要核對下載的檔案，可以在 PowerShell 執行 `Get-FileHash <檔名>`，把結果和 `SHA256SUMS.txt` 裡同一個檔案的那一行比對。

已經安裝過了？在 App 的「**設定**」頁檢查更新。更新檔會先核對簽章才安裝。

原始碼：https://github.com/ANONEKO777/speech-subtitle-ai（AGPL-3.0-or-later）。第三方授權在安裝資料夾裡的 `THIRD_PARTY.md`。
