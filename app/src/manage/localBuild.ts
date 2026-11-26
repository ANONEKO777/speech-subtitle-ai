import type { Translate } from "../i18n";
import type { MissingAsset } from "./types";

export const LOCAL_BUILD_SCRIPT = "scripts/mac/build_whisper_cli.sh";

/** Said where a program that this Mac builds for itself would otherwise show a size and a download. */
export const localBuildText = (t: Translate): string => t("localBuild.text", { script: LOCAL_BUILD_SCRIPT });

/** Said under a program that was found on PATH or in Homebrew: the app did not put it there and will not delete it. */
export const localBuildElsewhereText = (t: Translate): string => t("localBuild.elsewhere");

/** Said where "Check for updates" would otherwise call a program that was built here "Up to date" without checking it. */
export const localBuildNoUpdateText = (t: Translate): string => t("localBuild.noUpdate", { script: LOCAL_BUILD_SCRIPT });
export const localBuildElsewhereNoUpdateText = (t: Translate): string => t("localBuild.elsewhereNoUpdate");

export const toDownload = <T extends Pick<MissingAsset, "localBuild">>(list: readonly T[]): T[] => list.filter((m) => !m.localBuild);

export const toBuild = <T extends Pick<MissingAsset, "localBuild">>(list: readonly T[]): T[] => list.filter((m) => m.localBuild);
