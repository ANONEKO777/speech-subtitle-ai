import type { MissingAsset } from "./types";

export const LOCAL_BUILD_SCRIPT = "scripts/mac/build_whisper_cli.sh";

/** Said where a program that this Mac builds for itself would otherwise show a size and a download. */
export const LOCAL_BUILD_TEXT = `在這台 Mac 上自行建置（${LOCAL_BUILD_SCRIPT}，步驟見 docs/MACOS.md）`;

export const toDownload = <T extends Pick<MissingAsset, "localBuild">>(list: readonly T[]): T[] => list.filter((m) => !m.localBuild);

export const toBuild = <T extends Pick<MissingAsset, "localBuild">>(list: readonly T[]): T[] => list.filter((m) => m.localBuild);
