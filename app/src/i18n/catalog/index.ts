import { en } from "./en";
import { ja } from "./ja";
import { zhCN } from "./zh-CN";
import { zhTW } from "./zh-TW";
import type { Locale } from "../locale";

/** English is the source of the keys. Every other locale must hold exactly these keys, or `tsc` fails. */
export type English = typeof en;
export type Key = keyof English;

export const CATALOGS: Record<Locale, Readonly<Record<Key, string>>> = { en, "zh-TW": zhTW, "zh-CN": zhCN, ja };
