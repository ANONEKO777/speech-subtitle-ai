import type { MissingAsset } from "./types";

export const LOCAL_BUILD_SCRIPT = "scripts/mac/build_whisper_cli.sh";

/** Said where a program that this Mac builds for itself would otherwise show a size and a download. */
export const LOCAL_BUILD_TEXT = `在這台 Mac 上自行建置（${LOCAL_BUILD_SCRIPT}，步驟見 docs/MACOS.md）`;

/** Said under a program that was found on PATH or in Homebrew: the app did not put it there and will not delete it. */
export const LOCAL_BUILD_ELSEWHERE_TEXT = "不是 App 建置的，是在 PATH 或 Homebrew 的資料夾找到的。App 不會刪它，要移除請自己處理。";

/** Said where "檢查更新" would otherwise call a program that was built here "已是最新" without checking it. */
export const LOCAL_BUILD_NO_UPDATE_TEXT = `自行建置的程式沒有更新檢查，要換新版請重新執行 ${LOCAL_BUILD_SCRIPT}`;
export const LOCAL_BUILD_ELSEWHERE_NO_UPDATE_TEXT = "沒有更新檢查";

export const toDownload = <T extends Pick<MissingAsset, "localBuild">>(list: readonly T[]): T[] => list.filter((m) => !m.localBuild);

export const toBuild = <T extends Pick<MissingAsset, "localBuild">>(list: readonly T[]): T[] => list.filter((m) => m.localBuild);
